"""Offline Ollama classification regressions; no running Ollama or SSH server."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from worker.ollama_analysis import AnalysisError, OllamaAnalyzer, ProfileStore
from worker.live_capture_api import create_app
from worker.live_approval import LiveApprovalLedger


ANSWER = "Auf dem NAS ausführen:\n\n```bash\nzpool status\n```"
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJJ6ml7zbtSC8jwBsz/Pg/3zwvWrLUSK0coMUxgbMKBq"
TOKEN = "offline-ollama-integration-token-2026"
ORIGIN = "chrome-extension://" + "a" * 32


class OllamaPhase1Tests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile_path = self.root / "ollama.json"
        self.profile_path.write_text(json.dumps({
            "active": "local",
            "profiles": [
                {"name": "local", "url": "http://127.0.0.1:11434",
                 "model": "qwen3:4b", "timeout_seconds": 10, "auth_env": None},
                {"name": "nas", "url": "http://nas:11434",
                 "model": "qwen3:4b", "timeout_seconds": 20, "auth_env": None},
            ],
        }), encoding="utf-8")
        self.result = {"actionable": True, "commands": ["zpool status"],
                       "host": "nas", "risk": "green", "reason": "Read-only diagnosis"}
        self.requests = []

    def client(self, *, error=False):
        def handler(request):
            self.requests.append(request)
            if error:
                return httpx.Response(503, text="offline")
            return httpx.Response(200, json={
                "message": {"content": json.dumps(self.result)}
            })
        return httpx.Client(transport=httpx.MockTransport(handler))

    def analyze(self, text=ANSWER):
        return OllamaAnalyzer(ProfileStore(self.profile_path), self.client()).analyze(
            text, {"nas", "backup-nas", "vserver"})

    def test_verbatim_command_and_allowlisted_host(self):
        result = self.analyze()
        self.assertEqual(result.commands, ("zpool status",))
        self.assertEqual(result.host, "nas")
        proposal = result.batch("a" * 64)
        self.assertEqual(proposal.host_id, "nas")
        self.assertEqual(proposal.commands[0].command, "zpool status")
        self.assertTrue(self.requests[0].url.path.endswith("/api/chat"))

    def test_no_shell_block_is_inert_even_if_prose_says_execute(self):
        self.assertIsNone(self.analyze("Auf NAS bitte zpool status ausführen."))
        self.assertEqual(self.requests, [])

    def test_unlabeled_shell_fence_is_extracted(self):
        self.assertEqual(self.analyze(
            "Auf dem NAS ausführen:\n```\nzpool status\n```"
        ).commands, ("zpool status",))

    def test_explicit_terminal_prompt_without_fence(self):
        self.assertEqual(self.analyze(
            "Auf dem NAS ausführen:\n$ zpool status"
        ).commands, ("zpool status",))

    def test_hallucinated_modified_command_is_rejected(self):
        self.result["commands"] = ["zpool destroy storage"]
        with self.assertRaisesRegex(AnalysisError, "command_not_verbatim"):
            self.analyze()

    def test_partial_block_is_rejected(self):
        self.result["commands"] = ["zpool status"]
        with self.assertRaisesRegex(AnalysisError, "command_not_verbatim"):
            self.analyze("Auf NAS:\n```bash\nzpool status\nuptime\n```")

    def test_unknown_host_refused(self):
        self.result["host"] = "invented-host"
        with self.assertRaisesRegex(AnalysisError, "host_not_allowlisted"):
            self.analyze()

    def test_ambiguous_host_never_creates_live_batch(self):
        self.result["host"] = None
        self.assertIsNone(self.analyze().batch("b" * 64))

    def test_model_marks_example_nonactionable(self):
        self.result.update(actionable=False, commands=[])
        self.assertIsNone(self.analyze("Beispiel:\n```bash\nzpool status\n```"))

    def test_failing_ollama_is_fail_closed(self):
        analyzer = OllamaAnalyzer(ProfileStore(self.profile_path), self.client(error=True))
        with self.assertRaisesRegex(AnalysisError, "ollama_unavailable"):
            analyzer.analyze(ANSWER, {"nas"})

    def test_malformed_config_is_rejected(self):
        config = json.loads(self.profile_path.read_text(encoding="utf-8"))
        config["active"] = "not-configured"
        self.profile_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaisesRegex(AnalysisError, "unknown_active"):
            self.analyze()

    def test_switch_profile_without_restarting(self):
        store = ProfileStore(self.profile_path)
        self.assertEqual(store.load()[0]["name"], "local")
        store.select("nas")
        self.assertEqual(store.load()[0]["name"], "nas")
        with self.assertRaisesRegex(AnalysisError, "unknown_profile"):
            store.select("unconfigured")

    def test_model_listing_is_a_read_only_connection_test(self):
        def handler(request):
            self.assertEqual(request.url.path, "/api/tags")
            return httpx.Response(200, json={
                "models": [{"name": "qwen3:4b"}, {"name": "llama3.2:3b"}]
            })
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            analyzer = OllamaAnalyzer(ProfileStore(self.profile_path), client)
            self.assertEqual(analyzer.available_models(), ["qwen3:4b", "llama3.2:3b"])

    def test_multiple_complete_blocks_are_kept_separate(self):
        self.result["commands"] = ["zpool status", "uptime"]
        suggestion = self.analyze(
            "Auf dem NAS ausführen:\n\n```bash\nzpool status\n```\n"
            "\n```bash\nuptime\n```"
        )
        self.assertEqual(suggestion.commands, ("zpool status", "uptime"))

    def test_api_persists_review_only_suggestion_and_no_execution(self):
        targets = self.root / "targets.json"
        targets.write_text(json.dumps([{
            "host_id": "nas", "hostname": "fixture.example.invalid", "port": 22,
            "username": "fixture", "host_public_key": KEY,
        }]), encoding="utf-8")
        db = self.root / "worker.sqlite3"
        with self.client() as fake:
            app = create_app(db_path=db, targets_path=targets, token=TOKEN,
                             extension_origin=ORIGIN, ollama_profiles=self.profile_path,
                             ollama_client=fake)
            with TestClient(app) as api:
                capture = {
                    "schema_version": 1, "message_id": hashlib.sha256(ANSWER.encode()).hexdigest(),
                    "conversation_id": "chat-123", "tab_id": 19, "text": ANSWER,
                    "observed_at": "2026-11-23T14:00:00Z",
                }
                headers = {"Authorization": "Bearer " + TOKEN}
                accepted = api.post("/api/bridge/v1/captures", json=capture, headers=headers)
                self.assertEqual(accepted.status_code, 200, accepted.text)
                proposal = LiveApprovalLedger(db).get("ollama-" + capture["message_id"][:48])
                self.assertEqual(proposal["status"], "PROPOSED")
                self.assertEqual(proposal["conversation_id"], "chat-123")
                listing = api.get("/api/bridge/v1/ollama/suggestions", headers=headers)
                self.assertEqual(listing.json()["items"][0]["risk"], "green")
                self.assertTrue(listing.json()["items"][0]["review_only"])
                self.assertEqual(api.post("/api/bridge/v1/ssh/proposals/" +
                                          "ollama-x/approve", headers=headers).status_code, 404)
                self.assertEqual(api.get("/api/bridge/v1/outbound", headers=headers).json(),
                                 {"items": []})


if __name__ == "__main__":
    unittest.main()
