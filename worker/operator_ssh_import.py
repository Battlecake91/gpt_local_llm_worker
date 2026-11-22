"""Offline import of existing OpenSSH aliases into LIVE review targets.

Only runs ssh -G (configuration display) and ssh-keygen -F (local known_hosts
lookup). Neither command makes an SSH connection. Caller must separately verify
each fingerprint at the server console; known_hosts alone proves no trust.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from worker.live_approval import LiveTargetBinding
from worker.operator_hosts import HostEnrollmentError, parse_public_host_key
from worker.operator_review_gui import load_local_targets
from worker.ssh_transport import HOST_RE, USER_RE

MAX_OUTPUT = 64_000


def _local_process(argv: list[str], *, runner=subprocess.run) -> str:
    try:
        result = runner(argv, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostEnrollmentError("local_ssh_config_command_failed") from exc
    if result.returncode != 0 or len(result.stdout) > MAX_OUTPUT:
        raise HostEnrollmentError("local_ssh_config_command_failed")
    return result.stdout


def _effective_config(alias: str, *, runner=subprocess.run) -> dict[str, str]:
    if type(alias) is not str or not HOST_RE.fullmatch(alias):
        raise HostEnrollmentError("invalid_ssh_alias")
    rows = {}
    for line in _local_process(["ssh", "-G", alias], runner=runner).splitlines():
        field, _, value = line.partition(" ")
        if field in {"hostname", "user", "port", "identityfile", "hostkeyalias",
                     "userknownhostsfile"} and value:
            rows.setdefault(field, value)
    if not all(x in rows for x in ("hostname", "user", "port")):
        raise HostEnrollmentError("incomplete_ssh_config")
    if not HOST_RE.fullmatch(rows["hostname"]) or not USER_RE.fullmatch(rows["user"]):
        raise HostEnrollmentError("unsupported_ssh_config")
    try:
        port = int(rows["port"])
    except ValueError as exc:
        raise HostEnrollmentError("unsupported_ssh_config") from exc
    if not 1 <= port <= 65535:
        raise HostEnrollmentError("unsupported_ssh_config")
    rows["port"] = str(port)
    # Reject special host-key aliases until they have their own verification path.
    if "hostkeyalias" in rows and rows["hostkeyalias"] not in {"none", rows["hostname"]}:
        raise HostEnrollmentError("custom_hostkeyalias_not_supported")
    return rows


def _known_host_key(hostname: str, port: int, *, runner=subprocess.run) -> str:
    lookup = hostname if port == 22 else f"[{hostname}]:{port}"
    output = _local_process(["ssh-keygen", "-F", lookup], runner=runner)
    keys = []
    for line in output.splitlines():
        if line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 3 and fields[1] == "ssh-ed25519":
            keys.append(" ".join(fields[1:3]))
    if len(set(keys)) != 1 or not keys:
        raise HostEnrollmentError("ed25519_known_host_key_missing_or_ambiguous")
    return keys[0]


def inspect_alias(alias: str, expected_fingerprint: str, *,
                  runner=subprocess.run) -> LiveTargetBinding:
    cfg = _effective_config(alias, runner=runner)
    hostkey = _known_host_key(cfg["hostname"], int(cfg["port"]), runner=runner)
    verified = parse_public_host_key(hostkey, expected_fingerprint)
    return LiveTargetBinding(
        alias, cfg["hostname"], int(cfg["port"]), cfg["user"], verified)


def import_aliases(path: Path, confirmed: dict[str, str], *,
                   runner=subprocess.run) -> dict[str, LiveTargetBinding]:
    """Create a three-host allowlist only after all fingerprints agree.

    Confirmed fingerprints must come from a separate trusted console. This
    method cannot determine whether the confirmation source is trustworthy.
    """
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or path.parent.is_symlink()
            or not path.parent.is_dir()):
        raise HostEnrollmentError("invalid_allowlist_path")
    if type(confirmed) is not dict or set(confirmed) != {"nas", "backup-nas", "vserver"}:
        raise HostEnrollmentError("exact_three_host_confirmations_required")
    if path.exists():
        raise HostEnrollmentError("allowlist_already_exists")
    targets = {alias: inspect_alias(alias, fingerprint, runner=runner)
               for alias, fingerprint in confirmed.items()}
    payload = [{
        "host_id": target.host_id, "hostname": target.hostname,
        "port": target.port, "username": target.username,
        "host_public_key": target.host_public_key,
    } for target in targets.values()]
    raw = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if load_local_targets(path) != targets:
        raise HostEnrollmentError("allowlist_roundtrip_failed")
    return targets


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Import 3 OpenSSH aliases only with separately verified host fingerprints")
    parser.add_argument("--targets", required=True, type=Path)
    for alias in ("nas", "backup-nas", "vserver"):
        parser.add_argument("--" + alias + "-fingerprint", required=True)
    args = parser.parse_args(argv)
    try:
        targets = import_aliases(args.targets, {
            "nas": args.nas_fingerprint,
            "backup-nas": args.backup_nas_fingerprint,
            "vserver": args.vserver_fingerprint,
        })
    except HostEnrollmentError as exc:
        parser.error(str(exc))
    for target in targets.values():
        print(f"{target.host_id}: {target.username}@{target.hostname}:{target.port}")
    print("Host-Allowlist angelegt. Kein SSH gestartet; LIVE-Executor bleibt deaktiviert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
