"""Strictly offline SSH execution simulator. No subprocess, SSH or network APIs."""
from __future__ import annotations

import re
from dataclasses import dataclass

from worker.approval_state import ApprovalStateError, ApprovalStore

HOSTKEY_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]{20,64}=?$")
USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
MAX_OUTPUT_BYTES = 16_384


@dataclass(frozen=True)
class MockHost:
    alias: str
    username: str
    pinned_host_key: str

    def __post_init__(self):
        if not isinstance(self.alias, str) or not self.alias or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", self.alias):
            raise ValueError("invalid_mock_host_alias")
        if not isinstance(self.username, str) or not USER_PATTERN.fullmatch(self.username):
            raise ValueError("invalid_mock_username")
        if not isinstance(self.pinned_host_key, str) or not HOSTKEY_PATTERN.fullmatch(self.pinned_host_key):
            raise ValueError("invalid_mock_hostkey_pin")


@dataclass(frozen=True)
class FixtureReply:
    exit_code: int | None = 0
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    def __post_init__(self):
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise ValueError("invalid_mock_output")
        if type(self.timed_out) is not bool:
            raise ValueError("invalid_mock_timeout")
        if self.exit_code is not None and (type(self.exit_code) is not int or not 0 <= self.exit_code <= 255):
            raise ValueError("invalid_mock_exit_code")
        if self.timed_out and self.exit_code is not None:
            raise ValueError("timeout_cannot_have_exit_code")


def _bounded(text: str, budget: int) -> tuple[str, int, bool]:
    raw = text.encode("utf-8")
    head = raw[:budget]
    # Do not store broken UTF-8 sequences after applying a byte limit.
    clipped = head.decode("utf-8", errors="ignore")
    encoded_length = len(clipped.encode("utf-8"))
    return clipped, encoded_length, encoded_length < len(raw)


class MockSSHExecutor:
    """Consume one approved batch using fixtures keyed by command ID.

    Fixture values are *never* commands to run; they are static responses.
    A configured host key is metadata only, NOT a cryptographic verification.
    """

    def __init__(self, store: ApprovalStore, hosts: dict[str, MockHost], *,
                 max_output_bytes: int = MAX_OUTPUT_BYTES):
        if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_OUTPUT_BYTES:
            raise ValueError("invalid_mock_output_limit")
        for alias, host in hosts.items():
            if alias != host.alias:
                raise ValueError("mock_host_alias_mismatch")
        self.store = store
        self.hosts = dict(hosts)
        self.max_output_bytes = max_output_bytes

    def execute(self, request_id: str, approval_id: str, *,
                command_sha256: str, fixtures: dict[str, FixtureReply]) -> dict:
        row = self.store.get(request_id)
        if row is None or row["status"] != "APPROVED" or row["approval_id"] != approval_id:
            raise ApprovalStateError("mock_execution_denied")
        if row["command_sha256"] != command_sha256:
            raise ApprovalStateError("mock_digest_mismatch")
        host = self.hosts.get(row["host_id"])
        if host is None:
            raise ApprovalStateError("mock_host_not_configured")
        if not isinstance(fixtures, dict):
            raise ValueError("invalid_mock_fixtures")
        commands = row["commands"]
        if set(fixtures) != {cmd["id"] for cmd in commands} or not all(
            isinstance(x, FixtureReply) for x in fixtures.values()
        ):
            raise ValueError("mock_fixture_mismatch")

        # This is the one-time, durable side-effect gate. On crash this becomes
        # UNKNOWN during recovery; never re-execute the fixture automatically.
        self.store.claim_execution(request_id, approval_id)
        result = {
            "schema_version": 1,
            "kind": "ssh_batch_result",
            "request_id": request_id,
            "host_id": host.alias,
            "username": host.username,
            "mode": "MOCK_ONLY",
            "status": "SUCCEEDED",
            "commands": [],
        }
        remaining = self.max_output_bytes
        for command in commands:
            fixture = fixtures[command["id"]]
            stdout, used, truncated_stdout = _bounded(fixture.stdout, remaining)
            remaining -= used
            stderr, used, truncated_stderr = _bounded(fixture.stderr, remaining)
            remaining -= used
            failed = fixture.timed_out or fixture.exit_code != 0
            result["commands"].append({
                "id": command["id"],
                "exit_code": fixture.exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "timed_out": fixture.timed_out,
                "timeout_seconds": command["timeout_seconds"],
                "truncated": truncated_stdout or truncated_stderr,
            })
            if failed or truncated_stdout or truncated_stderr:
                result["status"] = "FAILED"
                break
        self.store.finish_mock_execution(request_id, approval_id, result)
        return result
