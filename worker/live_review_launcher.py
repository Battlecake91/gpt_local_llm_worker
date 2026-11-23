"""Explicit operator-initiated LIVE review from a local terminal.

Never accepts a password on argv, never connects to SSH, never sends to Brave.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from worker.live_approval import LiveApprovalLedger
from worker.operator_review_gui import load_local_targets, open_local_review
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_review import OperatorReviewController
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


def list_pending(ledger: LiveApprovalLedger) -> list[tuple[str, str, str]]:
    with ledger._connect() as db:
        return db.execute(
            "SELECT request_id,host_id,conversation_id FROM live_proposals "
            "WHERE status='PROPOSED' ORDER BY rowid DESC LIMIT 100"
        ).fetchall()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect or locally approve a LIVE proposal (NO SSH execution)")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--live-db", type=Path, required=True)
    exclusive = parser.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--list", action="store_true")
    exclusive.add_argument("--request-id")
    args = parser.parse_args(argv)
    if not args.state_dir.is_absolute() or not args.live_db.is_absolute():
        parser.error("absolute paths required")
    credential = args.state_dir / "operator-credential.json"
    rate = args.state_dir / "operator-rate-limit.sqlite3"
    target_file = args.state_dir / "targets.json"
    if not all(item.is_file() and not item.is_symlink()
               for item in (credential, rate, target_file, args.live_db)):
        parser.error("local operator credential, target, rate and LIVE files required")

    # Verify the configured allowlist even when just listing.
    targets = load_local_targets(target_file)
    ledger = LiveApprovalLedger(args.live_db)
    if args.list:
        rows = list_pending(ledger)
        print(f"Offene LIVE-Aufträge: {len(rows)}")
        for request_id, host_id, conversation_id in rows:
            print(f"{request_id}\t{host_id}\t{conversation_id}")
        print("Keine SSH-Ausführung.")
        return 0

    flow = TrustedOfflineOperatorFlow(
        OperatorCredentialFile(credential), rate, ledger)
    controller = OperatorReviewController(ledger, flow, targets)
    open_local_review(controller, args.request_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
