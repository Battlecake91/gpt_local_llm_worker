"""No network, no SSH and no live authorization: LIVE staging stays inert."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.ssh_protocol import parse_ssh_request
from worker.approval_state import ApprovalStore


class LiveLedgerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.database = Path(tmp.name) / "approval.sqlite"
        self.ledger = LiveApprovalLedger(self.database)
        self.mock_store = ApprovalStore(self.database)
        self.batch = parse_ssh_request(json.dumps({
            "schema_version": 1, "kind": "ssh_batch", "request_id": "fixture-live",
            "target": "isolated-fixture", "working_directory": "/tmp",
            "description": "Test without SSH",
            "commands": [{"id": "one", "command": "id", "timeout_seconds": 10}]
        }), {"isolated-fixture"})
        self.target = LiveTargetBinding(
            "isolated-fixture", "test.example.invalid", 2222,
            "testuser", "ssh-ed25519 FAKE-KEY-NOT-USED")

    def test_live_proposal_does_not_appear_in_mock_review(self):
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        self.assertEqual(self.ledger.get("fixture-live")["status"], "PROPOSED")
        self.assertEqual(self.mock_store.pending(), [])
        self.assertIsNone(self.mock_store.get("fixture-live"))
        self.assertEqual(self.mock_store.recent_mock_results(), [])

    def test_live_approval_and_execution_are_disabled(self):
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        with self.assertRaisesRegex(LiveAuthorizationError, "authenticator_not_integrated"):
            self.ledger.approve("fixture-live", operator="mock-user")
        with self.assertRaisesRegex(LiveAuthorizationError, "executor_not_enabled"):
            self.ledger.claim_execution("fixture-live", "any")
        self.assertEqual(self.ledger.get("fixture-live")["status"], "PROPOSED")

    def test_idempotence_preserves_target_binding(self):
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        changed = LiveTargetBinding(
            "isolated-fixture", "other.example.invalid", 2222,
            "testuser", "ssh-ed25519 FAKE-KEY-NOT-USED")
        with self.assertRaisesRegex(LiveAuthorizationError, "collision"):
            self.ledger.propose(self.batch, changed, tab_id=7, conversation_id="chat-7")
        with self.assertRaisesRegex(LiveAuthorizationError, "collision"):
            self.ledger.propose(self.batch, self.target, tab_id=8, conversation_id="chat-7")
        self.assertEqual(self.ledger.get("fixture-live")["target_digest"], self.target.digest())

    def test_live_and_mock_ids_are_independent_but_cannot_transfer_approvals(self):
        self.mock_store.propose(self.batch, tab_id=7, conversation_id="chat-7")
        mock_id = self.mock_store.approve("fixture-live",
            command_sha256=self.batch.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        self.assertEqual(self.ledger.get("fixture-live")["status"], "PROPOSED")
        self.assertIsNone(self.ledger.get("fixture-live")["approval_id"])
        self.assertNotEqual(self.mock_store.get("fixture-live")["approval_id"], None)
        with self.assertRaisesRegex(LiveAuthorizationError, "executor_not_enabled"):
            self.ledger.claim_execution("fixture-live", mock_id)

    def test_record_identity_is_immutable_in_sqlite(self):
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "live_proposal_immutable"):
            with self.ledger._connect() as db:
                db.execute("UPDATE live_proposals SET target_digest=? WHERE request_id=?",
                           ("altered", "fixture-live"))
        self.assertEqual(self.ledger.get("fixture-live")["target_digest"], self.target.digest())

    def test_unknown_recovery_never_reexecutes(self):
        self.ledger.propose(self.batch, self.target, tab_id=7, conversation_id="chat-7")
        with self.ledger._connect() as db:
            db.execute("UPDATE live_proposals SET status='RUNNING' WHERE request_id='fixture-live'")
        restarted = LiveApprovalLedger(self.database)
        self.assertEqual(restarted.recover_unknown(), 1)
        self.assertEqual(restarted.get("fixture-live")["status"], "UNKNOWN")
        self.assertEqual(restarted.recover_unknown(), 0)

    def test_target_and_origin_are_checked(self):
        with self.assertRaisesRegex(LiveAuthorizationError, "host_binding_mismatch"):
            self.ledger.propose(self.batch,
                LiveTargetBinding("different", "test.example.invalid", 22, "testuser", "key"),
                tab_id=7, conversation_id="chat-7")
        with self.assertRaisesRegex(LiveAuthorizationError, "invalid_origin"):
            self.ledger.propose(self.batch, self.target, tab_id=0, conversation_id="chat-7")
        with self.assertRaisesRegex(LiveAuthorizationError, "invalid_port"):
            LiveTargetBinding("a", "test.example.invalid", True, "testuser", "key")


if __name__ == "__main__":
    unittest.main()
