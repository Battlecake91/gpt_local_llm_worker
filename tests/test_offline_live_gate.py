"""Offline gate tests: no SSH, HTTP, browser or external credentials."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.offline_live_gate import OfflineLiveApprovalGate
from worker.operator_auth import OperatorAuthError, OperatorAuthenticator, create_password_record
from worker.ssh_protocol import parse_ssh_request
from worker.approval_state import ApprovalStore, ApprovalStateError


class OfflineLiveGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "gates.sqlite"
        self.ledger = LiveApprovalLedger(self.path)
        self.mock = ApprovalStore(self.path)
        self.batch = parse_ssh_request(json.dumps({
            "schema_version": 1, "kind": "ssh_batch", "request_id": "live-fixture-1",
            "target": "fake-host", "working_directory": "/tmp", "description": "No SSH",
            "commands": [{"id": "only", "command": "id", "timeout_seconds": 10}]
        }), {"fake-host"})
        self.target = LiveTargetBinding(
            "fake-host", "host.example.invalid", 2222, "localtest", "not-an-actual-ssh-key")
        self.ledger.propose(self.batch, self.target, tab_id=9, conversation_id="chat-fixture")
        self.auth = OperatorAuthenticator(
            create_password_record("operator-fixture", "offline-only-test-passphrase-123"))
        self.gate = OfflineLiveApprovalGate(self.ledger, self.auth)
        self.binding = {
            "request_id": self.batch.request_id,
            "command_sha256": self.batch.command_sha256,
            "target_digest": self.target.digest(),
            "conversation_id": "chat-fixture",
            "tab_id": 9,
        }

    def ticket(self):
        return self.auth.verify_for_proposal("offline-only-test-passphrase-123", **self.binding)

    def test_ticket_grants_single_audited_live_approval_without_execution(self):
        approval_id = self.gate.approve_with_ticket("live-fixture-1", self.ticket())
        row = self.ledger.get("live-fixture-1")
        self.assertEqual(row["status"], "APPROVED")
        self.assertEqual(row["approval_id"], approval_id)
        self.assertEqual(row["approved_by"], "operator-fixture")
        self.assertEqual(row["approved_via"], "operator_ticket")
        audit = self.gate.audit_for("live-fixture-1")
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["command_sha256"], self.batch.command_sha256)
        self.assertEqual(audit[0]["target_digest"], self.target.digest())
        self.assertEqual(self.mock.pending(), [])
        self.assertEqual(self.mock.recent_mock_results(), [])
        with self.assertRaisesRegex(LiveAuthorizationError, "live_executor_not_enabled"):
            self.ledger.claim_execution("live-fixture-1", approval_id)

    def test_approval_requires_ticket_and_cannot_repeat(self):
        with self.assertRaises(OperatorAuthError):
            self.gate.approve_with_ticket("live-fixture-1", None)
        ticket = self.ticket()
        self.gate.approve_with_ticket("live-fixture-1", ticket)
        with self.assertRaisesRegex(LiveAuthorizationError, "live_proposal_not_pending"):
            self.gate.approve_with_ticket("live-fixture-1", ticket)
        self.assertEqual(len(self.gate.audit_for("live-fixture-1")), 1)

    def test_wrong_chat_ticket_is_burned(self):
        ticket = self.auth.verify_for_proposal(
            "offline-only-test-passphrase-123", **dict(self.binding, conversation_id="other"))
        with self.assertRaisesRegex(OperatorAuthError, "ticket_binding_mismatch"):
            self.gate.approve_with_ticket("live-fixture-1", ticket)
        with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
            self.gate.approve_with_ticket("live-fixture-1", ticket)
        self.assertEqual(self.ledger.get("live-fixture-1")["status"], "PROPOSED")
        self.assertEqual(self.gate.audit_for("live-fixture-1"), [])

    def test_mock_approval_id_is_not_live_operator_ticket(self):
        self.mock.propose(self.batch, tab_id=9, conversation_id="chat-fixture")
        mock_approval = self.mock.approve(
            "live-fixture-1", command_sha256=self.batch.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        with self.assertRaises(OperatorAuthError):
            self.gate.approve_with_ticket("live-fixture-1", mock_approval)
        self.assertEqual(self.ledger.get("live-fixture-1")["status"], "PROPOSED")

    def test_db_failure_rolls_back_approval_and_burns_ticket(self):
        ticket = self.ticket()
        with self.ledger._connect() as db:
            db.execute("""
                CREATE TRIGGER audit_force_failure
                BEFORE INSERT ON live_approval_audit
                BEGIN SELECT RAISE(ABORT, 'test_audit_failure'); END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "test_audit_failure"):
            self.gate.approve_with_ticket("live-fixture-1", ticket)
        self.assertEqual(self.ledger.get("live-fixture-1")["status"], "PROPOSED")
        self.assertIsNone(self.ledger.get("live-fixture-1")["approval_id"])
        self.assertEqual(self.gate.audit_for("live-fixture-1"), [])
        with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
            self.gate.approve_with_ticket("live-fixture-1", ticket)

    def test_audit_rows_cannot_be_mutated_or_deleted(self):
        self.gate.approve_with_ticket("live-fixture-1", self.ticket())
        for stmt in (
            "DELETE FROM live_approval_audit",
            "UPDATE live_approval_audit SET operator_id='fake'",
        ):
            with self.subTest(stmt=stmt):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "audit_immutable"):
                    with self.ledger._connect() as db:
                        db.execute(stmt)
        self.assertEqual(len(self.gate.audit_for("live-fixture-1")), 1)

    def test_tampered_proposal_rejected_without_consuming_ticket(self):
        with self.ledger._connect() as db:
            db.execute("DROP TRIGGER live_proposals_identity_immutable")
            db.execute("UPDATE live_proposals SET command_sha256=? WHERE request_id=?",
                       ("0" * 64, "live-fixture-1"))
        with self.assertRaisesRegex(LiveAuthorizationError, "live_proposal_digest_mismatch"):
            self.gate.approve_with_ticket("live-fixture-1", self.ticket())
        self.assertEqual(self.ledger.get("live-fixture-1")["status"], "PROPOSED")
        self.assertEqual(self.gate.audit_for("live-fixture-1"), [])

    def test_plain_ledger_approve_remains_disabled(self):
        with self.assertRaisesRegex(LiveAuthorizationError, "live_authenticator_not_integrated"):
            self.ledger.approve("live-fixture-1")
        with self.assertRaisesRegex(LiveAuthorizationError, "live_executor_not_enabled"):
            self.ledger.claim_execution("live-fixture-1", "anything")


if __name__ == "__main__":
    unittest.main()
