"""Isolated operator password verification and single-use proposal-bound tickets.

No browser, HTTP, SSH, or LIVE approval is wired to this module.
A secret must be provisioned out-of-band and never shared with the extension.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

_SALT_BYTES = 16
_KEY_BYTES = 32
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60
_TICKET_SECONDS = 90
_MIN_SECRET_BYTES = 16
_MAX_SECRET_BYTES = 1024


class OperatorAuthError(ValueError):
    pass


@dataclass(frozen=True)
class OperatorPasswordRecord:
    operator_id: str
    salt: bytes
    password_hash: bytes

    def __post_init__(self):
        if not isinstance(self.operator_id, str) or not self.operator_id.strip() or len(self.operator_id) > 80:
            raise OperatorAuthError("invalid_operator")
        if (type(self.salt) is not bytes or type(self.password_hash) is not bytes
                or len(self.salt) != _SALT_BYTES or len(self.password_hash) != _KEY_BYTES):
            raise OperatorAuthError("invalid_credential_record")


def _derive(secret: str, salt: bytes) -> bytes:
    if not isinstance(secret, str):
        raise OperatorAuthError("invalid_operator_secret")
    encoded = secret.encode("utf-8")
    if not _MIN_SECRET_BYTES <= len(encoded) <= _MAX_SECRET_BYTES:
        raise OperatorAuthError("invalid_operator_secret")
    return hashlib.scrypt(encoded, salt=salt, n=2**14, r=8, p=1, dklen=_KEY_BYTES)


def create_password_record(operator_id: str, secret: str) -> OperatorPasswordRecord:
    """Return a salted credential record. Never store or log the clear secret."""
    salt = secrets.token_bytes(_SALT_BYTES)
    return OperatorPasswordRecord(operator_id, salt, _derive(secret, salt))


@dataclass(frozen=True)
class OperatorTicket:
    """Opaque, short-lived approval proof. Not a credential or a bearer for SSH."""
    token: str


class OperatorAuthenticator:
    """Memory-only verification, throttling and single-use bound ticket contract.

    This is an offline component. Restart invalidates tickets. The eventual
    integration must persist approval and audit atomically after consumption.
    """

    def __init__(self, record: OperatorPasswordRecord, *, clock: Callable[[], float] = time.monotonic):
        if type(record) is not OperatorPasswordRecord:
            raise OperatorAuthError("invalid_credential_record")
        self._record = record
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._locked_until = 0.0
        self._tickets: dict[str, tuple[float, tuple[str, str, str, str, int]]] = {}

    @staticmethod
    def _binding(request_id: str, command_sha256: str, target_digest: str,
                 conversation_id: str, tab_id: int):
        import re
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", request_id):
            raise OperatorAuthError("invalid_request_id")
        if not isinstance(command_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", command_sha256):
            raise OperatorAuthError("invalid_command_digest")
        if not isinstance(target_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", target_digest):
            raise OperatorAuthError("invalid_target_digest")
        if not isinstance(conversation_id, str) or not conversation_id or len(conversation_id) > 256:
            raise OperatorAuthError("invalid_conversation_id")
        if type(tab_id) is not int or tab_id <= 0:
            raise OperatorAuthError("invalid_tab_id")
        return (request_id, command_sha256, target_digest, conversation_id, tab_id)

    def verify_for_proposal(self, secret: str, *, request_id: str, command_sha256: str,
                            target_digest: str, conversation_id: str, tab_id: int) -> OperatorTicket:
        binding = self._binding(request_id, command_sha256, target_digest, conversation_id, tab_id)
        with self._lock:
            now = self._clock()
            if now < self._locked_until:
                raise OperatorAuthError("operator_temporarily_locked")
            try:
                candidate = _derive(secret, self._record.salt)
            except OperatorAuthError:
                candidate = bytes(_KEY_BYTES)
            if not hmac.compare_digest(candidate, self._record.password_hash):
                self._failures += 1
                if self._failures >= _MAX_ATTEMPTS:
                    self._locked_until = now + _LOCKOUT_SECONDS
                    self._failures = 0
                raise OperatorAuthError("operator_authentication_failed")
            self._failures = 0
            # Bound transient tickets so successful verifications cannot grow
            # in-memory state without limit.
            self._tickets = {
                key: value for key, value in self._tickets.items()
                if value[0] > now
            }
            if len(self._tickets) >= 128:
                raise OperatorAuthError("too_many_pending_tickets")
            token = secrets.token_urlsafe(32)
            self._tickets[token] = (now + _TICKET_SECONDS, binding)
            return OperatorTicket(token)

    def consume_for_proposal(self, ticket: OperatorTicket, *, request_id: str,
                             command_sha256: str, target_digest: str,
                             conversation_id: str, tab_id: int) -> str:
        binding = self._binding(request_id, command_sha256, target_digest, conversation_id, tab_id)
        if type(ticket) is not OperatorTicket:
            raise OperatorAuthError("invalid_operator_ticket")
        with self._lock:
            # Pop first: even a wrong origin/digest irrevocably consumes it.
            saved = self._tickets.pop(ticket.token, None)
            if saved is None:
                raise OperatorAuthError("ticket_missing_or_used")
            expires, expected = saved
            if self._clock() >= expires:
                raise OperatorAuthError("ticket_expired")
            if not hmac.compare_digest(repr(binding).encode(), repr(expected).encode()):
                raise OperatorAuthError("ticket_binding_mismatch")
            return self._record.operator_id
