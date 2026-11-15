"""Offline contract checks: no SSH process, network connection, or browser."""
import json
import tempfile
import unittest
from pathlib import Path

from worker.approval_state import ApprovalStateError, ApprovalStore
from worker.execution_coordinator import FixtureOnlyPermit, OfflineExecutionCoordinator
from worker.ssh_protocol import parse_ssh_request
from worker.ssh_transport import SSHRunResult


class FakeTransport:
    _offline_fixture_transport = True

    def __init__(self, replies=None, raise_on=None):
        self.calls = []
        self.replies = replies or [SSHRunResult(0, "fixture", "", False, False)]
        self.raise_on = raise_on

    def run_command(self, host_alias, cwd, command, timeout_seconds):
        self.calls.append((host_alias, cwd, command, timeout_seconds))
        if self.raise_on is not None:
            raise self.raise_on
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "approval.sqlite"
        self.store = ApprovalStore(self.path)
        self.request = parse_ssh_request(json.dumps({
            "schema_version": 1, "kind": "ssh_batch",
            "request_id": "fixture-1", "target": "isolated-fixture",
            "working_directory": "/tmp", "description": "test only",
            "commands": [{"id": "one", "command": "id", "timeout_seconds": 7},
                         {"id": "two", "command": "uname -a", "timeout_seconds": 9}],
        }), {"isolated-fixture"})
        self.store.propose(self.request, tab_id=12, conversation_id="fixture-chat")
        self.approval = self.store.approve(
            "fixture-1", command_sha256=self.request.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        self.permit = FixtureOnlyPermit("fixture-1", self.approval, self.request.command_sha256)

    def test_ordered_fixture_execution_is_durable_and_one_time(self):
        fake = FakeTransport()
        coordinator = OfflineExecutionCoordinator(self.store, fake)
        result = coordinator.run(self.permit)
        self.assertEqual(result["mode"], "MOCK_ONLY")
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual([x[2] for x in fake.calls], ["id", "uname -a"])
        self.assertEqual([x[3] for x in fake.calls], [7, 9])
        self.assertEqual(self.store.get_mock_result("fixture-1"), result)
        with self.assertRaisesRegex(ApprovalStateError, "execution_not_approved"):
            coordinator.run(self.permit)
        self.assertEqual(len(fake.calls), 2)

    def test_failed_first_command_stops_batch(self):
        fake = FakeTransport([SSHRunResult(5, "", "fixture-error", False, False)])
        result = OfflineExecutionCoordinator(self.store, fake).run(self.permit)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(fake.calls), 1)

    def test_mock_approval_alone_cannot_start_executor(self):
        fake = FakeTransport()
        coordinator = OfflineExecutionCoordinator(self.store, fake)
        with self.assertRaisesRegex(ApprovalStateError, "fixture_permit_required"):
            coordinator.run(None)
        self.assertEqual(self.store.get("fixture-1")["status"], "APPROVED")
        self.assertFalse(fake.calls)

    def test_wrong_permit_denied_without_consuming_job(self):
        fake = FakeTransport()
        coordinator = OfflineExecutionCoordinator(self.store, fake)
        bad = FixtureOnlyPermit("fixture-1", self.approval, "0" * 64)
        with self.assertRaisesRegex(ApprovalStateError, "execution_digest_mismatch"):
            coordinator.run(bad)
        self.assertEqual(self.store.get("fixture-1")["status"], "APPROVED")
        self.assertFalse(fake.calls)

    def test_after_claim_failure_recovery_is_unknown(self):
        fake = FakeTransport(raise_on=RuntimeError("simulated transport failure"))
        coordinator = OfflineExecutionCoordinator(self.store, fake)
        with self.assertRaisesRegex(RuntimeError, "simulated transport failure"):
            coordinator.run(self.permit)
        self.assertEqual(self.store.get("fixture-1")["status"], "RUNNING")
        restarted = ApprovalStore(self.path)
        self.assertEqual(restarted.recover_unknown(), 1)
        self.assertEqual(restarted.get("fixture-1")["status"], "UNKNOWN")
        with self.assertRaisesRegex(ApprovalStateError, "execution_not_approved"):
            coordinator.run(self.permit)
        self.assertEqual(len(fake.calls), 1)

    def test_tampered_db_denied_before_claim(self):
        with self.store._connect() as db:
            commands = json.loads(db.execute(
                "SELECT commands_json FROM ssh_batches WHERE request_id='fixture-1'").fetchone()[0])
            commands[0]["command"] = "bad"
            db.execute("UPDATE ssh_batches SET commands_json=? WHERE request_id='fixture-1'",
                       (json.dumps(commands),))
        fake = FakeTransport()
        with self.assertRaisesRegex(ApprovalStateError, "persisted_batch_digest_changed"):
            OfflineExecutionCoordinator(self.store, fake).run(self.permit)
        self.assertFalse(fake.calls)
        self.assertEqual(self.store.get("fixture-1")["status"], "APPROVED")

    def test_rejects_transport_without_explicit_fixture_marker(self):
        class Untrusted:
            def run_command(self, *args):
                raise AssertionError("should not run")
        with self.assertRaisesRegex(ApprovalStateError, "fixture_transport_required"):
            OfflineExecutionCoordinator(self.store, Untrusted())
        with self.assertRaisesRegex(ApprovalStateError, "real_transport_not_permitted"):
            OfflineExecutionCoordinator(self.store, type("HostTransport", (), {
                "_offline_fixture_transport": True, "hosts": {}, "run_command": lambda *args: None
            })())

    def test_mock_result_oversize_remains_unresolved_not_replayed(self):
        fake = FakeTransport([SSHRunResult(0, "A" * 70000, "", False, False)])
        with self.assertRaisesRegex(ApprovalStateError, "fixture_result_exceeds_limit"):
            OfflineExecutionCoordinator(self.store, fake).run(self.permit)
        self.assertEqual(self.store.get("fixture-1")["status"], "RUNNING")
        self.assertIsNone(self.store.get_mock_result("fixture-1"))


if __name__ == "__main__":
    unittest.main()
