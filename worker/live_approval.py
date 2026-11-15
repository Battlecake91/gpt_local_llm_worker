"""Unwired LIVE authorization ledger. No browser/API/CLI access or SSH execution.

LIVE approval has a separate table and cannot reuse mock approval IDs.
The operator identity proof must come from a future trusted authenticator.
No implementation of such an authenticator exists here.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from worker.ssh_protocol import SSHBatchRequest

class LiveAuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class LiveTargetBinding:
    host_id: str
    hostname: str
    port: int
    username: str
    host_public_key: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in
                   (self.host_id, self.hostname, self.username, self.host_public_key)):
            raise LiveAuthorizationError("invalid_target_identity")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise LiveAuthorizationError("invalid_port")

    def digest(self):
        content = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class LiveApprovalLedger:
    """Separate immutable LIVE proposal ledger. No execution or issuance endpoints."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS live_proposals (
                    request_id TEXT PRIMARY KEY,
                    command_sha256 TEXT NOT NULL,
                    host_id TEXT NOT NULL,
                    target_digest TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    tab_id INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status IN
                        ('PROPOSED','APPROVED','REJECTED','RUNNING','SUCCEEDED','FAILED','UNKNOWN')),
                    approval_id TEXT UNIQUE,
                    approved_by TEXT,
                    approved_via TEXT
                )
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS live_proposals_identity_immutable
                BEFORE UPDATE OF command_sha256, host_id, target_digest,
                    proposal_json, conversation_id, tab_id ON live_proposals
                BEGIN
                    SELECT RAISE(ABORT, 'live_proposal_immutable');
                END
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

    def propose(self, batch: SSHBatchRequest, target: LiveTargetBinding, *,
                tab_id: int, conversation_id: str):
        if batch.host_id != target.host_id:
            raise LiveAuthorizationError("host_binding_mismatch")
        if type(tab_id) is not int or tab_id <= 0 or not isinstance(conversation_id, str) or not conversation_id:
            raise LiveAuthorizationError("invalid_origin")
        data = json.dumps({
            "request_id": batch.request_id,
            "host_id": batch.host_id,
            "working_directory": batch.working_directory,
            "description": batch.description,
            "commands": [asdict(command) for command in batch.commands],
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        target_digest = target.digest()
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO live_proposals "
                "(request_id,command_sha256,host_id,target_digest,proposal_json,"
                "conversation_id,tab_id,status) VALUES (?,?,?,?,?,?,?,'PROPOSED')",
                (batch.request_id, batch.command_sha256, batch.host_id,
                 target_digest, data, conversation_id, tab_id)
            )
            existing = db.execute(
                "SELECT command_sha256,host_id,target_digest,proposal_json,"
                "conversation_id,tab_id FROM live_proposals WHERE request_id=?",
                (batch.request_id,)
            ).fetchone()
        if existing != (batch.command_sha256, batch.host_id, target_digest, data, conversation_id, tab_id):
            raise LiveAuthorizationError("live_request_id_collision")

    def get(self, request_id: str):
        with self._connect() as db:
            row = db.execute(
                "SELECT command_sha256,host_id,target_digest,proposal_json,"
                "conversation_id,tab_id,status,approval_id,approved_by,approved_via "
                "FROM live_proposals WHERE request_id=?", (request_id,)
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("command_sha256", "host_id", "target_digest", "proposal_json",
                         "conversation_id", "tab_id", "status", "approval_id",
                         "approved_by", "approved_via"),
                        row))

    def approve(self, *args, **kwargs):
        # Future integration must verify identity through a separate provider
        # before issuing an approval; never mistake a dataclass for credentials.
        raise LiveAuthorizationError("live_authenticator_not_integrated")

    def claim_execution(self, *args, **kwargs):
        raise LiveAuthorizationError("live_executor_not_enabled")

    def recover_unknown(self):
        """No active LIVE executor yet, but preserve crash safety for future wiring."""
        with self._connect() as db:
            return db.execute(
                "UPDATE live_proposals SET status='UNKNOWN' WHERE status='RUNNING'"
            ).rowcount
