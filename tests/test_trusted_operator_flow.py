"""End-to-end offline operator workflow. No SSH, browser or HTTP."""
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from worker.approval_state import ApprovalStore
from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.operator_auth import OperatorAuthError, create_password_record
from worker.operator_credentials import OperatorCredentialFile, CredentialStorageError
from worker.operator_rate_limit import PersistentOperatorVerifier
from worker.ssh_protocol import parse_ssh_request
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


class OfflineProtector:
    def protect(self, value):
        return bytes(byte ^ 0x5A for byte in value)

    def unprotect(self, value):
        return self.protect(value)


class TrustedOperatorFlowTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.credential_path = root / "credential.json"
        self.credential = OperatorCredentialFile(
            self.credential_path, protector=OfflineProtector())
        self.credential.create(create_password_record(
            "offline-operator", "a-local-offline-testing-password-123"))
        self.rate_path = root / "throttle.sqlite"
        self.live_path = root / "live.sqlite"
        self.ledger = LiveApprovalLedger(self.live_path)
        self.mock = ApprovalStore(self.live_path)
        self.batch = parse_ssh_request(json.dumps({
            "schema_version": 1, "kind": "ssh_batch",
            "request_id": "offline-test-1", "target": "offline-host",
            "working_directory": "/tmp", "description": "Offline fixture only",
            "commands": [{"id": "one", "command": "id", "timeout_seconds": 4}]
        }), {"offline-host"})
        self.target = LiveTargetBinding(
            "offline-host", "offline.example.invalid", 2222,
            "offline-user", "not-a-real-public-key")
        self.ledger.propose(
            self.batch, self.target, tab_id=11, conversation_id="fixture-chat")
        self.now = 1_800_000_000.0

    def flow(self):
        return TrustedOfflineOperatorFlow(
            self.credential, self.rate_path, LiveApprovalLedger(self.live_path),
            clock=lambda: self.now)

    def test_password_to_approval_and_audit_without_execution(self):
        flow = self.flow()
        approved_id = flow.approve(
            "offline-test-1", "a-local-offline-testing-password-123")
        self.assertTrue(approved_id.startswith("live-"))
        self.assertEqual(self.ledger.get("offline-test-1")["approval_id"], approved_id)
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "APPROVED")
        self.assertEqual(len(flow.audit_for("offline-test-1")), 1)
        self.assertEqual(flow.audit_for("offline-test-1")[0]["operator_id"], "offline-operator")
        self.assertEqual(self.mock.pending(), [])
        with self.assertRaisesRegex(LiveAuthorizationError, "live_executor_not_enabled"):
            self.ledger.claim_execution("offline-test-1", approved_id)

    def test_five_wrong_passwords_lock_out_after_restart(self):
        for _ in range(5):
            with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
                self.flow().approve("offline-test-1", "wrong-test-password-123")
        with self.assertRaisesRegex(OperatorAuthError, "operator_temporarily_locked"):
            self.flow().approve("offline-test-1", "a-local-offline-testing-password-123")
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "PROPOSED")
        self.assertEqual(self.flow().audit_for("offline-test-1"), [])
        self.now += 61
        self.assertTrue(self.flow().approve(
            "offline-test-1", "a-local-offline-testing-password-123").startswith("live-"))

    def test_mock_approval_never_unlocks_live_approval(self):
        self.mock.propose(
            self.batch, tab_id=11, conversation_id="fixture-chat")
        mock_approval = self.mock.approve(
            "offline-test-1", command_sha256=self.batch.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
            self.flow().approve("offline-test-1", mock_approval)
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "PROPOSED")
        self.assertEqual(self.flow().audit_for("offline-test-1"), [])

    def test_missing_credential_blocks_construction(self):
        self.credential_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.flow()
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "PROPOSED")

    def test_wrong_target_binding_cannot_be_supplied_by_caller(self):
        flow = self.flow()
        with self.assertRaises(TypeError):
            flow.approve(
                "offline-test-1", "a-local-offline-testing-password-123",
                target_digest="c" * 64)
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "PROPOSED")

    def test_duplicate_approval_does_not_create_second_audit(self):
        flow = self.flow()
        flow.approve("offline-test-1", "a-local-offline-testing-password-123")
        with self.assertRaisesRegex(LiveAuthorizationError, "live_proposal_not_pending"):
            self.flow().approve("offline-test-1", "a-local-offline-testing-password-123")
        self.assertEqual(len(flow.audit_for("offline-test-1")), 1)

    def test_corrupt_throttle_database_denies_approval(self):
        flow = self.flow()
        # sqlite3 connection context commits but does not close on Windows.
        with closing(sqlite3.connect(self.rate_path)) as db, db:
            db.execute("DROP TABLE operator_login_limits")
        with self.assertRaises(sqlite3.OperationalError):
            flow.approve("offline-test-1", "a-local-offline-testing-password-123")
        self.assertEqual(self.ledger.get("offline-test-1")["status"], "PROPOSED")


if __name__ == "__main__":
    unittest.main()
