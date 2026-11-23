"""Pure SSH proposal parser for docs/protocol.md v1. Never runs shell commands."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

MAX_REPLY = 256_000
MAX_COMMANDS = 32
MAX_COMMAND_SIZE = 8_192
MAX_TIMEOUT_SECONDS = 300
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
FENCE_PATTERN = re.compile(r"(?ms)^```json[ \t]*\n(.*?)\n```[ \t]*$")


class InvalidSSHRequest(ValueError):
    """Reject malformed, unexpected or non-allowlisted SSH requests."""


@dataclass(frozen=True)
class SSHCommand:
    id: str
    command: str
    timeout_seconds: int


@dataclass(frozen=True)
class SSHBatchRequest:
    request_id: str
    host_id: str
    working_directory: str
    commands: tuple[SSHCommand, ...]
    description: str
    command_sha256: str


def _unpack(text: str) -> object:
    if not isinstance(text, str) or not text or len(text) > MAX_REPLY:
        raise InvalidSSHRequest("invalid_reply_length")
    candidates = FENCE_PATTERN.findall(text)
    if len(candidates) > 1:
        raise InvalidSSHRequest("ambiguous_json_blocks")
    if candidates:
        text = candidates[0][1]

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise InvalidSSHRequest("duplicate_json_key")
            obj[key] = value
        return obj

    try:
        return json.loads(text, object_pairs_hook=no_duplicates)
    except InvalidSSHRequest:
        raise
    except (ValueError, TypeError) as exc:
        raise InvalidSSHRequest("invalid_json") from exc


def parse_ssh_request(text: str, allowed_hosts: set[str] | frozenset[str]) -> SSHBatchRequest:
    """Parse an explicit batch, without authorization or execution."""
    obj = _unpack(text)
    if not isinstance(obj, dict) or set(obj) != {
        "schema_version", "kind", "request_id", "target", "working_directory",
        "commands", "description"
    }:
        raise InvalidSSHRequest("unexpected_request_shape")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1 or obj["kind"] != "ssh_batch":
        raise InvalidSSHRequest("wrong_request_type")
    request_id, host_id = obj["request_id"], obj["target"]
    if not isinstance(request_id, str) or not ID_PATTERN.fullmatch(request_id):
        raise InvalidSSHRequest("invalid_request_id")
    if not isinstance(host_id, str) or not HOST_PATTERN.fullmatch(host_id) or host_id not in allowed_hosts:
        raise InvalidSSHRequest("host_not_allowlisted")
    cwd = obj["working_directory"]
    if (not isinstance(cwd, str) or not cwd.startswith("/") or
            len(cwd) > 1_024 or "\x00" in cwd or "\r" in cwd or
            ".." in cwd.split("/")):
        raise InvalidSSHRequest("invalid_working_directory")
    description = obj["description"]
    if not isinstance(description, str) or len(description) > 1_000:
        raise InvalidSSHRequest("invalid_description")
    raw_commands = obj["commands"]
    if not isinstance(raw_commands, list) or not 1 <= len(raw_commands) <= MAX_COMMANDS:
        raise InvalidSSHRequest("invalid_command_count")
    commands = []
    ids = set()
    for item in raw_commands:
        if not isinstance(item, dict) or set(item) != {"id", "command", "timeout_seconds"}:
            raise InvalidSSHRequest("invalid_command_shape")
        command_id, command, timeout = item["id"], item["command"], item["timeout_seconds"]
        if not isinstance(command_id, str) or not ID_PATTERN.fullmatch(command_id) or command_id in ids:
            raise InvalidSSHRequest("invalid_command_id")
        if (not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_SIZE or
                "\x00" in command or "\r" in command):
            raise InvalidSSHRequest("invalid_command")
        if type(timeout) is not int or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
            raise InvalidSSHRequest("invalid_command_timeout")
        ids.add(command_id)
        commands.append(SSHCommand(command_id, command, timeout))
    # The approved digest commits to the target, cwd, every command with its
    # timeout, and the description visible to the operator.
    binding = {
        "schema_version": 1, "target": host_id, "working_directory": cwd,
        "commands": [{"id": c.id, "command": c.command, "timeout_seconds": c.timeout_seconds}
                     for c in commands],
        "description": description,
    }
    canonical = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SSHBatchRequest(request_id, host_id, cwd, tuple(commands), description,
                           hashlib.sha256(canonical).hexdigest())
