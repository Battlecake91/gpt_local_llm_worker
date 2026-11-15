"""Operator-triggered OFFLINE fixture demo. Does not import SSH/subprocess transports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker.approval_state import ApprovalStore, ApprovalStateError
from worker.mock_executor import FixtureReply, MockHost, MockSSHExecutor

# Syntactic placeholder for simulated host metadata, NEVER a trusted real host key.
FIXTURE_ONLY_HOSTKEY = "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def simulate(db_path: str | Path, request_id: str, host_alias: str) -> dict:
    store = ApprovalStore(db_path)
    row = store.get(request_id)
    if row is None or row["status"] != "APPROVED":
        raise ApprovalStateError("no_approved_mock_proposal")
    if row["host_id"] != host_alias:
        raise ApprovalStateError("host_not_selected_for_mock")
    fixtures = {
        command["id"]: FixtureReply(
            stdout=f"MOCK ONLY: response fixture for command ID {command['id']}; no command executed.\n"
        )
        for command in row["commands"]
    }
    executor = MockSSHExecutor(
        store, {host_alias: MockHost(host_alias, "mockuser", FIXTURE_ONLY_HOSTKEY)})
    return executor.execute(
        request_id, row["approval_id"],
        command_sha256=row["command_sha256"], fixtures=fixtures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate previously approved SSH batch WITHOUT SSH")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--host-alias", required=True)
    parser.add_argument("--confirm-mock", action="store_true", required=True)
    args = parser.parse_args(argv)
    result = simulate(args.db, args.request_id, args.host_alias)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
