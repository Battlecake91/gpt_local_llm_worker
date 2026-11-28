"""Loopback-only snapshot intake for explicitly enabled, open ChatGPT tabs.

Observation only. No LLM decisions, SSH, browser send, or autonomous actions.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

MAX_MESSAGES = 500
MAX_TEXT = 256_000
MAX_TOTAL = 2_000_000
STALE_SECONDS = 90


class ChatMessage(BaseModel):
    role: str
    message_id: str = Field(min_length=1, max_length=512)
    text: str = Field(max_length=MAX_TEXT)
    complete: bool = False


class ChatSnapshot(BaseModel):
    tab_id: int = Field(gt=0)
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9-]{1,256}$")
    title: str = Field(max_length=200)
    generating: bool
    messages: list[ChatMessage] = Field(max_length=MAX_MESSAGES)


class ChatStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS chats (
                tab_id INTEGER PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                title TEXT NOT NULL,
                generating INTEGER NOT NULL,
                updated_at REAL NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS messages (
                tab_id INTEGER NOT NULL,
                ordinal INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                complete INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                PRIMARY KEY(tab_id, ordinal)
            )""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def put(self, snapshot: ChatSnapshot):
        if sum(len(m.text) for m in snapshot.messages) > MAX_TOTAL:
            raise ValueError("snapshot_too_large")
        if any(m.role not in ("user", "assistant") for m in snapshot.messages):
            raise ValueError("invalid_role")
        ids = [m.message_id for m in snapshot.messages]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate_message_id")
        with self.lock, self.connect() as db:
            db.execute("""INSERT INTO chats VALUES (?,?,?,?,?)
                ON CONFLICT(tab_id) DO UPDATE SET
                conversation_id=excluded.conversation_id,
                title=excluded.title,
                generating=excluded.generating,
                updated_at=excluded.updated_at""",
                (snapshot.tab_id, snapshot.conversation_id,
                 snapshot.title, int(snapshot.generating), time.time()))
            db.execute("DELETE FROM messages WHERE tab_id=?", (snapshot.tab_id,))
            db.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", [
                (snapshot.tab_id, i, m.message_id, m.role, m.text,
                 int(m.complete), hashlib.sha256(m.text.encode("utf-8")).hexdigest())
                for i, m in enumerate(snapshot.messages)
            ])

    def remove(self, tab_id: int):
        with self.lock, self.connect() as db:
            db.execute("DELETE FROM messages WHERE tab_id=?", (tab_id,))
            db.execute("DELETE FROM chats WHERE tab_id=?", (tab_id,))

    def list(self):
        now = time.time()
        with self.lock, self.connect() as db:
            # Expired tabs are not monitored. Remove abandoned snapshots even
            # when the browser was killed before it could send DELETE.
            old = [row[0] for row in db.execute(
                "SELECT tab_id FROM chats WHERE updated_at < ?", (now - 240,))]
            for tab_id in old:
                db.execute("DELETE FROM messages WHERE tab_id=?", (tab_id,))
                db.execute("DELETE FROM chats WHERE tab_id=?", (tab_id,))
            rows = db.execute(
                "SELECT tab_id,conversation_id,title,generating,updated_at "
                "FROM chats ORDER BY updated_at DESC").fetchall()
            return [{"tab_id": r[0], "conversation_id": r[1],
                     "title": r[2], "generating": bool(r[3]),
                     "online": now - r[4] <= STALE_SECONDS,
                     "last_seen_seconds": round(max(0, now-r[4]), 1)}
                    for r in rows]

    def messages(self, tab_id: int):
        with self.lock, self.connect() as db:
            rows = db.execute(
                "SELECT ordinal,message_id,role,text,complete,sha256 "
                "FROM messages WHERE tab_id=? ORDER BY ordinal", (tab_id,)).fetchall()
        return [{"ordinal": r[0], "message_id": r[1], "role": r[2],
                 "text": r[3], "complete": bool(r[4]), "sha256": r[5]}
                for r in rows]


def create_app(store: ChatStore, token: str, extension_id: str) -> FastAPI:
    if len(token) < 32:
        raise ValueError("weak_token")
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        raise ValueError("invalid_extension_id")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    origin = "chrome-extension://" + extension_id

    @app.middleware("http")
    async def require_browser_origin(request, call_next):
        # Browsers supply Origin for extension fetches. Reject web pages.
        if request.headers.get("origin") != origin:
            return JSONResponse({"detail": "invalid_origin"}, status_code=403)
        return await call_next(request)

    def authenticate(authorization: str | None):
        if not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.post("/v2/snapshot")
    def snapshot(body: ChatSnapshot, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        try:
            store.put(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"ok": True}

    @app.delete("/v2/tabs/{tab_id}")
    def remove(tab_id: int, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        store.remove(tab_id)
        return {"ok": True}

    @app.get("/v2/health")
    def health(authorization: str | None = Header(default=None)):
        authenticate(authorization)
        return {"ok": True}

    return app
