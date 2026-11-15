"""Offline-only coordinator contract for approved SSH batches.

Not connected to Brave, HTTP, CLI, or the real OpenSSH transport. This module
refuses any transport other than an explicitly provided test double.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from worker.approval_state import ApprovalStateError, ApprovalStore
from worker.ssh_protocol import InvalidSSHRequest, parse_ssh_request
from worker.ssh_transport import SSHRunResult

MAX_RESULT_BYTES = 65536


class CommandTransport(Protocol):
    def run_command(self, host_alias: str, cwd: str, command: str, timeout_seconds: int) -> SSHRunResult:
        ...


@dataclass(frozen=True)
class FixtureOnlyPermit:
    """Test-only capability, never supplied by page content or the mock UI."""
    request_id: str
    approval_id: str
    digest: str


class OfflineExecutionCoordinator:
    """Execute a DB-approved batch through an injected *fake* transport only.

    A second, distinct fixture permit is required in addition to the existing
    mock approval. There is intentionally no API or script that issues permits.
    """

    def __init__(self, store: ApprovalStore, fake_transport: CommandTransport):
        if getattr(fake_transport, "hosts", None) is not None:
            # Real SSHTransport exposes hosts: never accept it at this layer.
            raise ApprovalStateError("real_transport_not_permitted")
        if not getattr(fake_transport, "_offline_fixture_transport", False):
            raise ApprovalStateError("fixture_transport_required")
        self.store = store
        self.transport = fake_transport

    @staticmethod
    def _verify_row(request_id: str, row: dict, permit: FixtureOnlyPermit) -> None:
        if type(permit) is not FixtureOnlyPermit or permit.request_id != request_id:
            raise ApprovalStateError("fixture_permit_required")
        if row is None or row["status"] != "APPROVED" or row["approval_id"] != permit.approval_id:
            raise ApprovalStateError("execution_not_approved")
        if row["command_sha256"] != permit.digest:
            raise ApprovalStateError("execution_digest_mismatch")
        envelope = {
            "schema_version": 1, "kind": "ssh_batch", "request_id": request_id,
            "target": row["host_id"], "working_directory": row["working_directory"],
            "description": row["description"], "commands": row["commands"],
        }
        try:
            verified = parse_ssh_request(json.dumps(envelope, ensure_ascii=False), {row["host_id"]})
        except (InvalidSSHRequest, ValueError, TypeError) as exc:
            raise ApprovalStateError("persisted_batch_invalid") from exc
        if verified.command_sha256 != permit.digest:
            raise ApprovalStateError("persisted_batch_digest_changed")

    def run(self, permit: FixtureOnlyPermit) -> dict:
        if type(permit) is not FixtureOnlyPermit:
            raise ApprovalStateError("fixture_permit_required")
        row = self.store.get(permit.request_id)
        self._verify_row(permit.request_id, row, permit)
        # The claim is durable before calling the fake transport.
        self.store.claim_execution(permit.request_id, permit.approval_id)
        result = {
            "schema_version": 1, "kind": "ssh_batch_result",
            "request_id": permit.request_id, "host_id": row["host_id"],
            "mode": "MOCK_ONLY", "status": "SUCCEEDED",
            "commands": [],
        }
        try:
            for item in row["commands"]:
                response = self.transport.run_command(
                    row["host_id"], row["working_directory"], item["command"],
                    item["timeout_seconds"])
                if type(response) is not SSHRunResult:
                    raise ApprovalStateError("invalid_fake_transport_result")
                result["commands"].append({
                    "id": item["id"], "exit_code": response.exit_code,
                    "stdout": response.stdout, "stderr": response.stderr,
                    "timed_out": response.timed_out, "truncated": response.truncated,
                    "timeout_seconds": item["timeout_seconds"],
                })
                if (response.exit_code != 0 or response.timed_out or response.truncated):
                    result["status"] = "FAILED"
                    break
            if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_RESULT_BYTES:
                raise ApprovalStateError("fixture_result_exceeds_limit")
        except Exception:
            # Unclear whether the fake transport finished: leave RUNNING.
            # Startup reconciliation must convert it to UNKNOWN, never retry.
            raise
        self.store.finish_mock_execution(permit.request_id, permit.approval_id, result)
        return result
