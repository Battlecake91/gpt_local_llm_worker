"""Mock-only SSH review API: explicit operator decisions never execute commands."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mock.backend import app, db, approval_store


def ssh_text(request_id="review-1", target="lab-nas"):
    return json.dumps({
        "schema_version": 1, "kind": "ssh_batch", "request_id": request_id,
        "target": target, "working_directory": "/tmp",
        "description": "Nur lesen, keine Änderung",
        "commands": [
            {"id": "sys", "command": "uname -a", "timeout_seconds": 15},
            {"id": "disk", "command": "df -h", "timeout_seconds": 30},
        ],
    })


class ReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = patch.dict(os.environ, {
            "BRIDGE_APPROVAL_DB": str(Path(self.tmp.name) / "approvals.sqlite3"),
            "BRIDGE_ALLOWED_HOSTS": "lab-nas",
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        approval_store.cache_clear()
        self.addCleanup(approval_store.cache_clear)
        db.captures.clear()
        db.outbound.clear()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer mock-test-token"}

    def capture(self, text, message_id="one", conversation_id="chat-1", tab_id=7):
        return self.client.post("/api/bridge/v1/captures", headers=self.headers,
                                json={"schema_version": 1,
                                      "message_id": hashlib.sha256(message_id.encode()).hexdigest(),
                                      "conversation_id": conversation_id,
                                      "tab_id": tab_id,
                                      "text": text,
                                      "observed_at": "2026-11-14T20:00:00Z"})

    def pending(self):
        return self.client.get("/api/bridge/v1/ssh/proposals", headers=self.headers)

    def test_capture_creates_only_allowlisted_immutable_proposal(self):
        self.assertEqual(self.capture(ssh_text()).status_code, 200)
        self.assertEqual(self.capture(ssh_text("nope", "evil"), "two").status_code, 200)
        items = self.pending().json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["host_id"], "lab-nas")
        self.assertEqual(items[0]["working_directory"], "/tmp")
        self.assertEqual([c["timeout_seconds"] for c in items[0]["commands"]], [15, 30])
        self.assertEqual(db.outbound, {})

    def test_unauthed_cannot_list_or_approve(self):
        self.capture(ssh_text())
        item = self.pending().json()["items"][0]
        self.assertEqual(self.client.get("/api/bridge/v1/ssh/proposals").status_code, 401)
        self.assertEqual(self.client.post("/api/bridge/v1/ssh/proposals/review-1/approve",
                                          json=self.decision(item)).status_code, 401)

    def decision(self, item, **overrides):
        return {**{"confirmed": True, "command_sha256": item["command_sha256"],
                   "conversation_id": item["conversation_id"], "tab_id": item["tab_id"]},
                **overrides}

    def test_explicit_decision_is_single_use_and_never_enqueues_result(self):
        self.capture(ssh_text())
        item = self.pending().json()["items"][0]
        url = "/api/bridge/v1/ssh/proposals/review-1/approve"
        self.assertEqual(self.client.post(url, json=self.decision(item, confirmed=False),
                                          headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post(url, json=self.decision(item, command_sha256="0"*64),
                                          headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post(url, json=self.decision(item, tab_id=999),
                                          headers=self.headers).status_code, 409)
        accepted = self.client.post(url, json=self.decision(item), headers=self.headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["status"], "APPROVED_FOR_MOCK_REVIEW")
        self.assertEqual(self.client.post(url, json=self.decision(item),
                                          headers=self.headers).status_code, 409)
        self.assertEqual(self.pending().json()["items"], [])
        self.assertEqual(db.outbound, {})

    def test_rejection_is_terminal(self):
        self.capture(ssh_text())
        item = self.pending().json()["items"][0]
        url = "/api/bridge/v1/ssh/proposals/review-1/reject"
        self.assertEqual(self.client.post(url, json=self.decision(item),
                                          headers=self.headers).status_code, 200)
        self.assertEqual(self.pending().json()["items"], [])
        self.assertEqual(self.client.post(url, json=self.decision(item),
                                          headers=self.headers).status_code, 409)

    def test_request_id_collision_denied(self):
        self.assertEqual(self.capture(ssh_text()).status_code, 200)
        tampered = json.loads(ssh_text())
        tampered["commands"][0]["command"] = "id"
        self.assertEqual(self.capture(json.dumps(tampered), "another").status_code, 409)
        self.assertEqual(self.pending().json()["items"][0]["commands"][0]["command"], "uname -a")

    def test_mock_result_history_is_authenticated_read_only(self):
        from mock.backend import configured_approval_store
        self.assertEqual(self.client.get("/api/bridge/v1/ssh/mock-results").status_code, 401)
        self.assertEqual(self.client.get("/api/bridge/v1/ssh/mock-results",
                                         headers=self.headers).json()["items"], [])
        self.capture(ssh_text())
        proposal = self.pending().json()["items"][0]
        approval = self.client.post(
            "/api/bridge/v1/ssh/proposals/review-1/approve",
            json=self.decision(proposal), headers=self.headers)
        self.assertEqual(approval.status_code, 200)
        store = configured_approval_store()
        state = store.get("review-1")
        store.claim_execution("review-1", state["approval_id"])
        store.finish_mock_execution("review-1", state["approval_id"], {
            "mode": "MOCK_ONLY", "status": "SUCCEEDED",
            "commands": [{"id": "sys", "stdout": "MOCK ONLY"}]})
        response = self.client.get("/api/bridge/v1/ssh/mock-results", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(item["request_id"], "review-1")
        self.assertEqual(item["conversation_id"], "chat-1")
        self.assertEqual(item["result"]["commands"][0]["stdout"], "MOCK ONLY")
        self.assertEqual(store.get("review-1")["status"], "SUCCEEDED")
        self.assertEqual(db.outbound, {})

    def test_review_disabled_by_default(self):
        with patch.dict(os.environ, {"BRIDGE_APPROVAL_DB": "", "BRIDGE_ALLOWED_HOSTS": ""}):
            self.assertEqual(self.pending().json()["items"], [])
            response = self.client.get("/api/bridge/v1/ssh/mock-results", headers=self.headers)
            self.assertEqual(response.status_code, 503)
            self.assertIn("not configured", response.json()["detail"])
            self.assertEqual(self.capture(ssh_text()).status_code, 200)


if __name__ == "__main__":
    unittest.main()
