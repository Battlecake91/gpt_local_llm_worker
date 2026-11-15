"""Local credential record storage. Not connected to an SSH or browser entry point.

On Windows the record is encrypted with per-user DPAPI before atomic storage.
On POSIX an owner-readable-only file is required. Password plaintext is never
written; the protected payload contains the salted scrypt verifier.
"""
from __future__ import annotations

import base64
import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from worker.operator_auth import OperatorPasswordRecord

FORMAT_VERSION = 1
MAX_RECORD_BYTES = 4096


class CredentialStorageError(ValueError):
    pass


class RecordProtector(Protocol):
    def protect(self, data: bytes) -> bytes: ...
    def unprotect(self, data: bytes) -> bytes: ...


class WindowsDPAPI:
    """CryptProtectData with user-scoped encryption; not a machine-wide secret."""

    @staticmethod
    def _call(data: bytes, *, encrypt: bool) -> bytes:
        if sys.platform != "win32":
            raise CredentialStorageError("dpapi_requires_windows")
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p

        source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        input_blob = Blob(len(data), source)
        output = Blob()
        # CRYPTPROTECT_UI_FORBIDDEN; no dialog or profile switching.
        flags = 0x01
        if encrypt:
            ok = crypt32.CryptProtectData(
                ctypes.byref(input_blob), "LLM Worker Operator", None,
                None, None, flags, ctypes.byref(output))
        else:
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(input_blob), None, None,
                None, None, flags, ctypes.byref(output))
        if not ok:
            raise CredentialStorageError("dpapi_operation_failed")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))

    def protect(self, data: bytes) -> bytes:
        return self._call(data, encrypt=True)

    def unprotect(self, data: bytes) -> bytes:
        return self._call(data, encrypt=False)


@dataclass(frozen=True)
class StoredCredential:
    version: int
    protection: str
    payload: bytes


def _encode(record: OperatorPasswordRecord) -> bytes:
    data = {
        "version": FORMAT_VERSION,
        "operator_id": record.operator_id,
        "salt": base64.b64encode(record.salt).decode("ascii"),
        "password_hash": base64.b64encode(record.password_hash).decode("ascii"),
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(data: bytes) -> OperatorPasswordRecord:
    try:
        if len(data) > MAX_RECORD_BYTES:
            raise ValueError("oversize")
        item = json.loads(data)
        if type(item) is not dict or set(item) != {"version", "operator_id", "salt", "password_hash"}:
            raise ValueError("wrong_shape")
        if type(item["version"]) is not int or item["version"] != FORMAT_VERSION:
            raise ValueError("wrong_version")
        return OperatorPasswordRecord(
            item["operator_id"],
            base64.b64decode(item["salt"], validate=True),
            base64.b64decode(item["password_hash"], validate=True))
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise CredentialStorageError("invalid_operator_record") from exc


class OperatorCredentialFile:
    """Write-once credential file, never auto-create or overwrite records.

    Windows: DPAPI encryption is mandatory. POSIX: plaintext verifier requires
    private mode 0600 and a non-symlink file. Both still require OS account
    protection; neither is an online authentication endpoint.
    """

    def __init__(self, path: Path | str, protector: RecordProtector | None = None):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise CredentialStorageError("credential_path_must_be_absolute")
        self.protector = protector if protector is not None else (
            WindowsDPAPI() if sys.platform == "win32" else None)

    def _check_location(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise CredentialStorageError("credential_symlink_denied")
        if not self.path.parent.is_dir():
            raise CredentialStorageError("credential_directory_missing")
        if sys.platform != "win32":
            directory = self.path.parent.stat()
            if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
                raise CredentialStorageError("credential_directory_insecure")

    def create(self, record: OperatorPasswordRecord):
        if type(record) is not OperatorPasswordRecord:
            raise CredentialStorageError("invalid_operator_record")
        self._check_location()
        if self.path.exists():
            raise CredentialStorageError("credential_already_exists")
        if sys.platform == "win32" and self.protector is None:
            raise CredentialStorageError("dpapi_required")
        payload = _encode(record)
        protection = "dpapi-user" if sys.platform == "win32" else "owner-file"
        if self.protector is not None:
            payload = self.protector.protect(payload)
            if type(payload) is not bytes:
                raise CredentialStorageError("invalid_protector_output")
        outer = json.dumps({
            "version": FORMAT_VERSION,
            "protection": protection,
            "payload": base64.b64encode(payload).decode("ascii"),
        }, separators=(",", ":")).encode("ascii")
        if len(outer) > MAX_RECORD_BYTES:
            raise CredentialStorageError("credential_too_large")
        # Exclusive create avoids overwriting even when racing another setup.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(outer)
                file.flush()
                os.fsync(file.fileno())
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise

    def load(self) -> OperatorPasswordRecord:
        self._check_location()
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags)
        with os.fdopen(fd, "rb") as file:
            mode = os.fstat(file.fileno()).st_mode
            if not stat.S_ISREG(mode):
                raise CredentialStorageError("credential_not_regular_file")
            if sys.platform != "win32":
                if mode & 0o077:
                    raise CredentialStorageError("credential_permissions_too_open")
                if os.fstat(file.fileno()).st_uid != os.getuid():
                    raise CredentialStorageError("credential_owner_mismatch")
            data = file.read(MAX_RECORD_BYTES + 1)
        try:
            if len(data) > MAX_RECORD_BYTES:
                raise ValueError("oversize")
            outer = json.loads(data)
            if type(outer) is not dict or set(outer) != {"version", "protection", "payload"}:
                raise ValueError("wrong_shape")
            if outer["version"] != FORMAT_VERSION:
                raise ValueError("wrong_version")
            expected = "dpapi-user" if sys.platform == "win32" else "owner-file"
            if outer["protection"] != expected:
                raise ValueError("wrong_protection")
            payload = base64.b64decode(outer["payload"], validate=True)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise CredentialStorageError("invalid_credential_file") from exc
        if self.protector is not None:
            payload = self.protector.unprotect(payload)
        return _decode(payload)
