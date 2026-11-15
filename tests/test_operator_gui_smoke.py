"""Smoke-fixture tests. The real Tk window is never opened by pytest."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

from worker.live_approval import LiveAuthorizationError


_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "operator-review-gui-smoke.py"
_spec = importlib.util.spec_from_file_location("operator_review_smoke_fixture", _SCRIPT)
_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smoke)


class OperatorGuiSmokeTests(unittest.TestCase):
    def test_fixture_generates_complete_review_without_opening_gui(self):
        with tempfile.TemporaryDirectory(prefix="llm-review-test-") as root:
            controller, ledger = _smoke.prepare_smoke(Path(root))
            review = controller.prepare(_smoke.TEST_REQUEST)
            rendered = review.render_text()
            self.assertIn("fixture.example.invalid", rendered)
            self.assertIn("SYNTHETIC-KEY-NOT-VALID", rendered)
            self.assertIn("printf 'fixture only'", rendered)
            self.assertEqual(review.conversation_id, "offline-fixture-chat-not-real")
            self.assertEqual(ledger.get(_smoke.TEST_REQUEST)["status"], "PROPOSED")
            self.assertEqual(controller._flow.audit_for(_smoke.TEST_REQUEST), [])

    def test_cancel_keeps_proposal_unapproved(self):
        observed = []
        def closed_without_approval(controller, request_id):
            observed.append(controller.prepare(request_id).host_alias)
        _smoke.run_smoke(show_gui=closed_without_approval)
        self.assertEqual(observed, ["offline-fixture"])

    def test_confirm_fixture_writes_only_offline_audit(self):
        observed = []
        def confirm_without_gui(controller, request_id):
            review = controller.prepare(request_id)
            approval = controller.approve(
                review, _smoke.TEST_PASSWORD,
                full_batch_confirmed=True,
                command_sha256=review.command_sha256,
            )
            self.assertTrue(approval.startswith("live-"))
            observed.append(request_id)
            with self.assertRaisesRegex(LiveAuthorizationError, "live_executor_not_enabled"):
                controller._ledger.claim_execution(request_id, approval)
        _smoke.run_smoke(show_gui=confirm_without_gui)
        self.assertEqual(observed, [_smoke.TEST_REQUEST])

    def test_wrong_password_does_not_approve(self):
        def wrong_password(controller, request_id):
            review = controller.prepare(request_id)
            from worker.operator_auth import OperatorAuthError
            with self.assertRaisesRegex(OperatorAuthError, "operator_authentication_failed"):
                controller.approve(
                    review, "wrong-fixture-password-2026",
                    full_batch_confirmed=True,
                    command_sha256=review.command_sha256,
                )
        _smoke.run_smoke(show_gui=wrong_password)


if __name__ == "__main__":
    unittest.main()
