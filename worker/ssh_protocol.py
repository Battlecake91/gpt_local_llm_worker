"""Pure, non-executing SSH request parser. Untrusted model text never grants approval."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

MAX_REPLY = 256_000
MAX_COMMANDS = 32
MAX_COMMAND_SIZE = 8_192
HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
FENCE_PATTERN = re.compile(r"(?ms)^```json[ \t]*\n(.*?)\n```[ \t]*$")


class InvalidSSHRequest(ValueError):
    """Reject malformed, unexpected or non-allowlisted SSH requests."""


@dataclass(frozen=True)
class SSHBatchRequest:
    request_id: str
    host_id: str
    commands: tuple[str, ...]
    command_sha256: str


def _unpack(text: str) -> object:
    if not isinstance(text, str) or not text or len(text) > MAX_REPLY:
        raise InvalidSSHRequest("invalid_reply_length")
    candidates = FENCE_PATTERN.findall(text)
    if len(candidates) > 1:
        raise InvalidSSHRequest("ambiguous_json_blocks")
    if candidates:
        text = candidates[0]
    try:
        return json.loads(text)
    except (ValueError, TypeError) as exc:
        raise InvalidSSHRequest("invalid_json") from exc


def parse_ssh_request(text: str, allowed_hosts: set[str] | frozenset[str]) -> SSHBatchRequest:
    """Validate a structured SSH batch; do not connect, execute or approve anything.

    A complete JSON object, or exactly one fenced JSON object embedded in a response,
    is accepted. Only names from operator configuration are allowed as destinations.
    """
    obj = _unpack(text)
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "type", "request_id", "host_id", "commands"}:
        raise InvalidSSHRequest("unexpected_request_shape")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1 or obj["type"] != "ssh_batch_request":
        raise InvalidSSHRequest("wrong_request_type")
    request_id, host_id, commands = obj["request_id"], obj["host_id"], obj["commands"]
    if not isinstance(request_id, str) or not ID_PATTERN.fullmatch(request_id):
        raise InvalidSSHRequest("invalid_request_id")
    if not isinstance(host_id, str) or not HOST_PATTERN.fullmatch(host_id) or host_id not in allowed_hosts:
        raise InvalidSSHRequest("host_not_allowlisted")
    if not isinstance(commands, list) or not 1 <= len(commands) <= MAX_COMMANDS:
        raise InvalidSSHRequest("invalid_command_count")
    for command in commands:
        if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_SIZE:
            raise InvalidSSHRequest("invalid_command")
        if "\x00" in command or "\r" in command:
            raise InvalidSSHRequest("invalid_command_control")
    # The digest commits to host AND the entire ordered block, never a single line.
    binding = {"schema_version": 1, "host_id": host_id, "commands": commands}
    canonical = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SSHBatchRequest(request_id, host_id, tuple(commands), hashlib.sha256(canonical).hexdigest())
