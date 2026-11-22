"""Local ssh -G / ssh-keygen -F importer tests, subprocess fully mocked."""
import base64
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from worker.operator_hosts import HostEnrollmentError
from worker.operator_ssh_import import import_aliases, inspect_alias
from worker.operator_review_gui import load_local_targets


ALIAS_CONFIG = {
    "nas": ("192.168.0.100", "steven", "22"),
    "backup-nas": ("192.168.0.101", "steven", "22"),
    "vserver": ("87.106.7.53", "steven", "22"),
}


def fixture_key(seed):
    typ = b"ssh-ed25519"
    pub = bytes([seed]) * 32
    data = (len(typ).to_bytes(4, "big") + typ +
            len(pub).to_bytes(4, "big") + pub)
    key = "ssh-ed25519 " + base64.b64encode(data).decode("ascii")
    fp = "SHA256:" + base64.b64encode(
        hashlib.sha256(data).digest()).decode("ascii").rstrip("=")
    return key, fp


class FakeLocalRunner:
    def __init__(self):
        self.keys = {}
        self.fingerprints = {}
        self.calls = []
        for i, alias in enumerate(ALIAS_CONFIG, 1):
            self.keys[alias], self.fingerprints[alias] = fixture_key(i)

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if argv[:2] == ["ssh", "-G"]:
            hostname, username, port = ALIAS_CONFIG[argv[2]]
            stdout = (f"hostname {hostname}\nuser {username}\nport {port}\n"
                      f"identityfile ~/.ssh/id_ed25519_{argv[2]}\n")
        elif argv[:2] == ["ssh-keygen", "-F"]:
            alias = next(alias for alias, cfg in ALIAS_CONFIG.items()
                         if cfg[0] == argv[2])
            stdout = (f"# Host {argv[2]} found\n"
                      f"{argv[2]} {self.keys[alias]}\n")
        else:
            raise AssertionError("Unexpected command")
        return subprocess.CompletedProcess(argv, 0, stdout, "")


class SSHImportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "targets.json"
        self.runner = FakeLocalRunner()

    def test_three_host_import_reuses_exact_existing_aliases(self):
        targets = import_aliases(
            self.path, dict(self.runner.fingerprints), runner=self.runner)
        self.assertEqual(set(targets), set(ALIAS_CONFIG))
        self.assertEqual(load_local_targets(self.path), targets)
        self.assertEqual(targets["nas"].hostname, "192.168.0.100")
        self.assertEqual(targets["backup-nas"].hostname, "192.168.0.101")
        self.assertEqual(targets["vserver"].hostname, "87.106.7.53")
        self.assertTrue(all(target.username == "steven" for target in targets.values()))
        self.assertEqual(len(self.runner.calls), 6)
        self.assertTrue(all(call[:2] in (["ssh", "-G"], ["ssh-keygen", "-F"])
                            for call in self.runner.calls))

    def test_wrong_confirmation_blocks_entire_import(self):
        confirmed = dict(self.runner.fingerprints, vserver="SHA256:" + "X" * 43)
        with self.assertRaisesRegex(HostEnrollmentError, "fingerprint_mismatch"):
            import_aliases(self.path, confirmed, runner=self.runner)
        self.assertFalse(self.path.exists())

    def test_partial_confirmation_is_not_accepted(self):
        with self.assertRaisesRegex(
                HostEnrollmentError, "exact_three_host_confirmations_required"):
            import_aliases(self.path, {"nas": self.runner.fingerprints["nas"]},
                           runner=self.runner)
        self.assertEqual(self.runner.calls, [])

    def test_preexisting_allowlist_remains_untouched(self):
        self.path.write_bytes(b"do-not-touch")
        with self.assertRaisesRegex(HostEnrollmentError, "allowlist_already_exists"):
            import_aliases(self.path, self.runner.fingerprints, runner=self.runner)
        self.assertEqual(self.path.read_bytes(), b"do-not-touch")

    def test_ambiguous_ed25519_entries_denied(self):
        original = self.runner
        def runner(argv, **kwargs):
            result = original(argv, **kwargs)
            if argv == ["ssh-keygen", "-F", "192.168.0.100"]:
                key, _ = fixture_key(99)
                result.stdout += f"192.168.0.100 {key}\n"
            return result
        with self.assertRaisesRegex(
                HostEnrollmentError, "ed25519_known_host_key_missing_or_ambiguous"):
            import_aliases(self.path, self.runner.fingerprints, runner=runner)
        self.assertFalse(self.path.exists())

    def test_single_host_inspection_keeps_network_disabled(self):
        target = inspect_alias("nas", self.runner.fingerprints["nas"],
                               runner=self.runner)
        self.assertEqual(target.host_id, "nas")
        self.assertEqual(self.runner.calls, [
            ["ssh", "-G", "nas"], ["ssh-keygen", "-F", "192.168.0.100"]])


if __name__ == "__main__":
    unittest.main()
