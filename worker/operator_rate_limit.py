"""SQLite-backed failed-login limits, independent of process restarts.

Not wired to Brave, CLI, HTTP, or live execution. The wrapper must be used
instead of calling OperatorAuthenticator.verify_for_proposal directly by any
future trusted operator entry point.
"""
from __future__ import annotations

import math
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from worker.operator_auth import OperatorAuthenticator, OperatorAuthError

MAX_FAILURES = 5
LOCK_SECONDS = 60


class PersistentOperatorVerifier:
    """Serialize password verification and failed-attempt updates in SQLite.

    Each attempt takes a BEGIN IMMEDIATE writer lock before checking or
    modifying persistent counters. A clock rollback fails closed rather than
    shortening a lockout. Only verifier metadata is persisted, not passwords
    or short-lived tickets.
    """

    def __init__(self, db_path: str | Path, authenticator: OperatorAuthenticator,
                 *, clock: Callable[[], float] = time.time):
        path = Path(db_path)
        if not path.is_absolute():
            raise OperatorAuthError("rate_limit_path_not_absolute")
        if type(authenticator) is not OperatorAuthenticator:
            raise OperatorAuthError("invalid_authenticator")
        self.db_path = str(path)
        self._auth = authenticator
        self._clock = clock
        # The operator identity originates from the authenticated credential
        # record, not from model content or browser-provided parameters.
        self._operator_id = authenticator._record.operator_id
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS operator_login_limits (
                    operator_id TEXT PRIMARY KEY,
                    failed_attempts INTEGER NOT NULL DEFAULT 0
                        CHECK(failed_attempts BETWEEN 0 AND 4),
                    locked_until REAL NOT NULL DEFAULT 0,
                    last_observed REAL NOT NULL DEFAULT 0
                )
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.rollback()
                raise
            else:
                db.commit()
        finally:
            db.close()

    def verify_for_proposal(self, secret: str, **binding):
        now = self._clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            raise OperatorAuthError("invalid_wall_clock")
        error = None
        ticket = None
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO operator_login_limits(operator_id) VALUES (?)",
                (self._operator_id,))
            row = db.execute(
                "SELECT failed_attempts,locked_until,last_observed "
                "FROM operator_login_limits WHERE operator_id=?",
                (self._operator_id,)).fetchone()
            failures, locked_until, last_observed = row
            if now < last_observed:
                raise OperatorAuthError("operator_clock_rollback")
            if now < locked_until:
                raise OperatorAuthError("operator_temporarily_locked")
            try:
                ticket = self._auth.verify_for_proposal(secret, **binding)
            except OperatorAuthError as exc:
                error = exc
                # Only incorrect credentials count toward the limit. Invalid
                # request metadata cannot clear the counter or issue a ticket.
                if str(exc) == "operator_authentication_failed":
                    failures += 1
                    if failures >= MAX_FAILURES:
                        locked_until = now + LOCK_SECONDS
                        failures = 0
                # Unknown/invalid inputs must not update the lockout history
                # except for monotonic wall-clock protection.
            else:
                failures = 0
                locked_until = 0.0
            db.execute(
                "UPDATE operator_login_limits SET failed_attempts=?,locked_until=?,"
                "last_observed=? WHERE operator_id=?",
                (failures, locked_until, now, self._operator_id))
        if error is not None:
            raise error
        return ticket

    def status(self):
        """Read-only metadata for offline diagnostics, never secret material."""
        with self._connect() as db:
            row = db.execute(
                "SELECT failed_attempts,locked_until,last_observed "
                "FROM operator_login_limits WHERE operator_id=?",
                (self._operator_id,)).fetchone()
        if row is None:
            return {"failed_attempts": 0, "locked_until": 0.0, "last_observed": 0.0}
        return dict(zip(("failed_attempts", "locked_until", "last_observed"), row))
