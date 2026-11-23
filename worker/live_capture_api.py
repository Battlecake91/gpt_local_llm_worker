"""Opt-in loopback LIVE proposal intake, without authorization or execution.

Compatible with the MV3 capture protocol. Does not provide approve/reject,
outbound, SSH command execution, or browser auto-send capabilities.
"""
from __future__ import annotations

import hmac
import hashlib
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
from worker.ollama_analysis import OllamaAnalyzer, ProfileStore, AnalysisError, FENCE, PROMPT_LINE

MAX_CAPTURE_TEXT = 256_000
MAX_CONVERSATION_ID = 256


class ProfileSelection(BaseModel):
    name: str


class Capture(BaseModel):
    schema_version: int
    message_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    conversation_id: str
    tab_id: int
    text: str
    user_prompt: str = Field(default="", max_length=8192)
    observed_at: str


def create_app(*, db_path: Path, targets_path: Path, token: str,
               extension_origin: str, ollama_profiles: Path | None = None,
               ollama_client=None) -> FastAPI:
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
    analyzer = OllamaAnalyzer(ProfileStore(ollama_profiles), ollama_client) if ollama_profiles else None
    if analyzer is not None:
        analyzer.profiles.load()  # Fail closed on malformed administrator configuration.
    ledger = LiveApprovalLedger(db_path)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS live_captures (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id INTEGER NOT NULL,
                text_sha256 TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )
        """)

    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS ollama_suggestions (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id INTEGER NOT NULL,
                analysis_json TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                FOREIGN KEY(message_id) REFERENCES live_captures(message_id)
            )
        """)

    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS ollama_diagnostics (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                tab_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                user_prompt_present INTEGER NOT NULL,
                eligible_shell_blocks INTEGER NOT NULL,
                model TEXT,
                FOREIGN KEY(message_id) REFERENCES live_captures(message_id)
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

        # Classification is advisory only. Nothing here grants execution.
        # Analyze outside SQLite's write transaction, so Ollama cannot block other writes.
        analysis = None
        diagnostic_status = None
        eligible_shell_blocks = len(FENCE.findall(payload.text)) + len(
            PROMPT_LINE.findall(FENCE.sub("", payload.text)))
        model = None
        if analyzer is not None:
            try:
                model = analyzer.profiles.load()[0]["model"]
                analysis = analyzer.analyze(payload.text, set(targets), payload.user_prompt)
            except (AnalysisError, OSError) as exc:
                raise HTTPException(503, "Ollama analysis unavailable: " + str(exc)) from exc
            diagnostic_status = (
                "no_shell_blocks" if eligible_shell_blocks == 0 else
                "classified_nonactionable" if analysis is None else
                "target_unresolved" if analysis.host is None else
                "proposal_ready"
            )

        # Capture dedup and LIVE proposal commit in one SQLite transaction.
        with ledger._connect() as conn:
            # Serialize concurrent retries before checking either identity.
            conn.execute("BEGIN IMMEDIATE")
            old = conn.execute(
                "SELECT conversation_id, tab_id, text_sha256, observed_at "
                "FROM live_captures WHERE message_id=?", (payload.message_id,)
            ).fetchone()
            incoming = (payload.conversation_id, payload.tab_id,
                        hashlib.sha256((payload.text + ("\0" + payload.user_prompt if payload.user_prompt else "")).encode('utf-8')).hexdigest(),
                        payload.observed_at)
            if old is not None:
                # observed_at is receipt metadata, not the immutable content.
                # A manual re-capture after MV3 restart may have a new time.
                if old[:3] != incoming[:3]:
                    raise HTTPException(409, "Capture ID collision")
                return {"message_id": payload.message_id, "status": "duplicate"}

            if analyzer is not None:
                proposal = analysis.batch(payload.message_id) if analysis else None
            else:
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
                "(message_id,conversation_id,tab_id,text_sha256,observed_at) "
                "VALUES (?,?,?,?,?)",
                (payload.message_id, *incoming))
            if diagnostic_status is not None:
                conn.execute(
                    "INSERT INTO ollama_diagnostics "
                    "(message_id,conversation_id,tab_id,status,user_prompt_present,"
                    "eligible_shell_blocks,model) VALUES (?,?,?,?,?,?,?)",
                    (payload.message_id, payload.conversation_id, payload.tab_id,
                     diagnostic_status, int(bool(payload.user_prompt)),
                     eligible_shell_blocks, model))
            if analysis is not None:
                conn.execute(
                    "INSERT INTO ollama_suggestions "
                    "(message_id,conversation_id,tab_id,analysis_json,source_sha256) "
                    "VALUES (?,?,?,?,?)",
                    (payload.message_id, payload.conversation_id, payload.tab_id,
                     json.dumps({
                         "commands": analysis.commands, "host": analysis.host,
                         "risk": analysis.risk, "reason": analysis.reason,
                         "model": analysis.model, "review_only": True,
                     }, ensure_ascii=False), incoming[2]))
        return {"message_id": payload.message_id, "status": "accepted"}

    @app.get("/api/bridge/v1/ollama/profiles", dependencies=[Depends(require_token)])
    def list_ollama_profiles():
        if analyzer is None:
            return {"enabled": False, "profiles": [], "active": None}
        try:
            active, profiles = analyzer.profiles.load()
        except (AnalysisError, OSError, ValueError) as exc:
            raise HTTPException(503, "Invalid Ollama configuration") from exc
        return {"enabled": True, "profiles": [
            {"name": p["name"], "model": p["model"], "url": p["url"]}
            for p in profiles], "active": active["name"]}

    @app.get("/api/bridge/v1/ollama/models", dependencies=[Depends(require_token)])
    def list_ollama_models():
        if analyzer is None:
            raise HTTPException(404, "Ollama disabled")
        try:
            models = analyzer.available_models()
            active, _ = analyzer.profiles.load()
        except (AnalysisError, OSError, ValueError) as exc:
            raise HTTPException(503, "Ollama model discovery unavailable") from exc
        return {"active": active["name"], "selected_model": active["model"],
                "models": models}

    @app.post("/api/bridge/v1/ollama/select", dependencies=[Depends(require_token)])
    def select_ollama_profile(selection: ProfileSelection):
        if analyzer is None:
            raise HTTPException(404, "Ollama disabled")
        try:
            analyzer.profiles.select(selection.name)
        except (AnalysisError, OSError, ValueError) as exc:
            raise HTTPException(422, "Invalid Ollama profile") from exc
        return {"active": selection.name}

    @app.get("/api/bridge/v1/ollama/diagnostics", dependencies=[Depends(require_token)])
    def list_ollama_diagnostics():
        # Bounded metadata only. No captured response, user prompt, token, or
        # raw model output is retained in these diagnostics.
        with ledger._connect() as conn:
            rows = conn.execute(
                "SELECT message_id,conversation_id,tab_id,status,"
                "user_prompt_present,eligible_shell_blocks,model "
                "FROM ollama_diagnostics ORDER BY rowid DESC LIMIT 20"
            ).fetchall()
        return {"items": [
            {"message_id": row[0], "conversation_id": row[1],
             "tab_id": row[2], "status": row[3],
             "user_prompt_present": bool(row[4]),
             "eligible_shell_blocks": row[5], "model": row[6]}
            for row in rows
        ]}

    @app.get("/api/bridge/v1/ollama/suggestions", dependencies=[Depends(require_token)])
    def list_ollama_suggestions():
        with ledger._connect() as conn:
            rows = conn.execute(
                "SELECT message_id,conversation_id,tab_id,analysis_json "
                "FROM ollama_suggestions ORDER BY rowid DESC LIMIT 50"
            ).fetchall()
        return {"items": [
            {"message_id": row[0], "conversation_id": row[1], "tab_id": row[2],
             **json.loads(row[3])} for row in rows
        ]}

    @app.get("/api/bridge/v1/ssh/proposals", dependencies=[Depends(require_token)])
    def mock_panel_proposals():
        # The existing side panel's buttons are MOCK approve/reject actions.
        # LIVE proposals are only listed/reviewed via live_review_launcher.
        return {"items": []}

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
    parser.add_argument("--ollama-profiles", type=Path, default=None,
                        help="Opt-in JSON configuration for verbatim Ollama analysis")
    args = parser.parse_args()
    # Credential must come from an intentionally supplied local environment,
    # never the mock backend's fixed known token.
    token = os.environ.get("BRIDGE_LIVE_TOKEN", "")
    application = create_app(db_path=args.db, targets_path=args.targets,
                             token=token, extension_origin=args.extension_origin,
                             ollama_profiles=args.ollama_profiles)
    print("LIVE proposal intake: approval, SSH and outbound sending DISABLED")
    uvicorn.run(application, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
