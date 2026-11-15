"""Offline-only operator-ticket-to-LIVE-approval transaction.

Not exposed through HTTP, Brave, CLI, or any SSH execution path.
The public LIVE ledger approve() and claim_execution() remain disabled.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError
from worker.operator_auth import OperatorAuthenticator, OperatorTicket
from worker.ssh_protocol import InvalidSSHRequest, parse_ssh_request


class OfflineLiveApprovalGate:
    """Consume a locally verified one-use ticket and persist one audited approval.

    The ticket is burned before the SQL change. Database failure therefore
    cannot result in an unlogged approval or reusable authorization token.
    """

    def __init__(self, ledger: LiveApprovalLedger, authenticator: OperatorAuthenticator):
        if type(ledger) is not LiveApprovalLedger or type(authenticator) is not OperatorAuthenticator:
            raise LiveAuthorizationError("trusted_components_required")
        self._ledger = ledger
        self._authenticator = authenticator
        with ledger._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS live_approval_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    approval_id TEXT NOT NULL UNIQUE,
                    operator_id TEXT NOT NULL,
                    command_sha256 TEXT NOT NULL,
                    target_digest TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    tab_id INTEGER NOT NULL,
                    action TEXT NOT NULL CHECK(action='APPROVED'),
                    created_at TEXT NOT NULL
                )
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS live_approval_audit_no_update
                BEFORE UPDATE ON live_approval_audit
                BEGIN SELECT RAISE(ABORT, 'audit_immutable'); END
            """)
            db.execute("""
                CREATE TRIGGER IF NOT EXISTS live_approval_audit_no_delete
                BEFORE DELETE ON live_approval_audit
                BEGIN SELECT RAISE(ABORT, 'audit_immutable'); END
            """)

    def approve_with_ticket(self, request_id: str, ticket: OperatorTicket) -> str:
        # BEGIN IMMEDIATE serializes concurrent approval attempts per DB file.
        with self._ledger._connect() as db:
            row = db.execute(
                "SELECT command_sha256,host_id,target_digest,proposal_json,"
                "conversation_id,tab_id,status FROM live_proposals WHERE request_id=?",
                (request_id,)
            ).fetchone()
            if row is None or row[6] != "PROPOSED":
                raise LiveAuthorizationError("live_proposal_not_pending")
            command_digest, host_id, target_digest, payload, conversation_id, tab_id, _ = row
            try:
                proposal = json.loads(payload)
                envelope = {
                    "schema_version": 1, "kind": "ssh_batch",
                    "request_id": proposal["request_id"],
                    "target": proposal["host_id"],
                    "working_directory": proposal["working_directory"],
                    "description": proposal["description"],
                    "commands": proposal["commands"],
                }
                parsed = parse_ssh_request(json.dumps(envelope, ensure_ascii=False), {host_id})
            except (ValueError, TypeError, KeyError, InvalidSSHRequest) as exc:
                raise LiveAuthorizationError("live_proposal_invalid") from exc
            if parsed.request_id != request_id or parsed.command_sha256 != command_digest:
                raise LiveAuthorizationError("live_proposal_digest_mismatch")

            operator_id = self._authenticator.consume_for_proposal(
                ticket, request_id=request_id, command_sha256=command_digest,
                target_digest=target_digest, conversation_id=conversation_id, tab_id=tab_id
            )
            approval_id = "live-" + secrets.token_urlsafe(24)
            updated = db.execute(
                "UPDATE live_proposals SET status='APPROVED', approval_id=?,"
                "approved_by=?, approved_via='operator_ticket' "
                "WHERE request_id=? AND status='PROPOSED'",
                (approval_id, operator_id, request_id)
            ).rowcount
            if updated != 1:
                raise LiveAuthorizationError("live_approval_race")
            db.execute(
                "INSERT INTO live_approval_audit "
                "(request_id,approval_id,operator_id,command_sha256,target_digest,"
                "conversation_id,tab_id,action,created_at) VALUES (?,?,?,?,?,?,?,'APPROVED',?)",
                (request_id, approval_id, operator_id, command_digest,
                 target_digest, conversation_id, tab_id,
                 datetime.now(timezone.utc).isoformat())
            )
            return approval_id

    def audit_for(self, request_id: str) -> list[dict]:
        with self._ledger._connect() as db:
            rows = db.execute(
                "SELECT approval_id,operator_id,command_sha256,target_digest,"
                "conversation_id,tab_id,action,created_at FROM live_approval_audit "
                "WHERE request_id=? ORDER BY audit_id", (request_id,)
            ).fetchall()
        keys = ("approval_id", "operator_id", "command_sha256", "target_digest",
                "conversation_id", "tab_id", "action", "created_at")
        return [dict(zip(keys, row)) for row in rows]
