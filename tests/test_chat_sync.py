"""API and persistence tests for phase-one opt-in chat transport."""
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from worker.chat_sync import ChatStore, create_app

EXT = "a" * 32
ORIGIN = "chrome-extension://" + EXT
TOKEN = "test-token-with-at-least-32-chars-1234567"
HEADERS = {"Origin": ORIGIN, "Authorization": "Bearer " + TOKEN}

def fixture():
    return {
        "tab_id": 19,
        "conversation_id": "chat-123",
        "title": "Test Chat",
        "generating": False,
        "messages": [
            {"role": "user", "message_id": "u1",
             "text": "Bitte einen Befehl für NAS", "complete": True},
            {"role": "assistant", "message_id": "a1",
             "text": "```bash\nzpool status\n```", "complete": True}
        ]
    }

def test_roundtrip_and_idempotent_updates():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            assert client.post("/v2/snapshot", json=fixture(), headers=HEADERS).status_code == 200
            assert client.post("/v2/snapshot", json=fixture(), headers=HEADERS).status_code == 200
            chats = store.list()
            assert len(chats) == 1
            assert chats[0]["online"] and chats[0]["conversation_id"] == "chat-123"
            messages = store.messages(19)
            assert len(messages) == 2
            assert messages[1]["text"].startswith("```bash\n")
            assert len(messages[1]["sha256"]) == 64
            changed = fixture()
            changed["messages"][1]["complete"] = False
            changed["generating"] = True
            assert client.post("/v2/snapshot", json=changed, headers=HEADERS).status_code == 200
            assert not store.messages(19)[1]["complete"]
            assert client.delete("/v2/tabs/19", headers=HEADERS).status_code == 200
            assert store.list() == []
            assert store.messages(19) == []

def test_reject_unauthorized_and_untrusted_page():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            assert client.post("/v2/snapshot", json=fixture()).status_code == 401
            # A privileged extension request may omit Origin, but must never
            # bypass the same bearer-token authentication as other requests.
            assert client.get("/v2/health", headers={
                "Authorization": "Bearer " + TOKEN}).status_code == 200
            assert client.get("/v2/health", headers={
                "Authorization": "Bearer wrong"}).status_code == 401
            assert client.post("/v2/snapshot", json=fixture(), headers={
                "Authorization": "Bearer " + TOKEN}).status_code == 200
            assert store.list()[0]["tab_id"] == 19
            store.remove(19)
            assert client.post("/v2/snapshot", json=fixture(),
                               headers={"Origin": "https://chatgpt.com",
                                        "Authorization": "Bearer " + TOKEN}).status_code == 403
            assert client.post("/v2/snapshot", json=fixture(),
                               headers={"Origin": ORIGIN,
                                        "Authorization": "Bearer wrong"}).status_code == 401
            assert store.list() == []

def test_invalid_messages_rejected_without_partial_commit():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            bad = fixture()
            bad["messages"][0]["role"] = "system"
            assert client.post("/v2/snapshot", json=bad, headers=HEADERS).status_code == 422
            bad = fixture()
            bad["messages"][1]["message_id"] = "u1"
            assert client.post("/v2/snapshot", json=bad, headers=HEADERS).status_code == 422
            assert store.list() == []

def test_last_seen_expires_offline():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            assert client.post("/v2/snapshot", json=fixture(), headers=HEADERS).status_code == 200
            with store.connect() as db:
                db.execute("UPDATE chats SET updated_at=? WHERE tab_id=19", (time.time()-110,))
            assert not store.list()[0]["online"]
            with store.connect() as db:
                db.execute("UPDATE chats SET updated_at=? WHERE tab_id=19", (time.time()-250,))
            assert store.list() == []
            assert store.messages(19) == []

def test_multiple_tabs_are_independent():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            first = fixture()
            second = fixture()
            second["tab_id"] = 27
            second["conversation_id"] = "chat-456"
            second["messages"][0]["text"] = "Anderer Chat"
            for body in [first, second]:
                assert client.post("/v2/snapshot", json=body, headers=HEADERS).status_code == 200
            assert len(store.list()) == 2
            assert store.messages(19)[0]["text"] != store.messages(27)[0]["text"]
            assert client.delete("/v2/tabs/19", headers=HEADERS).status_code == 200
            assert len(store.list()) == 1
            assert store.list()[0]["tab_id"] == 27

def test_extension_cors_preflight_allows_authenticated_headers():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            response = client.options("/v2/health", headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            })
            assert response.status_code == 200, response.text
            assert response.headers["access-control-allow-origin"] == ORIGIN
            assert "authorization" in response.headers["access-control-allow-headers"].lower()

            response = client.options("/v2/snapshot", headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            })
            assert response.status_code == 200, response.text

            rejected = client.options("/v2/snapshot", headers={
                "Origin": "https://chatgpt.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization",
            })
            assert rejected.status_code == 400
            assert rejected.headers.get("access-control-allow-origin") != "https://chatgpt.com"

def test_health_returns_configured_extension_id_for_diagnostics():
    with tempfile.TemporaryDirectory() as root:
        store = ChatStore(Path(root) / "chat.db")
        with TestClient(create_app(store, TOKEN, EXT)) as client:
            result = client.get("/v2/health", headers=HEADERS)
            assert result.status_code == 200
            assert result.json() == {"ok": True, "extension_id": EXT}
            denied = client.get("/v2/health", headers={
                "Origin": "chrome-extension://" + "b" * 32,
                "Authorization": "Bearer " + TOKEN})
            assert denied.status_code == 403
