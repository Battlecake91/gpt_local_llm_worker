"""Single offline operator entry flow using persistent credentials and lockout.

No HTTP, Brave, CLI or real SSH integration. This is a library-only contract
for a future trusted local UI; merely importing it never enables execution.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable
import time

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError
from worker.offline_live_gate import OfflineLiveApprovalGate
from worker.operator_auth import OperatorAuthenticator
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_rate_limit import PersistentOperatorVerifier


class TrustedOfflineOperatorFlow:
    """Load provisioned credentials and require durable throttling for approvals.

    The caller cannot supply an already-verified ticket or an authenticator.
    Password input is checked against the private credential record through
    the persistent verifier on every approval attempt. This object is not an
    authentication boundary against arbitrary in-process Python code.
    """

    def __init__(
        self,
        credentials: OperatorCredentialFile,
        rate_limit_db: str | Path,
        live_ledger: LiveApprovalLedger,
        *,
        clock: Callable[[], float] = time.time,
    ):
        if type(credentials) is not OperatorCredentialFile:
            raise LiveAuthorizationError("trusted_credentials_required")
        if type(live_ledger) is not LiveApprovalLedger:
            raise LiveAuthorizationError("trusted_live_ledger_required")
        record = credentials.load()  # Missing or corrupt credentials deny startup.
        authenticator = OperatorAuthenticator(record)
        self._verifier = PersistentOperatorVerifier(
            rate_limit_db, authenticator, clock=clock
        )
        self._ledger = live_ledger
        self._gate = OfflineLiveApprovalGate(live_ledger, authenticator)

    def approve(self, request_id: str, password: str) -> str:
        """Approve a previously persisted LIVE proposal after password check.

        No execution occurs. The exact immutable row supplies all binding
        values; untrusted callers may only choose the existing request ID.
        """
        if not isinstance(request_id, str) or not request_id:
            raise LiveAuthorizationError("invalid_live_request_id")
        row = self._ledger.get(request_id)
        if row is None or row["status"] != "PROPOSED":
            raise LiveAuthorizationError("live_proposal_not_pending")
        ticket = self._verifier.verify_for_proposal(
            password,
            request_id=request_id,
            command_sha256=row["command_sha256"],
            target_digest=row["target_digest"],
            conversation_id=row["conversation_id"],
            tab_id=row["tab_id"],
        )
        return self._gate.approve_with_ticket(request_id, ticket)

    def audit_for(self, request_id: str) -> list[dict]:
        return self._gate.audit_for(request_id)
