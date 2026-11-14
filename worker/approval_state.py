"""Durable, non-executing SSH approval state. Only an authenticated UI may call approve()."""
from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

from worker.ssh_protocol import SSHBatchRequest


class ApprovalStateError(ValueError):
    pass


class ApprovalStore:
    """Transactional proposal/approval ledger. This class never executes commands."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS ssh_batches (
                    request_id TEXT PRIMARY KEY,
                    host_id TEXT NOT NULL,
                    command_sha256 TEXT NOT NULL,
                    commands_json TEXT NOT NULL,
                    tab_id INTEGER NOT NULL,
                    conversation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_id TEXT UNIQUE,
                    approved_by TEXT
                )
            """)

    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level="IMMEDIATE")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def propose(self, request: SSHBatchRequest, *, tab_id: int, conversation_id: str):
        if type(tab_id) is not int or tab_id <= 0 or not isinstance(conversation_id, str) or not conversation_id:
            raise ApprovalStateError("invalid_origin")
        commands_json = json.dumps(request.commands, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO ssh_batches VALUES (?,?,?,?,?,?,?,?,?)", (
                request.request_id, request.host_id, request.command_sha256,
                commands_json, tab_id, conversation_id, "PROPOSED", None, None
            ))
            row = db.execute(
                "SELECT host_id, command_sha256, commands_json, tab_id, conversation_id FROM ssh_batches WHERE request_id=?",
                (request.request_id,)
            ).fetchone()
            if row != (request.host_id, request.command_sha256, commands_json, tab_id, conversation_id):
                raise ApprovalStateError("request_id_collision")
        return request.request_id

    def approve(self, request_id: str, *, command_sha256: str, authenticated_operator: str):
        """Call ONLY after the trusted approval UI displays and confirms the complete batch."""
        if not isinstance(authenticated_operator, str) or not authenticated_operator.strip():
            raise ApprovalStateError("missing_operator")
        approval_id = secrets.token_urlsafe(24)
        with self._connect() as db:
            row = db.execute("SELECT command_sha256, status FROM ssh_batches WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row[0] != command_sha256 or row[1] != "PROPOSED":
                raise ApprovalStateError("approval_denied")
            updated = db.execute(
                "UPDATE ssh_batches SET status='APPROVED', approval_id=?, approved_by=? WHERE request_id=? AND status='PROPOSED'",
                (approval_id, authenticated_operator, request_id)
            ).rowcount
            if updated != 1:
                raise ApprovalStateError("approval_race")
        return approval_id

    def reject(self, request_id: str):
        with self._connect() as db:
            if db.execute("UPDATE ssh_batches SET status='REJECTED' WHERE request_id=? AND status='PROPOSED'",
                          (request_id,)).rowcount != 1:
                raise ApprovalStateError("rejection_denied")

    def claim_execution(self, request_id: str, approval_id: str):
        """Persist RUNNING before any executor could be invoked. Never auto-retry."""
        with self._connect() as db:
            changed = db.execute(
                "UPDATE ssh_batches SET status='RUNNING' WHERE request_id=? AND approval_id=? AND status='APPROVED'",
                (request_id, approval_id)
            ).rowcount
            if changed != 1:
                raise ApprovalStateError("execution_denied")

    def recover_unknown(self):
        """On startup, unresolved RUNNING batches require manual reconciliation."""
        with self._connect() as db:
            return db.execute(
                "UPDATE ssh_batches SET status='UNKNOWN' WHERE status='RUNNING'"
            ).rowcount

    def get(self, request_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT host_id,command_sha256,commands_json,tab_id,conversation_id,status,approval_id,approved_by "
                "FROM ssh_batches WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("host_id", "command_sha256", "commands", "tab_id", "conversation_id",
                         "status", "approval_id", "approved_by"),
                        (row[0], row[1], json.loads(row[2]), *row[3:])))
