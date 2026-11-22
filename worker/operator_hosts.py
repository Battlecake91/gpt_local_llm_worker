"""Local, operator-controlled SSH host allowlist setup. No network access.

The key must be obtained and its fingerprint confirmed independently through
a trusted device/server console. ssh-keyscan alone is NOT trusted evidence.
This module never invokes SSH or probes a host.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
from pathlib import Path

from worker.live_approval import LiveTargetBinding
from worker.operator_review_gui import load_local_targets
from worker.ssh_transport import HOST_RE, USER_RE, KEY_TYPES

_FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
_MAX_KEY_FILE_BYTES = 16384


class HostEnrollmentError(ValueError):
    pass


def parse_public_host_key(source: str, fingerprint: str) -> str:
    """Validate a complete OpenSSH public key and its out-of-band fingerprint."""
    if not isinstance(source, str) or not isinstance(fingerprint, str):
        raise HostEnrollmentError("invalid_host_key")
    if "\\n" in source.strip() or "\\r" in source.strip():
        raise HostEnrollmentError("invalid_host_key")
    # OpenSSH .pub files may contain an optional human-readable comment.
    parts = source.strip().split()
    if len(parts) < 2 or parts[0] not in KEY_TYPES:
        raise HostEnrollmentError("invalid_host_key")
    try:
        raw = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HostEnrollmentError("invalid_host_key") from exc
    if not 32 <= len(raw) <= 8192:
        raise HostEnrollmentError("invalid_host_key")
    # SSH wire format starts with a length-prefixed algorithm identifier.
    name_len = int.from_bytes(raw[:4], "big")
    if not 1 <= name_len <= 128 or len(raw) < 4 + name_len:
        raise HostEnrollmentError("invalid_host_key")
    try:
        embedded_algorithm = raw[4:4 + name_len].decode("ascii")
    except UnicodeDecodeError as exc:
        raise HostEnrollmentError("invalid_host_key") from exc
    accepted_wire_names = {"ssh-rsa"} if parts[0] in {"rsa-sha2-256", "rsa-sha2-512", "ssh-rsa"} else {parts[0]}
    if embedded_algorithm not in accepted_wire_names:
        raise HostEnrollmentError("host_key_algorithm_mismatch")
    encoded = base64.b64encode(raw).decode("ascii")
    normalized = f"{parts[0]} {encoded}"
    computed = "SHA256:" + base64.b64encode(
        hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    if not _FINGERPRINT.fullmatch(fingerprint) or computed != fingerprint:
        raise HostEnrollmentError("host_key_fingerprint_mismatch")
    return normalized


def enroll_host(
    config_file: Path,
    *,
    host_id: str,
    hostname: str,
    port: int,
    username: str,
    key_file: Path,
    expected_fingerprint: str,
) -> LiveTargetBinding:
    """Create one new allowlist, never overwrite an existing configuration."""
    config_file = Path(config_file)
    key_file = Path(key_file)
    if (not config_file.is_absolute() or not key_file.is_absolute()
            or config_file.is_symlink() or config_file.parent.is_symlink()
            or key_file.is_symlink() or not key_file.is_file()
            or not config_file.parent.is_dir()):
        raise HostEnrollmentError("invalid_host_file_path")
    if (type(host_id) is not str or not HOST_RE.fullmatch(host_id)
            or type(hostname) is not str or not HOST_RE.fullmatch(hostname)
            or type(username) is not str or not USER_RE.fullmatch(username)
            or type(port) is not int or not 1 <= port <= 65535):
        raise HostEnrollmentError("invalid_host_configuration")
    if key_file.stat().st_size > _MAX_KEY_FILE_BYTES:
        raise HostEnrollmentError("invalid_host_key")
    try:
        key = parse_public_host_key(key_file.read_text(encoding="ascii"),
                                    expected_fingerprint)
    except (UnicodeError, OSError) as exc:
        raise HostEnrollmentError("invalid_host_key") from exc
    target = LiveTargetBinding(host_id, hostname, port, username, key)

    if config_file.exists():
        # Existing allowlist is read only by default; fail closed rather than
        # overwriting a previously verified identity. Further hosts can be
        # deliberately installed via a separate future atomic update workflow.
        raise HostEnrollmentError("allowlist_already_exists")
    data = json.dumps([{
        "host_id": target.host_id,
        "hostname": target.hostname,
        "port": target.port,
        "username": target.username,
        "host_public_key": target.host_public_key,
    }], ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    fd = os.open(config_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        loaded = load_local_targets(config_file)
        if loaded.get(host_id) != target:
            raise HostEnrollmentError("host_configuration_roundtrip_failed")
    except BaseException:
        # Never erase the file silently when another process can have observed
        # it. Leave any partial file for manual inspection.
        raise
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Create one trusted SSH host allowlist entry (no SSH calls)")
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--username", required=True)
    parser.add_argument("--host-key-file", required=True, type=Path)
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args(argv)
    try:
        target = enroll_host(
            args.targets, host_id=args.alias, hostname=args.hostname,
            port=args.port, username=args.username, key_file=args.host_key_file,
            expected_fingerprint=args.fingerprint)
    except HostEnrollmentError as exc:
        parser.error(str(exc))
    print("Host-Allowlist angelegt:", args.targets)
    print("Ziel:", f"{target.username}@{target.hostname}:{target.port}")
    print("Fingerprint:", args.fingerprint)
    print("Keine SSH-Verbindung hergestellt; LIVE-Ausführung deaktiviert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
