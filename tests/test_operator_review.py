"""Headless tests for explicit full-command LIVE review. No SSH/GUI."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.operator_auth import OperatorAuthError, create_password_record
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_review import OperatorReviewController
from worker.ssh_protocol import parse_ssh_request
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


class FixtureProtector:
    def protect(self, data):
        return bytes(v ^ 0x25 for v in data)

    def unprotect(self, data):
        return self.protect(data)


class OperatorReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.ledger = LiveApprovalLedger(root / "live.sqlite")
        credentials = OperatorCredentialFile(root / "credential.dat", protector=FixtureProtector())
        credentials.create(create_password_record("fixture-user", "fixture-operator-passphrase-123"))
        flow = TrustedOfflineOperatorFlow(credentials, root / "rate.sqlite", self.ledger)
        self.target = LiveTargetBinding(
            "fixture-host", "fixture.example.invalid", 2222,
            "fixtureuser", "ssh-ed25519 SYNTHETIC-PUBLIC-KEY")
        self.batch = parse_ssh_request(json.dumps({
            "schema_version": 1, "kind": "ssh_batch", "request_id": "review-1",
            "target": "fixture-host", "working_directory": "/tmp/testing",
            "description": "exact review fixture",
            "commands": [
                {"id": "a", "command": "printf 'text one'", "timeout_seconds": 3},
                {"id": "b", "command": "printf 'text two'", "timeout_seconds": 7},
            ],
        }), {"fixture-host"})
        self.ledger.propose(self.batch, self.target, tab_id=91, conversation_id="chat-fixture")
        self.controller = OperatorReviewController(
            self.ledger, flow, {"fixture-host": self.target})

    def test_preview_contains_full_commands_and_identity(self):
        review = self.controller.prepare("review-1")
        content = review.render_text()
        for value in ("fixtureuser@fixture.example.invalid:2222",
                      self.target.host_public_key, "printf 'text one'",
                      "printf 'text two'", self.batch.command_sha256,
                      "chat-fixture", "91", "/tmp/testing"):
            self.assertIn(value, content)
        self.assertEqual([c.timeout_seconds for c in review.commands], [3, 7])
        self.assertEqual(self.ledger.get("review-1")["status"], "PROPOSED")

    def test_full_confirmation_and_password_store_audited_approval_only(self):
        review = self.controller.prepare("review-1")
        approval = self.controller.approve(
            review, "fixture-operator-passphrase-123",
            full_batch_confirmed=True, command_sha256=review.command_sha256)
        self.assertTrue(approval.startswith("live-"))
        self.assertEqual(self.ledger.get("review-1")["status"], "APPROVED")
        with self.assertRaisesRegex(LiveAuthorizationError, "live_executor_not_enabled"):
            self.ledger.claim_execution("review-1", approval)

    def test_no_confirmation_never_attempts_password(self):
        review = self.controller.prepare("review-1")
        with self.assertRaisesRegex(LiveAuthorizationError, "explicit_full_batch_confirmation_required"):
            self.controller.approve(
                review, "wrong-password",
                full_batch_confirmed=False, command_sha256=review.command_sha256)
        self.assertEqual(self.ledger.get("review-1")["status"], "PROPOSED")

    def test_wrong_digest_denied(self):
        review = self.controller.prepare("review-1")
        with self.assertRaisesRegex(LiveAuthorizationError, "explicit_full_batch_confirmation_required"):
            self.controller.approve(
                review, "fixture-operator-passphrase-123",
                full_batch_confirmed=True, command_sha256="0" * 64)
        self.assertEqual(self.ledger.get("review-1")["status"], "PROPOSED")

    def test_untrusted_target_config_cannot_be_reviewed(self):
        altered = LiveTargetBinding(
            "fixture-host", "evil.example.invalid", 2222, "fixtureuser",
            self.target.host_public_key)
        ctrl = OperatorReviewController(
            self.ledger, self.controller._flow, {"fixture-host": altered})
        with self.assertRaisesRegex(LiveAuthorizationError, "live_review_target_mismatch"):
            ctrl.prepare("review-1")
        self.assertEqual(self.ledger.get("review-1")["status"], "PROPOSED")

    def test_no_registered_host_denied(self):
        ctrl = OperatorReviewController(self.ledger, self.controller._flow, {})
        with self.assertRaisesRegex(LiveAuthorizationError, "live_review_invalid"):
            ctrl.prepare("review-1")

    def test_tampered_digest_and_payload_denied(self):
        with self.ledger._connect() as db:
            db.execute("DROP TRIGGER live_proposals_identity_immutable")
            db.execute("UPDATE live_proposals SET command_sha256=? WHERE request_id=?",
                       ("0" * 64, "review-1"))
        with self.assertRaisesRegex(LiveAuthorizationError, "live_review_digest_mismatch"):
            self.controller.prepare("review-1")

    def test_changed_state_between_display_and_click_denied(self):
        review = self.controller.prepare("review-1")
        with self.ledger._connect() as db:
            db.execute("UPDATE live_proposals SET status='REJECTED' WHERE request_id='review-1'")
        with self.assertRaisesRegex(LiveAuthorizationError, "live_proposal_not_pending"):
            self.controller.approve(
                review, "fixture-operator-passphrase-123",
                full_batch_confirmed=True, command_sha256=review.command_sha256)

    def test_wrong_password_does_not_approve(self):
        review = self.controller.prepare("review-1")
        with self.assertRaisesRegex(OperatorAuthError, "operator_authentication_failed"):
            self.controller.approve(
                review, "fixture-wrong-password-123",
                full_batch_confirmed=True, command_sha256=review.command_sha256)
        self.assertEqual(self.ledger.get("review-1")["status"], "PROPOSED")


if __name__ == "__main__":
    unittest.main()
