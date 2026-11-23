"""Opt-in LIVE API contract: authenticated intake, no remote execution."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from worker.live_approval import LiveApprovalLedger
from worker.live_capture_api import create_app
from worker.operator_hosts import parse_public_host_key


# Pure fixture key: no private keys, hosts, browser, or network operations.
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJJ6ml7zbtSC8jwBsz/Pg/3zwvWrLUSK0coMUxgbMKBq"
ORIGIN = "chrome-extension://" + "a" * 32
TOKEN = "offline-integration-fixture-token-2026"


class LiveCaptureAPITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / "live.sqlite3"
        self.targets = root / "targets.json"
        self.targets.write_text(json.dumps([{
            "host_id": "nas", "hostname": "fixture.example.invalid",
            "port": 22, "username": "steven", "host_public_key": KEY,
        }]), encoding="utf-8")
        self.app = create_app(db_path=self.db, targets_path=self.targets,
                              token=TOKEN, extension_origin=ORIGIN)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.auth = {"Authorization": "Bearer " + TOKEN}

    def data(self, *, request_id="live-001", target="nas",
             command="printf fixture", message_id=None):
        text = json.dumps({
            "schema_version": 1, "kind": "ssh_batch",
            "request_id": request_id, "target": target,
            "working_directory": "/tmp", "description": "fixture only",
            "commands": [{"id": "one", "command": command,
                          "timeout_seconds": 5}],
        })
        return {
            "schema_version": 1,
            "message_id": message_id or hashlib.sha256(text.encode()).hexdigest(),
            "conversation_id": "chat-fixture", "tab_id": 17,
            "observed_at": "2026-11-23T00:00:00Z", "text": text,
        }

    def post(self, data, headers=None):
        return self.client.post("/api/bridge/v1/captures", json=data,
                                headers=self.auth if headers is None else headers)

    def test_capture_persists_live_proposal_and_exact_origin(self):
        data = self.data()
        self.assertEqual(self.post(data).status_code, 200)
        row = LiveApprovalLedger(self.db).get("live-001")
        self.assertEqual(row["status"], "PROPOSED")
        self.assertEqual(row["conversation_id"], "chat-fixture")
        self.assertEqual(row["tab_id"], 17)
        self.assertEqual(row["host_id"], "nas")

    def test_identical_capture_is_idempotent(self):
        data = self.data()
        self.assertEqual(self.post(data).json()["status"], "accepted")
        self.assertEqual(self.post(data).json()["status"], "duplicate")

    def test_capture_id_collision_fails_closed(self):
        data = self.data()
        self.assertEqual(self.post(data).status_code, 200)
        altered = dict(data, text="different text")
        self.assertEqual(self.post(altered).status_code, 409)
        self.assertEqual(LiveApprovalLedger(self.db).get("live-001")["status"],
                         "PROPOSED")

    def test_same_request_id_different_command_refused(self):
        one = self.data()
        two = self.data(command="printf changed")
        self.assertEqual(self.post(one).status_code, 200)
        self.assertEqual(self.post(two).status_code, 409)
        self.assertEqual(LiveApprovalLedger(self.db).get("live-001")["status"],
                         "PROPOSED")

    def test_nonssh_text_captured_but_no_live_proposal(self):
        data = dict(self.data(), text="Hello, no SSH request")
        self.assertEqual(self.post(data).status_code, 200)
        self.assertIsNone(LiveApprovalLedger(self.db).get("live-001"))

    def test_unknown_host_cannot_create_proposal(self):
        data = self.data(target="unknown")
        self.assertEqual(self.post(data).status_code, 200)
        self.assertIsNone(LiveApprovalLedger(self.db).get("live-001"))

    def test_authentication_and_readonly_listing(self):
        data = self.data()
        self.assertEqual(self.post(data, headers={}).status_code, 401)
        self.assertEqual(self.post(data).status_code, 200)
        path = "/api/bridge/v1/ssh/proposals"
        self.assertEqual(self.client.get(path).status_code, 401)
        response = self.client.get(path, headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)
        self.assertEqual(response.json()["items"][0]["status"], "PROPOSED")
        self.assertEqual(self.client.post(
            path + "/live-001/approve", headers=self.auth,
            json={}).status_code, 404)
        self.assertEqual(self.client.post(
            path + "/live-001/reject", headers=self.auth,
            json={}).status_code, 404)

    def test_no_outbound_or_execution_routes(self):
        self.assertEqual(self.client.get("/api/bridge/v1/outbound",
                                         headers=self.auth).json(), {"items": []})
        self.assertEqual(self.client.post(
            "/api/bridge/v1/outbound/job/claim",
            headers=self.auth, json={}).status_code, 404)

    def test_weak_or_mock_token_and_unscoped_origin_denied(self):
        for token, origin in (
            ("mock-test-token", ORIGIN),
            ("short", ORIGIN),
            (TOKEN, "*"),
        ):
            with self.subTest(token=token, origin=origin):
                with self.assertRaises(ValueError):
                    create_app(db_path=self.db, targets_path=self.targets,
                               token=token, extension_origin=origin)


if __name__ == "__main__":
    unittest.main()
