from __future__ import annotations

import sqlite3
from pathlib import Path

from .contracts import SSHBatch


class Store:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS batches (
                request_id TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                payload TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN
                    ('AWAITING_APPROVAL','APPROVED','REJECTED','RUNNING','UNKNOWN','SUCCEEDED','FAILED'))
            )
        """)
        self.db.commit()

    def propose(self, batch: SSHBatch) -> dict:
        payload = batch.model_dump_json()
        digest = batch.approval_digest()
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO batches VALUES (?, ?, ?, 'AWAITING_APPROVAL')",
                (batch.request_id, digest, payload),
            )
        row = self.get(batch.request_id)
        if row["digest"] != digest:
            raise ValueError("request_id already used for a different batch")
        return row

    def get(self, request_id: str) -> dict:
        row = self.db.execute("SELECT * FROM batches WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise KeyError(request_id)
        return dict(row)

    def decide(self, request_id: str, digest: str, approve: bool) -> dict:
        state = "APPROVED" if approve else "REJECTED"
        with self.db:
            result = self.db.execute(
                "UPDATE batches SET state=? WHERE request_id=? AND digest=? AND state='AWAITING_APPROVAL'",
                (state, request_id, digest),
            )
            if result.rowcount != 1:
                raise ValueError("missing, changed or already decided proposal")
        return self.get(request_id)

    def recover(self) -> None:
        with self.db:
            self.db.execute("UPDATE batches SET state='UNKNOWN' WHERE state='RUNNING'")
