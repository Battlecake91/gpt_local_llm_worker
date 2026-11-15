"""Unwired SSH transport contract. No live endpoint, scheduler or CLI enables this.

Hosts are configured by the operator, not the model. Tests inject a fake runner.
OpenSSH supplies strict host-key verification against an isolated pinned key file.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
KEY_TYPES = {"ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
             "ecdsa-sha2-nistp521", "rsa-sha2-256", "rsa-sha2-512", "ssh-rsa"}
MAX_STREAM_BYTES = 16_384


class SSHTransportError(ValueError):
    pass


@dataclass(frozen=True)
class SSHHostConfig:
    alias: str
    hostname: str
    username: str
    port: int
    identity_file: Path
    host_public_key: str

    def __post_init__(self):
        if not HOST_RE.fullmatch(self.alias) or not HOST_RE.fullmatch(self.hostname):
            raise SSHTransportError("invalid_host")
        if not USER_RE.fullmatch(self.username):
            raise SSHTransportError("invalid_username")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise SSHTransportError("invalid_port")
        identity = Path(self.identity_file)
        if not identity.is_absolute() or not identity.is_file():
            raise SSHTransportError("identity_file_missing")
        if identity.is_symlink():
            raise SSHTransportError("identity_file_symlink_denied")
        parts = self.host_public_key.split()
        if len(parts) != 2 or parts[0] not in KEY_TYPES:
            raise SSHTransportError("invalid_host_public_key")
        try:
            decoded = base64.b64decode(parts[1], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SSHTransportError("invalid_host_public_key") from exc
        if not 32 <= len(decoded) <= 8192:
            raise SSHTransportError("invalid_host_public_key")


@dataclass(frozen=True)
class SSHRunResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool


def remote_command(cwd: str, command: str) -> str:
    """Remote shell is unavoidable for SSH commands; quote CWD, keep command exact."""
    if not isinstance(cwd, str) or not cwd.startswith("/") or "\x00" in cwd or "\r" in cwd or ".." in cwd.split("/"):
        raise SSHTransportError("invalid_working_directory")
    if not isinstance(command, str) or not command.strip() or "\x00" in command or "\r" in command:
        raise SSHTransportError("invalid_command")
    return "cd -- " + shlex.quote(cwd) + " && " + command


def pinned_known_hosts(config: SSHHostConfig) -> str:
    name = config.hostname if config.port == 22 else f"[{config.hostname}]:{config.port}"
    return name + " " + config.host_public_key + "\n"


def ssh_argv(config: SSHHostConfig, known_hosts_path: Path, cwd: str, command: str) -> list[str]:
    if not known_hosts_path.is_absolute():
        raise SSHTransportError("known_hosts_path_not_absolute")
    # -F none disables ambient per-user SSH config. Pinned key and private key
    # are passed as argv elements, never interpolated into a local shell.
    return [
        "ssh", "-F", "none", "-T", "-p", str(config.port), "-i", str(config.identity_file),
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "CheckHostIP=no", "-o", "GlobalKnownHostsFile=none",
        "-o", f"UserKnownHostsFile={known_hosts_path}",
        "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
        "-o", "ForwardAgent=no", "-o", "ForwardX11=no",
        "-o", "PermitLocalCommand=no", "-o", "ClearAllForwardings=yes",
        "-o", "ControlMaster=no", "-o", "UpdateHostKeys=no",
        "-o", "ConnectTimeout=10", "-o", "NumberOfPasswordPrompts=0",
        "--", f"{config.username}@{config.hostname}", remote_command(cwd, command)
    ]


def _decode(value: bytes) -> str:
    return value.decode("utf-8", errors="replace")


class OpenSSHRunner:
    """Streaming bounded subprocess adapter. Not invoked by the live application."""

    def run(self, argv: list[str], timeout_seconds: int, max_output_bytes: int) -> SSHRunResult:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise SSHTransportError("invalid_timeout")
        if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_STREAM_BYTES:
            raise SSHTransportError("invalid_output_limit")
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   shell=False)
        buffers = [bytearray(), bytearray()]
        overflow = threading.Event()
        output_lock = threading.Lock()

        def consume(stream, index):
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    # Protect the combined byte budget across both reader threads.
                    with output_lock:
                        left = max_output_bytes - sum(len(buf) for buf in buffers)
                        if left > 0:
                            buffers[index].extend(chunk[:left])
                        exceeded = len(chunk) > left
                        if exceeded:
                            overflow.set()
                    if exceeded:
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
                        break
            finally:
                stream.close()

        readers = [threading.Thread(target=consume, args=(process.stdout, 0), daemon=True),
                   threading.Thread(target=consume, args=(process.stderr, 1), daemon=True)]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            process.wait()
        for reader in readers:
            reader.join(timeout=2)
        if any(reader.is_alive() for reader in readers):
            # Unknown state is safer than returning incomplete output as success.
            raise SSHTransportError("ssh_output_reader_incomplete")
        return SSHRunResult(
            None if timed_out else process.returncode,
            _decode(bytes(buffers[0])), _decode(bytes(buffers[1])),
            timed_out, overflow.is_set())


class SSHTransport:
    """Unwired OpenSSH transport; caller must independently enforce approval."""

    def __init__(self, hosts: dict[str, SSHHostConfig], runner=None):
        for alias, cfg in hosts.items():
            if alias != cfg.alias:
                raise SSHTransportError("host_alias_mismatch")
        self.hosts = dict(hosts)
        self.runner = runner if runner is not None else OpenSSHRunner()

    def run_command(self, host_alias: str, cwd: str, command: str, timeout_seconds: int) -> SSHRunResult:
        if host_alias not in self.hosts:
            raise SSHTransportError("host_not_allowlisted")
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 300:
            raise SSHTransportError("invalid_timeout")
        config = self.hosts[host_alias]
        # Temporary known_hosts is created with restrictive permissions and
        # removed immediately after the invocation, including on failure.
        with tempfile.TemporaryDirectory(prefix="gpt-ssh-pin-") as temp_dir:
            path = Path(temp_dir) / "known_hosts"
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="ascii") as file:
                file.write(pinned_known_hosts(config))
            argv = ssh_argv(config, path, cwd, command)
            return self.runner.run(argv, timeout_seconds, MAX_STREAM_BYTES)
