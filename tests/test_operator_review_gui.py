"""Headless tests of the local review launch contract, no Tk window/SSH."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.live_approval import LiveAuthorizationError
from worker.operator_review_gui import load_local_targets, main


class LocalReviewConfigTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "targets.json"
        self.value = {
            "host_id": "fixture", "hostname": "fixture.example.invalid",
            "username": "testuser", "port": 2222,
            "host_public_key": "ssh-ed25519 SYNTHETIC",
        }
        self.path.write_text(json.dumps([self.value]), encoding="utf-8")

    def test_local_config_can_show_ssh_identity(self):
        target = load_local_targets(self.path)["fixture"]
        self.assertEqual(target.hostname, "fixture.example.invalid")
        self.assertEqual(target.username, "testuser")
        self.assertEqual(target.port, 2222)

    def test_duplicate_host_is_rejected(self):
        self.path.write_text(json.dumps([self.value, self.value]), encoding="utf-8")
        with self.assertRaisesRegex(LiveAuthorizationError, "trusted_target_file_invalid"):
            load_local_targets(self.path)

    def test_unknown_target_fields_are_rejected(self):
        self.path.write_text(json.dumps([dict(self.value, secret="unexpected")]), encoding="utf-8")
        with self.assertRaisesRegex(LiveAuthorizationError, "trusted_target_file_invalid"):
            load_local_targets(self.path)

    def test_relative_missing_and_oversize_files_denied(self):
        with self.assertRaisesRegex(LiveAuthorizationError, "trusted_target_file_required"):
            load_local_targets(Path("targets.json"))
        with self.assertRaisesRegex(LiveAuthorizationError, "trusted_target_file_required"):
            load_local_targets(self.path.parent / "missing.json")
        self.path.write_text("x" * 65537, encoding="utf-8")
        with self.assertRaisesRegex(LiveAuthorizationError, "target_file_too_large"):
            load_local_targets(self.path)

    def test_non_object_entries_are_rejected(self):
        self.path.write_text(json.dumps([1]), encoding="utf-8")
        with self.assertRaisesRegex(LiveAuthorizationError, "trusted_target_file_invalid"):
            load_local_targets(self.path)

    def test_missing_local_credential_blocks_gui_launch(self):
        with self.assertRaises(SystemExit) as captured:
            main([
                "--live-db", str(self.path),
                "--credentials", str(self.path.parent / "missing-credential"),
                "--rate-db", str(self.path),
                "--targets", str(self.path),
                "--request-id", "request-test",
            ])
        self.assertEqual(captured.exception.code, 2)

    def test_no_automatic_ui_or_execution_from_module_import(self):
        # Actual Tk startup is only in open_local_review() under explicit main().
        # Verify the parsing contract doesn't need a display server.
        import worker.operator_review_gui as module
        self.assertTrue(callable(module.open_local_review))
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
