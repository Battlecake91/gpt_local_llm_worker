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

    def test_successful_callback_never_queries_destroyed_tk_application(self):
        """Regression: Python 3.13 raises TclError for winfo after destroy."""
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock

        events = []
        buttons = []

        class FakeWidget:
            def __init__(self, *args, **kwargs):
                self.command = kwargs.get("command")
                self.text = kwargs.get("text", "")
                if self.text == "LIVE-Batch freigeben":
                    buttons.append(self)

            def pack(self, **kwargs):
                return None

            def insert(self, *args):
                return None

            def configure(self, **kwargs):
                if "command" in kwargs:
                    self.command = kwargs["command"]
                return None

            def focus_set(self):
                return None

            def get(self):
                return "fixture-only-password"

            def delete(self, *args):
                events.append("password_cleared")

        class FakeRoot(FakeWidget):
            destroyed = False

            def title(self, *args):
                return None

            def geometry(self, *args):
                return None

            def minsize(self, *args):
                return None

            def destroy(self):
                self.destroyed = True
                events.append("destroyed")

            def winfo_exists(self):
                if self.destroyed:
                    raise RuntimeError("Tk accessed after destroy")
                return True

            def mainloop(self):
                self.assert_has_button()
                buttons[0].command()

            def assert_has_button(self):
                if len(buttons) != 1:
                    raise AssertionError("expected exactly one approve button")

        class FakeVar:
            def __init__(self, value=None):
                self.value = True if value is False else value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        tk = SimpleNamespace(Tk=FakeRoot, BooleanVar=FakeVar, StringVar=FakeVar,
                             END="end")
        ttk = SimpleNamespace(Frame=FakeWidget, Label=FakeWidget,
                              Checkbutton=FakeWidget, Entry=FakeWidget,
                              Button=FakeWidget)
        messagebox = SimpleNamespace(
            showinfo=lambda *args, **kwargs: events.append("success_popup"),
            showerror=lambda *args, **kwargs: events.append("error_popup"),
            showwarning=lambda *args, **kwargs: events.append("warning_popup"),
        )
        scrolledtext = SimpleNamespace(ScrolledText=FakeWidget)
        tk.ttk, tk.messagebox, tk.scrolledtext = ttk, messagebox, scrolledtext
        review = Mock(command_sha256="a" * 64)
        review.render_text.return_value = "fixture review only"
        controller = Mock()
        controller.prepare.return_value = review
        controller.approve.return_value = "live-fixture-approval"

        from worker.operator_review_gui import open_local_review
        with patch.dict(sys.modules, {
            "tkinter": tk, "tkinter.ttk": ttk,
            "tkinter.messagebox": messagebox,
            "tkinter.scrolledtext": scrolledtext,
        }):
            open_local_review(controller, "fixture-request")

        controller.approve.assert_called_once()
        self.assertIn("success_popup", events)
        self.assertNotIn("error_popup", events)
        self.assertLess(events.index("password_cleared"), events.index("destroyed"))


if __name__ == "__main__":
    unittest.main()
