"""Offline mock executor contract tests. Never touches SSH or subprocess."""
import json
import tempfile
import unittest
from pathlib import Path

from worker.approval_state import ApprovalStateError, ApprovalStore
from worker.mock_executor import FixtureReply, MockHost, MockSSHExecutor
from worker.ssh_protocol import parse_ssh_request

HOST_PIN = "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class MockExecutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "approvals.sqlite"
        self.store = ApprovalStore(self.path)
        text = json.dumps({
            "schema_version": 1, "kind": "ssh_batch", "request_id": "job-1",
            "target": "lab-nas", "working_directory": "/tmp",
            "description": "read-only fixture",
            "commands": [
                {"id": "one", "command": "uname -a", "timeout_seconds": 5},
                {"id": "two", "command": "id", "timeout_seconds": 10},
            ],
        })
        self.batch = parse_ssh_request(text, {"lab-nas"})
        self.store.propose(self.batch, tab_id=7, conversation_id="chat-1")
        self.approval_id = self.store.approve(
            self.batch.request_id, command_sha256=self.batch.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        self.executor = MockSSHExecutor(
            self.store, {"lab-nas": MockHost("lab-nas", "mockuser", HOST_PIN)})

    def execute(self, fixtures=None):
        return self.executor.execute("job-1", self.approval_id,
                                     command_sha256=self.batch.command_sha256,
                                     fixtures=fixtures or {
                                         "one": FixtureReply(stdout="Linux mock\n"),
                                         "two": FixtureReply(stdout="uid=1000(mockuser)\n"),
                                     })

    def test_success_is_persisted_and_cannot_replay(self):
        result = self.execute()
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["mode"], "MOCK_ONLY")
        self.assertEqual([x["exit_code"] for x in result["commands"]], [0, 0])
        self.assertEqual(self.store.get("job-1")["status"], "SUCCEEDED")
        self.assertEqual(self.store.get_mock_result("job-1"), result)
        with self.assertRaisesRegex(ApprovalStateError, "mock_execution_denied"):
            self.execute()

    def test_first_nonzero_exit_stops_block(self):
        result = self.execute({
            "one": FixtureReply(exit_code=2, stderr="failure"),
            "two": FixtureReply(stdout="must never be stored"),
        })
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(len(result["commands"]), 1)
        self.assertEqual(result["commands"][0]["stderr"], "failure")

    def test_timeout_flag_stops_block(self):
        result = self.execute({
            "one": FixtureReply(exit_code=None, timed_out=True),
            "two": FixtureReply(),
        })
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(result["commands"][0]["timed_out"])
        self.assertEqual(result["commands"][0]["timeout_seconds"], 5)
        self.assertEqual(len(result["commands"]), 1)

    def test_utf8_output_is_limited_without_breaking_codepoints(self):
        executor = MockSSHExecutor(
            self.store, {"lab-nas": MockHost("lab-nas", "mockuser", HOST_PIN)},
            max_output_bytes=5)
        result = executor.execute(
            "job-1", self.approval_id,
            command_sha256=self.batch.command_sha256,
            fixtures={"one": FixtureReply(stdout="éééé"), "two": FixtureReply()})
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["commands"][0]["stdout"], "éé")
        self.assertTrue(result["commands"][0]["truncated"])
        self.assertLessEqual(len(result["commands"][0]["stdout"].encode("utf-8")), 5)

    def test_wrong_digest_and_approval_do_not_consume_job(self):
        with self.assertRaisesRegex(ApprovalStateError, "mock_digest_mismatch"):
            self.executor.execute("job-1", self.approval_id,
                                  command_sha256="a"*64, fixtures={})
        with self.assertRaisesRegex(ApprovalStateError, "mock_execution_denied"):
            self.executor.execute("job-1", "wrong",
                                  command_sha256=self.batch.command_sha256, fixtures={})
        self.assertEqual(self.store.get("job-1")["status"], "APPROVED")

    def test_missing_host_or_fixtures_denied_without_claim(self):
        empty = MockSSHExecutor(self.store, {})
        with self.assertRaisesRegex(ApprovalStateError, "mock_host_not_configured"):
            empty.execute("job-1", self.approval_id,
                          command_sha256=self.batch.command_sha256, fixtures={})
        with self.assertRaisesRegex(ValueError, "mock_fixture_mismatch"):
            self.executor.execute("job-1", self.approval_id,
                                  command_sha256=self.batch.command_sha256, fixtures={})
        self.assertEqual(self.store.get("job-1")["status"], "APPROVED")

    def test_restart_recovers_running_as_unknown_and_blocks_second_execution(self):
        self.store.claim_execution("job-1", self.approval_id)
        restarted = ApprovalStore(self.path)
        self.assertEqual(restarted.recover_unknown(), 1)
        self.assertEqual(restarted.get("job-1")["status"], "UNKNOWN")
        self.assertIsNone(restarted.get_mock_result("job-1"))
        with self.assertRaisesRegex(ApprovalStateError, "mock_execution_denied"):
            self.execute()

    def test_result_cannot_be_replaced_after_completion(self):
        self.execute()
        with self.assertRaisesRegex(ApprovalStateError, "mock_completion_denied"):
            self.store.finish_mock_execution("job-1", self.approval_id,
                                             {"status": "FAILED"})
        self.assertEqual(self.store.get("job-1")["status"], "SUCCEEDED")

    def test_result_bound_to_approved_origin(self):
        item = self.store.get("job-1")
        self.assertEqual(item["tab_id"], 7)
        self.assertEqual(item["conversation_id"], "chat-1")
        result = self.execute()
        self.assertEqual(result["request_id"], "job-1")

    def test_host_pin_and_username_must_be_explicit(self):
        with self.assertRaisesRegex(ValueError, "invalid_mock_hostkey_pin"):
            MockHost("lab-nas", "mockuser", "")
        with self.assertRaisesRegex(ValueError, "invalid_mock_username"):
            MockHost("lab-nas", "root user", HOST_PIN)
        with self.assertRaisesRegex(ValueError, "mock_host_alias_mismatch"):
            MockSSHExecutor(self.store, {"wrong": MockHost("lab-nas", "mockuser", HOST_PIN)})

    def test_unapproved_or_rejected_cannot_execute(self):
        self.store.propose(
            parse_ssh_request(json.dumps({
                "schema_version": 1, "kind": "ssh_batch", "request_id": "job-2",
                "target": "lab-nas", "working_directory": "/tmp",
                "description": "none", "commands": [
                    {"id": "one", "command": "id", "timeout_seconds": 5},
                ]}), {"lab-nas"}), tab_id=7, conversation_id="chat-1")
        with self.assertRaisesRegex(ApprovalStateError, "mock_execution_denied"):
            self.executor.execute("job-2", self.approval_id,
                                  command_sha256="a"*64, fixtures={"one": FixtureReply()})


if __name__ == "__main__":
    unittest.main()
