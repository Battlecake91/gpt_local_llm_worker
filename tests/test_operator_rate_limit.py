"""Offline persistent lockout tests: no browser, SSH, API, or account enrollment."""
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from worker.operator_auth import OperatorAuthenticator, OperatorAuthError, create_password_record
from worker.operator_rate_limit import PersistentOperatorVerifier


class PersistentOperatorRateLimitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db_path = Path(tmp.name) / "rate-limit.sqlite"
        self.now = 1_800_000_000.0
        self.record = create_password_record("fixture-operator", "correct-offline-test-password-123")
        self.binding = dict(
            request_id="fixture", command_sha256="a" * 64,
            target_digest="b" * 64, conversation_id="chat", tab_id=17)
        self.new_auth = lambda: OperatorAuthenticator(self.record)
        self.new_guard = lambda: PersistentOperatorVerifier(
            self.db_path, self.new_auth(), clock=lambda: self.now)

    def test_failed_attempts_persist_across_restarts(self):
        for i in range(4):
            guard = self.new_guard()
            with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
                guard.verify_for_proposal("incorrect-offline-password", **self.binding)
            self.assertEqual(guard.status()["failed_attempts"], i + 1)
        with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
            self.new_guard().verify_for_proposal(
                "incorrect-offline-password", **self.binding)
        restarted = self.new_guard()
        self.assertEqual(restarted.status()["failed_attempts"], 0)
        self.assertEqual(restarted.status()["locked_until"], self.now + 60)
        with self.assertRaisesRegex(OperatorAuthError, "operator_temporarily_locked"):
            restarted.verify_for_proposal("correct-offline-test-password-123", **self.binding)
        self.now += 61
        self.assertIsNotNone(self.new_guard().verify_for_proposal(
            "correct-offline-test-password-123", **self.binding))
        self.assertEqual(self.new_guard().status()["locked_until"], 0)

    def test_success_resets_failure_counter(self):
        guard = self.new_guard()
        with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
            guard.verify_for_proposal("incorrect-offline-password", **self.binding)
        self.assertEqual(self.new_guard().status()["failed_attempts"], 1)
        self.new_guard().verify_for_proposal("correct-offline-test-password-123", **self.binding)
        self.assertEqual(self.new_guard().status()["failed_attempts"], 0)

    def test_parallel_process_like_instances_share_counter(self):
        def wrong(_):
            try:
                self.new_guard().verify_for_proposal(
                    "incorrect-offline-password", **self.binding)
            except OperatorAuthError as exc:
                return str(exc)
            raise AssertionError("unexpected authentication success")
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(wrong, range(5)))
        self.assertEqual(results, ["operator_authentication_failed"] * 5)
        self.assertEqual(self.new_guard().status()["locked_until"], self.now + 60)

    def test_clock_rollback_fails_closed_after_restart(self):
        guard = self.new_guard()
        guard.verify_for_proposal("correct-offline-test-password-123", **self.binding)
        self.now -= 120
        with self.assertRaisesRegex(OperatorAuthError, "operator_clock_rollback"):
            self.new_guard().verify_for_proposal(
                "correct-offline-test-password-123", **self.binding)

    def test_invalid_request_does_not_reset_failures(self):
        guard = self.new_guard()
        with self.assertRaisesRegex(OperatorAuthError, "authentication_failed"):
            guard.verify_for_proposal("incorrect-offline-password", **self.binding)
        with self.assertRaisesRegex(OperatorAuthError, "invalid_tab_id"):
            guard.verify_for_proposal(
                "correct-offline-test-password-123", **dict(self.binding, tab_id=True))
        self.assertEqual(guard.status()["failed_attempts"], 1)

    def test_bad_database_fails_closed(self):
        guard = self.new_guard()
        with guard._connect() as db:
            db.execute("DROP TABLE operator_login_limits")
        with self.assertRaises(sqlite3.OperationalError):
            guard.verify_for_proposal("correct-offline-test-password-123", **self.binding)

    def test_reject_relative_database_path(self):
        with self.assertRaisesRegex(OperatorAuthError, "rate_limit_path_not_absolute"):
            PersistentOperatorVerifier("rate-limit.sqlite", self.new_auth())

    def test_no_secret_or_ticket_in_sqlite_file(self):
        guard = self.new_guard()
        ticket = guard.verify_for_proposal("correct-offline-test-password-123", **self.binding)
        raw = self.db_path.read_bytes()
        self.assertNotIn(b"correct-offline-test-password-123", raw)
        self.assertNotIn(ticket.token.encode(), raw)
        self.assertNotIn(self.record.password_hash, raw)


if __name__ == "__main__":
    unittest.main()
