"""Manual, local-only operator enrollment. No SSH, browser or API endpoints.

Run: python -m worker.operator_setup --state-dir ABSOLUTE_PATH --operator-id ID
Prompts on the local terminal; does not take passwords from argv or environment.
"""
from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
from pathlib import Path

from worker.operator_auth import OperatorAuthError, create_password_record
from worker.operator_credentials import CredentialStorageError, OperatorCredentialFile
from worker.operator_rate_limit import PersistentOperatorVerifier
from worker.operator_auth import OperatorAuthenticator


class OperatorSetupError(ValueError):
    pass


def prepare_state_directory(path: Path):
    """Create a private local directory, never modify a public directory."""
    if not path.is_absolute() or path.is_symlink() or path.parent.is_symlink():
        raise OperatorSetupError("invalid_state_directory")
    if path.exists():
        if not path.is_dir():
            raise OperatorSetupError("invalid_state_directory")
    else:
        path.mkdir(mode=0o700, parents=False)
    if sys.platform != "win32":
        meta = path.stat()
        if meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) & 0o077:
            raise OperatorSetupError("state_directory_not_private")


def enroll_operator(state_dir: Path, operator_id: str, secret: str, confirmation: str):
    """Explicit one-time enrollment, no replace, no automatic SSH enablement."""
    if not isinstance(secret, str) or secret != confirmation:
        raise OperatorSetupError("password_confirmation_mismatch")
    if not state_dir.is_absolute():
        raise OperatorSetupError("invalid_state_directory")
    credentials = state_dir / "operator-credential.json"
    rate_db = state_dir / "operator-rate-limit.sqlite3"
    if credentials.exists() or credentials.is_symlink() or rate_db.exists():
        raise OperatorSetupError("operator_already_configured")
    # Validate the operator and password *before* creating any state.
    record = create_password_record(operator_id, secret)
    prepare_state_directory(state_dir)
    if credentials.exists() or credentials.is_symlink() or rate_db.exists():
        raise OperatorSetupError("operator_already_configured")
    storage = OperatorCredentialFile(credentials)
    storage.create(record)
    try:
        PersistentOperatorVerifier(rate_db, OperatorAuthenticator(storage.load()))
    except BaseException:
        # Credentials remain for forensics/recovery, never auto-re-enroll.
        raise
    return credentials, rate_db


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Manually provision local operator verification (never enables SSH)")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--operator-id", required=True)
    args = parser.parse_args(argv)
    if not args.state_dir.is_absolute():
        parser.error("--state-dir must be an absolute path")
    if not sys.stdin.isatty():
        parser.error("a local interactive terminal is required")
    if (args.state_dir / "operator-credential.json").exists():
        parser.error("operator already enrolled; never overwrite credentials")
    first = getpass.getpass("Neues separates Betreiberpasswort: ")
    second = getpass.getpass("Passwort bestätigen: ")
    try:
        paths = enroll_operator(args.state_dir, args.operator_id, first, second)
    except (OperatorSetupError, OperatorAuthError, CredentialStorageError) as exc:
        parser.error(str(exc))
    finally:
        first = second = ""
    print("Betreiber-Credential und Rate-Limit-Datenbank eingerichtet.")
    print("Ablage:", args.state_dir)
    print("SSH und Brave-Auto-Send bleiben deaktiviert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
