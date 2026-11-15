"""Local LIVE review model, separate from Brave and the mock review UI.

The operator must see the exact full commands and configured SSH identity.
No HTTP, browser, service, SSH execution or auto-send is enabled.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.ssh_protocol import InvalidSSHRequest, parse_ssh_request
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


@dataclass(frozen=True)
class CommandReview:
    id: str
    command: str
    timeout_seconds: int


@dataclass(frozen=True)
class LiveReview:
    request_id: str
    host_alias: str
    hostname: str
    port: int
    ssh_username: str
    host_public_key: str
    working_directory: str
    description: str
    commands: tuple[CommandReview, ...]
    command_sha256: str
    target_digest: str
    conversation_id: str
    tab_id: int

    def render_text(self) -> str:
        """Never use this as shell input; commands are untrusted plain text."""
        lines = [
            "LIVE SSH COMMAND BATCH / REVIEW ONLY",
            f"Request: {self.request_id}",
            f"Host alias: {self.host_alias}",
            f"SSH destination: {self.ssh_username}@{self.hostname}:{self.port}",
            f"Pinned public hostkey: {self.host_public_key}",
            f"Working directory: {self.working_directory}",
            f"Description: {self.description}",
            f"Origin conversation: {self.conversation_id}",
            f"Origin tab: {self.tab_id}",
            f"Command digest (SHA-256): {self.command_sha256}",
            f"Target digest (SHA-256): {self.target_digest}",
            f"Commands ({len(self.commands)}), exact text:",
        ]
        for index, command in enumerate(self.commands, 1):
            lines.extend((
                f"[{index}] id={command.id} timeout={command.timeout_seconds}s",
                command.command,
                "----- END COMMAND -----",
            ))
        lines.append("No SSH execution occurs when a batch is approved.")
        return "\n".join(lines)


class OperatorReviewController:
    """Pure review/approval contract; no shell/process/browser privileges."""

    def __init__(
        self,
        ledger: LiveApprovalLedger,
        flow: TrustedOfflineOperatorFlow,
        configured_targets: dict[str, LiveTargetBinding],
    ):
        if type(ledger) is not LiveApprovalLedger or type(flow) is not TrustedOfflineOperatorFlow:
            raise LiveAuthorizationError("trusted_review_components_required")
        if not isinstance(configured_targets, dict):
            raise LiveAuthorizationError("configured_target_list_required")
        if any(type(value) is not LiveTargetBinding or key != value.host_id
               for key, value in configured_targets.items()):
            raise LiveAuthorizationError("invalid_configured_target")
        self._ledger = ledger
        self._flow = flow
        self._targets = dict(configured_targets)

    def prepare(self, request_id: str) -> LiveReview:
        row = self._ledger.get(request_id)
        if row is None or row["status"] != "PROPOSED":
            raise LiveAuthorizationError("live_proposal_not_pending")
        try:
            data = json.loads(row["proposal_json"])
            if type(data) is not dict or set(data) != {
                "request_id", "host_id", "working_directory", "description", "commands"
            }:
                raise ValueError("invalid_proposal_shape")
            target = self._targets[row["host_id"]]
            batch = parse_ssh_request(json.dumps({
                "schema_version": 1, "kind": "ssh_batch",
                "request_id": data["request_id"], "target": data["host_id"],
                "working_directory": data["working_directory"],
                "description": data["description"], "commands": data["commands"],
            }, ensure_ascii=False), {row["host_id"]})
        except (ValueError, TypeError, KeyError, InvalidSSHRequest) as exc:
            raise LiveAuthorizationError("live_review_invalid") from exc
        if batch.request_id != request_id or batch.command_sha256 != row["command_sha256"]:
            raise LiveAuthorizationError("live_review_digest_mismatch")
        if target.digest() != row["target_digest"]:
            raise LiveAuthorizationError("live_review_target_mismatch")
        return LiveReview(
            request_id=batch.request_id,
            host_alias=target.host_id,
            hostname=target.hostname,
            port=target.port,
            ssh_username=target.username,
            host_public_key=target.host_public_key,
            working_directory=batch.working_directory,
            description=batch.description,
            commands=tuple(CommandReview(item.id, item.command, item.timeout_seconds)
                           for item in batch.commands),
            command_sha256=batch.command_sha256,
            target_digest=row["target_digest"],
            conversation_id=row["conversation_id"],
            tab_id=row["tab_id"],
        )

    def approve(self, review: LiveReview, password: str, *,
                full_batch_confirmed: bool, command_sha256: str) -> str:
        if type(review) is not LiveReview:
            raise LiveAuthorizationError("review_receipt_required")
        if full_batch_confirmed is not True or command_sha256 != review.command_sha256:
            raise LiveAuthorizationError("explicit_full_batch_confirmation_required")
        # Rebuild from the durable row to detect navigation/replacement/tampering
        # after display but before password validation and approval.
        current = self.prepare(review.request_id)
        if current != review:
            raise LiveAuthorizationError("review_changed")
        return self._flow.approve(review.request_id, password)
