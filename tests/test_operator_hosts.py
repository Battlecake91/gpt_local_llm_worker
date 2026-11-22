"""Operator-controlled host allowlist tests. No real SSH or network calls."""
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from worker.operator_hosts import (
    HostEnrollmentError, enroll_host, main, parse_public_host_key)
from worker.operator_review_gui import load_local_targets


def fixture_key_and_fingerprint():
    algorithm = b"ssh-ed25519"
    pub = bytes(range(32))
    wire = (len(algorithm).to_bytes(4, "big") + algorithm +
            len(pub).to_bytes(4, "big") + pub)
    key = "ssh-ed25519 " + base64.b64encode(wire).decode("ascii")
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(wire).digest()).decode("ascii").rstrip("=")
    return key, fingerprint


class HostEnrollmentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.config = root / "targets.json"
        self.key_file = root / "hostkey.pub"
        self.key, self.fingerprint = fixture_key_and_fingerprint()
        self.key_file.write_text(self.key + "\n", encoding="ascii")

    def enroll(self, **updates):
        args = dict(
            config_file=self.config, host_id="lab-nas",
            hostname="lab.example.invalid", port=2222,
            username="operator", key_file=self.key_file,
            expected_fingerprint=self.fingerprint,
        )
        args.update(updates)
        return enroll_host(**args)

    def test_verified_public_key_creates_allowlist_usable_by_review(self):
        target = self.enroll()
        self.assertEqual(target.host_public_key, self.key)
        loaded = load_local_targets(self.config)["lab-nas"]
        self.assertEqual(loaded, target)
        saved = self.config.read_text(encoding="utf-8")
        self.assertNotIn("PRIVATE KEY", saved)
        self.assertEqual(json.loads(saved)[0]["hostname"], "lab.example.invalid")

    def test_wrong_fingerprint_denies_creation(self):
        with self.assertRaisesRegex(HostEnrollmentError, "fingerprint_mismatch"):
            self.enroll(expected_fingerprint="SHA256:" + "A" * 43)
        self.assertFalse(self.config.exists())

    def test_valid_fingerprint_can_be_computed_but_not_trusted_automatically(self):
        self.assertEqual(parse_public_host_key(self.key, self.fingerprint),
                         self.key)
        with self.assertRaisesRegex(HostEnrollmentError, "fingerprint_mismatch"):
            parse_public_host_key(self.key, "SHA256:" + "B" * 43)

    def test_invalid_key_algorithm_and_payload_denied(self):
        self.key_file.write_text("ssh-ed25519 Zm9v\n", encoding="ascii")
        with self.assertRaisesRegex(HostEnrollmentError, "invalid_host_key"):
            self.enroll()
        self.assertFalse(self.config.exists())
        self.key_file.write_text(self.key.replace("ssh-ed25519 ", "ssh-rsa "), encoding="ascii")
        with self.assertRaisesRegex(HostEnrollmentError, "host_key_algorithm_mismatch"):
            self.enroll()

    def test_existing_verified_allowlist_not_overwritten(self):
        self.enroll()
        prior = self.config.read_bytes()
        with self.assertRaisesRegex(HostEnrollmentError, "allowlist_already_exists"):
            self.enroll(hostname="other.example.invalid")
        self.assertEqual(self.config.read_bytes(), prior)

    def test_existing_unrecognized_file_not_overwritten(self):
        self.config.write_bytes(b"invalid-do-not-replace")
        with self.assertRaisesRegex(HostEnrollmentError, "allowlist_already_exists"):
            self.enroll()
        self.assertEqual(self.config.read_bytes(), b"invalid-do-not-replace")

    def test_invalid_host_and_username_denied(self):
        for changes in (
            {"host_id": "bad host"},
            {"hostname": "bad/host"},
            {"username": "root;id"},
            {"port": 0},
            {"port": True},
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(HostEnrollmentError, "invalid_host_configuration"):
                    self.enroll(**changes)
                self.assertFalse(self.config.exists())

    def test_relative_and_missing_key_path_denied(self):
        with self.assertRaisesRegex(HostEnrollmentError, "invalid_host_file_path"):
            self.enroll(config_file=Path("relative.json"))
        with self.assertRaisesRegex(HostEnrollmentError, "invalid_host_file_path"):
            self.enroll(key_file=self.key_file.parent / "absent.pub")

    def test_cli_creates_local_allowlist_without_network(self):
        code = main([
            "--targets", str(self.config),
            "--alias", "lab-nas",
            "--hostname", "lab.example.invalid",
            "--port", "2222",
            "--username", "operator",
            "--host-key-file", str(self.key_file),
            "--fingerprint", self.fingerprint,
        ])
        self.assertEqual(code, 0)
        self.assertEqual(load_local_targets(self.config)["lab-nas"].username,
                         "operator")


if __name__ == "__main__":
    unittest.main()
