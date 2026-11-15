"""Persistent credential storage checks, isolated temporary files only."""
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from worker.operator_auth import OperatorAuthenticator, create_password_record
from worker.operator_credentials import (
    CredentialStorageError, OperatorCredentialFile, WindowsDPAPI,
)


class TestProtector:
    def protect(self, data):
        return bytes(b ^ 0x5A for b in data)

    def unprotect(self, data):
        return self.protect(data)


class CredentialFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "operator-credential.json"
        self.record = create_password_record(
            "test-operator", "isolated-long-test-passphrase-123")
        self.protector = TestProtector()

    def test_write_once_and_restart_loads_exact_record(self):
        storage = OperatorCredentialFile(self.path, protector=self.protector)
        storage.create(self.record)
        self.assertEqual(OperatorCredentialFile(
            self.path, protector=self.protector).load(), self.record)
        with self.assertRaisesRegex(CredentialStorageError, "already_exists"):
            storage.create(self.record)
        self.assertEqual(storage.load(), self.record)

    def test_record_never_stores_cleartext_password(self):
        storage = OperatorCredentialFile(self.path, protector=self.protector)
        storage.create(self.record)
        content = self.path.read_bytes()
        self.assertNotIn(b"isolated-long-test-passphrase-123", content)
        self.assertNotIn(self.record.password_hash, content)
        self.assertNotIn(self.record.salt, content)

    def test_malformed_files_fail_closed(self):
        for value in (
            b"invalid-json",
            b'{"version":2,"protection":"owner-file","payload":"eA=="}',
            b'{"version":1,"protection":"unknown","payload":"eA=="}',
            b'{"version":1,"protection":"owner-file","payload":"!"}',
            b"x" * 4097,
        ):
            with self.subTest(value=value[:20]):
                self.path.write_bytes(value)
                if sys.platform != "win32":
                    self.path.chmod(0o600)
                with self.assertRaises(CredentialStorageError):
                    OperatorCredentialFile(self.path, protector=self.protector).load()

    def test_no_relative_paths_and_missing_parent(self):
        with self.assertRaisesRegex(CredentialStorageError, "path_must_be_absolute"):
            OperatorCredentialFile("operator.json")
        missing = self.path.parent / "missing" / "credential.json"
        with self.assertRaisesRegex(CredentialStorageError, "directory_missing"):
            OperatorCredentialFile(missing, protector=self.protector).create(self.record)

    def test_file_is_private_on_posix(self):
        if sys.platform == "win32":
            self.skipTest("Windows uses DPAPI instead of POSIX mode bits")
        storage = OperatorCredentialFile(self.path, protector=self.protector)
        storage.create(self.record)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.path.chmod(0o644)
        with self.assertRaisesRegex(CredentialStorageError, "permissions_too_open"):
            storage.load()

    def test_symlink_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        target = self.path.parent / "target.json"
        target.write_text("keep", encoding="ascii")
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable for this Windows account")
        with self.assertRaisesRegex(CredentialStorageError, "symlink_denied"):
            OperatorCredentialFile(self.path, protector=self.protector).create(self.record)
        with self.assertRaisesRegex(CredentialStorageError, "symlink_denied"):
            OperatorCredentialFile(self.path, protector=self.protector).load()
        self.assertEqual(target.read_text(encoding="ascii"), "keep")

    def test_loaded_record_still_supports_offline_auth(self):
        storage = OperatorCredentialFile(self.path, protector=self.protector)
        storage.create(self.record)
        verified = OperatorAuthenticator(storage.load())
        ticket = verified.verify_for_proposal(
            "isolated-long-test-passphrase-123",
            request_id="fixture", command_sha256="a" * 64,
            target_digest="b" * 64, conversation_id="local", tab_id=7)
        self.assertEqual(verified.consume_for_proposal(
            ticket, request_id="fixture", command_sha256="a" * 64,
            target_digest="b" * 64, conversation_id="local", tab_id=7), "test-operator")

    def test_windows_default_protection_is_dpapi(self):
        if sys.platform != "win32":
            self.skipTest("native Windows DPAPI only")
        storage = OperatorCredentialFile(self.path)
        self.assertIsInstance(storage.protector, WindowsDPAPI)
        storage.create(self.record)
        self.assertEqual(OperatorCredentialFile(self.path).load(), self.record)
        self.assertNotIn(self.record.password_hash, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
