"""Opt-in loopback LIVE proposal intake, without authorization or execution.

Compatible with the MV3 capture protocol. Does not provide approve/reject,
outbound, SSH command execution, or browser auto-send capabilities.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from worker.live_approval import LiveApprovalLedger
from worker.operator_review_gui import load_local_targets
from worker.ssh_protocol import InvalidSSHRequest, parse_ssh_request

MAX_CAPTURE_TEXT = 256_000
MAX_CONVERSATION_ID = 256


class Capture(BaseModel):
    schema_version: int
    message_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversation_id: str
    tab_id: int
    text: str
    observed_at: str


def create_app(*, db_path: Path, targets_path: Path, token: str,
               extension_origin: str) -> FastAPI:
    """Construct a separately configured instance; never auto-enable from mock."""
    if not db_path.is_absolute() or db_path.is_symlink() or not db_path.parent.is_dir():
        raise ValueError("invalid_live_db_path")
    if not targets_path.is_absolute() or targets_path.is_symlink():
        raise ValueError("invalid_targets_path")
    if not isinstance(token, str) or len(token) < 32 or token == "mock-test-token":
        raise ValueError("strong_live_token_required")
    if not re.fullmatch(r"chrome-extension://[a-p]{32}", extension_origin):
        raise ValueError("explicit_extension_origin_required")

    targets = load_local_targets(targets_path)
    ledger = LiveApprovalLedger(db_path)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS live_captures (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )
        """)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=[extension_origin],
                       allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])

    def require_token(authorization: str | None = Header(default=None)):
        expected = "Bearer " + token
        if not isinstance(authorization, str) or not hmac.compare_digest(
                authorization, expected):
            raise HTTPException(401, "Unauthorized")

    @app.post("/api/bridge/v1/captures", dependencies=[Depends(require_token)])
    def capture(payload: Capture):
        if (payload.schema_version != 1 or
                not 1 <= len(payload.conversation_id) <= MAX_CONVERSATION_ID or
                payload.tab_id <= 0 or len(payload.text) > MAX_CAPTURE_TEXT or
                not payload.observed_at or len(payload.observed_at) > 128):
            raise HTTPException(422, "Invalid capture")

        # Capture dedup and LIVE proposal commit in one SQLite transaction.
        with ledger._connect() as conn:
            old = conn.execute(
                "SELECT conversation_id, tab_id, text, observed_at "
                "FROM live_captures WHERE message_id=?", (payload.message_id,)
            ).fetchone()
            incoming = (payload.conversation_id, payload.tab_id,
                        payload.text, payload.observed_at)
            if old is not None:
                if old != incoming:
                    raise HTTPException(409, "Capture ID collision")
                return {"message_id": payload.message_id, "status": "duplicate"}

            try:
                proposal = parse_ssh_request(payload.text, set(targets))
            except InvalidSSHRequest:
                proposal = None
            if proposal is not None:
                target = targets[proposal.host_id]
                data = json.dumps({
                    "request_id": proposal.request_id,
                    "host_id": proposal.host_id,
                    "working_directory": proposal.working_directory,
                    "description": proposal.description,
                    "commands": [asdict(command) for command in proposal.commands],
                }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                target_digest = target.digest()
                values = (
                    proposal.command_sha256, proposal.host_id, target_digest,
                    data, payload.conversation_id, payload.tab_id)
                existing = conn.execute(
                    "SELECT command_sha256,host_id,target_digest,proposal_json,"
                    "conversation_id,tab_id FROM live_proposals WHERE request_id=?",
                    (proposal.request_id,)).fetchone()
                if existing is not None and existing != values:
                    raise HTTPException(409, "LIVE proposal collision")
                if existing is None:
                    conn.execute(
                        "INSERT INTO live_proposals "
                        "(request_id,command_sha256,host_id,target_digest,"
                        "proposal_json,conversation_id,tab_id,status) "
                        "VALUES (?,?,?,?,?,?,?,'PROPOSED')",
                        (proposal.request_id, *values))
            conn.execute(
                "INSERT INTO live_captures "
                "(message_id,conversation_id,tab_id,text,observed_at) "
                "VALUES (?,?,?,?,?)",
                (payload.message_id, *incoming))
        return {"message_id": payload.message_id, "status": "accepted"}

    @app.get("/api/bridge/v1/ssh/proposals", dependencies=[Depends(require_token)])
    def list_proposals():
        # This is read-only metadata; the existing mock approve/reject paths
        # are deliberately NOT exposed by this service.
        with ledger._connect() as conn:
            rows = conn.execute(
                "SELECT request_id,host_id,conversation_id,tab_id,status "
                "FROM live_proposals WHERE status='PROPOSED' "
                "ORDER BY rowid DESC LIMIT 100").fetchall()
        return {"items": [
            dict(zip(("request_id", "host_id", "conversation_id",
                      "tab_id", "status"), row)) for row in rows]}

    @app.get("/api/bridge/v1/outbound", dependencies=[Depends(require_token)])
    def outbound():
        return {"items": []}

    @app.get("/api/bridge/v1/ssh/mock-results", dependencies=[Depends(require_token)])
    def mock_results():
        return {"items": []}

    return app


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Opt-in LIVE proposal intake; no SSH execution")
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--extension-origin", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    # Credential must come from an intentionally supplied local environment,
    # never the mock backend's fixed known token.
    token = os.environ.get("BRIDGE_LIVE_TOKEN", "")
    application = create_app(db_path=args.db, targets_path=args.targets,
                             token=token, extension_origin=args.extension_origin)
    print("LIVE proposal intake: approval, SSH and outbound sending DISABLED")
    uvicorn.run(application, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
