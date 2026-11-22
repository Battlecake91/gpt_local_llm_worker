"""Operator authentication tests. No browser, SSH or LIVE approval is enabled."""
import unittest

from worker.operator_auth import (
    OperatorAuthenticator, OperatorAuthError, OperatorPasswordRecord, OperatorTicket, create_password_record,
)


class OperatorAuthTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.record = create_password_record("local-operator", "local-only-high-entropy-test-passphrase")
        self.auth = OperatorAuthenticator(self.record, clock=lambda: self.now)
        self.binding = dict(
            request_id="live-fixture", command_sha256="a" * 64,
            target_digest="b" * 64, conversation_id="chat-fixture", tab_id=7)

    def test_correct_password_yields_one_use_origin_bound_ticket(self):
        self.assertNotEqual(self.record.password_hash, b"local-only-high-entropy-test-passphrase")
        self.assertEqual(len(self.record.salt), 16)
        ticket = self.auth.verify_for_proposal(
            "local-only-high-entropy-test-passphrase", **self.binding)
        self.assertEqual(self.auth.consume_for_proposal(ticket, **self.binding), "local-operator")
        with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
            self.auth.consume_for_proposal(ticket, **self.binding)

    def test_malformed_credential_record_denied(self):
        with self.assertRaisesRegex(OperatorAuthError, "invalid_credential_record"):
            OperatorPasswordRecord("local-operator", "x" * 16, b"x" * 32)
        with self.assertRaisesRegex(OperatorAuthError, "invalid_credential_record"):
            OperatorPasswordRecord("local-operator", b"x" * 16, "x" * 32)

    def test_eight_character_password_is_accepted(self):
        for secret in ("12345678", "äöüßabcd"):
            with self.subTest(secret_length=len(secret)):
                record = create_password_record("local-operator", secret)
                auth = OperatorAuthenticator(record)
                ticket = auth.verify_for_proposal(secret, **self.binding)
                self.assertEqual(auth.consume_for_proposal(ticket, **self.binding),
                                 "local-operator")

    def test_seven_unicode_characters_are_rejected(self):
        # UTF-8 can exceed 8 bytes even with fewer than 8 characters.
        with self.assertRaisesRegex(OperatorAuthError, "invalid_operator_secret"):
            create_password_record("local-operator", "äöüßabc")

    def test_wrong_password_fails_without_ticket(self):
        with self.assertRaisesRegex(OperatorAuthError, "operator_authentication_failed"):
            self.auth.verify_for_proposal("this-is-wrong-passphrase", **self.binding)

    def test_ticket_bound_to_exact_digest_origin_and_tab(self):
        for field, replacement in (
            ("request_id", "other"), ("command_sha256", "c" * 64),
            ("target_digest", "d" * 64), ("conversation_id", "other"), ("tab_id", 8),
        ):
            with self.subTest(field=field):
                ticket = self.auth.verify_for_proposal(
                    "local-only-high-entropy-test-passphrase", **self.binding)
                changed = dict(self.binding, **{field: replacement})
                with self.assertRaisesRegex(OperatorAuthError, "ticket_binding_mismatch"):
                    self.auth.consume_for_proposal(ticket, **changed)
                with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
                    self.auth.consume_for_proposal(ticket, **self.binding)

    def test_ticket_expires_and_restart_invalidates(self):
        ticket = self.auth.verify_for_proposal(
            "local-only-high-entropy-test-passphrase", **self.binding)
        self.now += 91
        with self.assertRaisesRegex(OperatorAuthError, "ticket_expired"):
            self.auth.consume_for_proposal(ticket, **self.binding)
        new_auth = OperatorAuthenticator(self.record, clock=lambda: self.now)
        with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
            new_auth.consume_for_proposal(ticket, **self.binding)

    def test_rate_limit_five_failures_then_recovery(self):
        for _ in range(5):
            with self.assertRaisesRegex(OperatorAuthError, "operator_authentication_failed"):
                self.auth.verify_for_proposal("wrong-secret-attempt", **self.binding)
        with self.assertRaisesRegex(OperatorAuthError, "operator_temporarily_locked"):
            self.auth.verify_for_proposal(
                "local-only-high-entropy-test-passphrase", **self.binding)
        self.now += 61
        self.assertIsInstance(self.auth.verify_for_proposal(
            "local-only-high-entropy-test-passphrase", **self.binding), OperatorTicket)

    def test_missing_and_invalid_binding_denied(self):
        with self.assertRaisesRegex(OperatorAuthError, "invalid_operator_secret"):
            create_password_record("local-operator", "short")
        with self.assertRaisesRegex(OperatorAuthError, "invalid_tab_id"):
            self.auth.verify_for_proposal(
                "local-only-high-entropy-test-passphrase",
                **dict(self.binding, tab_id=True))
        with self.assertRaisesRegex(OperatorAuthError, "invalid_target_digest"):
            self.auth.verify_for_proposal(
                "local-only-high-entropy-test-passphrase",
                **dict(self.binding, target_digest="bad"))
        with self.assertRaisesRegex(OperatorAuthError, "invalid_operator_ticket"):
            self.auth.consume_for_proposal("not-a-ticket", **self.binding)

    def test_ticket_is_not_reusable_after_failed_origin_match(self):
        ticket = self.auth.verify_for_proposal(
            "local-only-high-entropy-test-passphrase", **self.binding)
        with self.assertRaisesRegex(OperatorAuthError, "ticket_binding_mismatch"):
            self.auth.consume_for_proposal(
                ticket, **dict(self.binding, tab_id=999))
        with self.assertRaisesRegex(OperatorAuthError, "ticket_missing_or_used"):
            self.auth.consume_for_proposal(ticket, **self.binding)


if __name__ == "__main__":
    unittest.main()
