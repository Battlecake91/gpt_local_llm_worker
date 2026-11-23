"""Explicit CLI LIVE review wiring; no GUI opened and no SSH executed."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.live_approval import LiveApprovalLedger
from worker.live_review_launcher import list_pending, main
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_auth import create_password_record
from worker.operator_rate_limit import PersistentOperatorVerifier
from worker.operator_auth import OperatorAuthenticator
from worker.ssh_protocol import parse_ssh_request
from worker.live_approval import LiveTargetBinding


class LocalReviewLaunchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.state = root / "operator"
        self.state.mkdir()
        self.db = root / "live.sqlite3"
        self.ledger = LiveApprovalLedger(self.db)
        self.target = LiveTargetBinding("nas", "fixture.example.invalid", 22,
                                        "steven", "ssh-ed25519 fixture")
        (self.state / "targets.json").write_text(json.dumps([{
            "host_id": self.target.host_id,
            "hostname": self.target.hostname,
            "port": self.target.port,
            "username": self.target.username,
            "host_public_key": self.target.host_public_key,
        }]), encoding="utf-8")
        credentials = self.state / "operator-credential.json"
        storage = OperatorCredentialFile(credentials)
        storage.create(create_password_record("fixture-operator", "offline-fixture-secret"))
        PersistentOperatorVerifier(self.state / "operator-rate-limit.sqlite3",
                                   OperatorAuthenticator(storage.load()))

    def proposal(self):
        payload = json.dumps({
            "schema_version": 1, "kind": "ssh_batch", "request_id": "fixture-pending",
            "target": "nas", "working_directory": "/tmp",
            "description": "fixture only",
            "commands": [{"id": "one", "command": "printf ok",
                          "timeout_seconds": 5}],
        })
        batch = parse_ssh_request(payload, {"nas"})
        self.ledger.propose(batch, self.target, tab_id=12, conversation_id="fixture-chat")

    def test_list_only_returns_pending_request_ids(self):
        self.proposal()
        self.assertEqual(list_pending(self.ledger),
                         [("fixture-pending", "nas", "fixture-chat")])
        with patch("builtins.print") as output:
            self.assertEqual(main(["--state-dir", str(self.state),
                                   "--live-db", str(self.db), "--list"]), 0)
        self.assertTrue(any(call.args and "fixture-pending" in str(call.args)
                            for call in output.call_args_list))

    def test_review_launches_existing_gui_without_ssh(self):
        self.proposal()
        with patch("worker.live_review_launcher.open_local_review") as gui:
            self.assertEqual(main([
                "--state-dir", str(self.state), "--live-db", str(self.db),
                "--request-id", "fixture-pending"]), 0)
            self.assertEqual(gui.call_count, 1)
            controller, request_id = gui.call_args.args
            self.assertEqual(request_id, "fixture-pending")
            self.assertEqual(controller.prepare(request_id).host_alias, "nas")
        self.assertEqual(self.ledger.get("fixture-pending")["status"], "PROPOSED")

    def test_missing_operator_files_denied(self):
        (self.state / "targets.json").unlink()
        with self.assertRaises(SystemExit) as exc:
            main(["--state-dir", str(self.state),
                  "--live-db", str(self.db), "--list"])
        self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
