"""Local offline setup tests, no real operator password or SSH."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.operator_auth import OperatorAuthError
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_setup import OperatorSetupError, enroll_operator, main


class OperatorSetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name) / "private-operator"
        self.password = "fixture-only-operator-secret-2026"

    def test_enrollment_creates_reusable_verifier_and_rate_database(self):
        credential_path, rate_path = enroll_operator(
            self.directory, "fixture-operator", self.password, self.password)
        self.assertTrue(credential_path.is_file())
        self.assertTrue(rate_path.is_file())
        self.assertEqual(
            OperatorCredentialFile(credential_path).load().operator_id,
            "fixture-operator")
        self.assertNotIn(self.password.encode(), credential_path.read_bytes())
        self.assertNotIn(self.password.encode(), rate_path.read_bytes())

    def test_reenrollment_refuses_to_overwrite_credentials(self):
        credential_path, _ = enroll_operator(
            self.directory, "fixture-operator", self.password, self.password)
        before = credential_path.read_bytes()
        with self.assertRaisesRegex(OperatorSetupError, "already_configured"):
            enroll_operator(self.directory, "fixture-operator", self.password, self.password)
        self.assertEqual(credential_path.read_bytes(), before)

    def test_mismatched_password_creates_no_files(self):
        with self.assertRaisesRegex(OperatorSetupError, "confirmation_mismatch"):
            enroll_operator(self.directory, "fixture-operator",
                            self.password, "not-matching-secret")
        self.assertFalse(self.directory.exists())

    def test_short_password_creates_no_files(self):
        with self.assertRaisesRegex(OperatorAuthError, "invalid_operator_secret"):
            enroll_operator(self.directory, "fixture-operator", "short", "short")
        self.assertFalse(self.directory.exists())

    def test_relative_path_is_denied(self):
        with self.assertRaisesRegex(OperatorSetupError, "invalid_state_directory"):
            enroll_operator(Path("relative"), "fixture-operator", self.password, self.password)

    def test_existing_rate_limit_database_denies_enrollment(self):
        self.directory.mkdir()
        (self.directory / "operator-rate-limit.sqlite3").write_bytes(b"do-not-replace")
        with self.assertRaisesRegex(OperatorSetupError, "already_configured"):
            enroll_operator(self.directory, "fixture-operator", self.password, self.password)
        self.assertEqual(
            (self.directory / "operator-rate-limit.sqlite3").read_bytes(), b"do-not-replace")

    def test_cli_requires_interactive_terminal(self):
        with patch("worker.operator_setup.sys.stdin.isatty", return_value=False):
            with self.assertRaises(SystemExit) as ctx:
                main(["--state-dir", str(self.directory),
                      "--operator-id", "fixture-operator"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertFalse(self.directory.exists())

    def test_cli_password_is_prompted_not_passed_as_argument(self):
        with patch("worker.operator_setup.sys.stdin.isatty", return_value=True), \
             patch("worker.operator_setup.getpass.getpass",
                   side_effect=[self.password, self.password]):
            self.assertEqual(main(["--state-dir", str(self.directory),
                                   "--operator-id", "fixture-operator"]), 0)
        self.assertTrue((self.directory / "operator-credential.json").exists())


if __name__ == "__main__":
    unittest.main()
