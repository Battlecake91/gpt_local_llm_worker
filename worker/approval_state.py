"""Durable, non-executing SSH approval state. Only an authenticated UI may call approve()."""
from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import asdict
from contextlib import contextmanager
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
                    working_directory TEXT NOT NULL,
                    description TEXT NOT NULL,
                    command_sha256 TEXT NOT NULL,
                    commands_json TEXT NOT NULL,
                    tab_id INTEGER NOT NULL,
                    conversation_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    approval_id TEXT UNIQUE,
                    approved_by TEXT
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS mock_execution_results (
                    request_id TEXT PRIMARY KEY REFERENCES ssh_batches(request_id),
                    status TEXT NOT NULL CHECK(status IN ('SUCCEEDED','FAILED','UNKNOWN')),
                    result_json TEXT NOT NULL
                )
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level="IMMEDIATE")
        try:
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                yield db
        finally:
            db.close()

    def propose(self, request: SSHBatchRequest, *, tab_id: int, conversation_id: str):
        if type(tab_id) is not int or tab_id <= 0 or not isinstance(conversation_id, str) or not conversation_id:
            raise ApprovalStateError("invalid_origin")
        commands_json = json.dumps([asdict(command) for command in request.commands], ensure_ascii=False, separators=(",", ":"))
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO ssh_batches VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                request.request_id, request.host_id, request.working_directory,
                request.description, request.command_sha256, commands_json,
                tab_id, conversation_id, "PROPOSED", None, None
            ))
            row = db.execute(
                "SELECT host_id, working_directory, description, command_sha256, commands_json, tab_id, conversation_id "
                "FROM ssh_batches WHERE request_id=?",
                (request.request_id,)
            ).fetchone()
            if row != (request.host_id, request.working_directory, request.description,
                       request.command_sha256, commands_json, tab_id, conversation_id):
                raise ApprovalStateError("request_id_collision")
        return request.request_id

    def pending(self, limit: int = 30):
        """Return complete, immutable review data without any approval side effect."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT request_id,host_id,working_directory,description,command_sha256,"
                "commands_json,tab_id,conversation_id FROM ssh_batches "
                "WHERE status='PROPOSED' ORDER BY rowid LIMIT ?", (min(max(limit, 1), 100),)
            ).fetchall()
        return [
            dict(request_id=row[0], host_id=row[1], working_directory=row[2],
                 description=row[3], command_sha256=row[4], commands=json.loads(row[5]),
                 tab_id=row[6], conversation_id=row[7])
            for row in rows
        ]

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

    def finish_mock_execution(self, request_id: str, approval_id: str, result: dict):
        """Atomically commit a bounded fixture result; never accept a second result."""
        if not isinstance(result, dict) or result.get("status") not in ("SUCCEEDED", "FAILED", "UNKNOWN"):
            raise ApprovalStateError("invalid_mock_result")
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 131_072:
            raise ApprovalStateError("mock_result_too_large")
        with self._connect() as db:
            updated = db.execute(
                "UPDATE ssh_batches SET status=? WHERE request_id=? AND approval_id=? AND status='RUNNING'",
                (result["status"], request_id, approval_id)
            ).rowcount
            if updated != 1:
                raise ApprovalStateError("mock_completion_denied")
            db.execute(
                "INSERT INTO mock_execution_results(request_id,status,result_json) VALUES (?,?,?)",
                (request_id, result["status"], serialized)
            )

    def get_mock_result(self, request_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT result_json FROM mock_execution_results WHERE request_id=?",
                (request_id,)
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def get(self, request_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT host_id,working_directory,description,command_sha256,commands_json,tab_id,conversation_id,status,approval_id,approved_by "
                "FROM ssh_batches WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("host_id", "working_directory", "description", "command_sha256",
                         "commands", "tab_id", "conversation_id", "status", "approval_id", "approved_by"),
                        (row[0], row[1], row[2], row[3], json.loads(row[4]), *row[5:])))
