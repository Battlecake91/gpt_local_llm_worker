"""Strictly offline transport contract tests; fake runner never spawns ssh."""
import base64
import io
import subprocess
import tempfile
from unittest.mock import patch
import unittest
from pathlib import Path

from worker.ssh_transport import (
    SSHHostConfig, SSHTransport, SSHTransportError, SSHRunResult,
    OpenSSHRunner, pinned_known_hosts, remote_command, ssh_argv,
)


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.known_hosts_content = None

    def run(self, argv, timeout_seconds, max_output_bytes):
        self.calls.append((argv, timeout_seconds, max_output_bytes))
        idx = next(i for i, arg in enumerate(argv) if arg.startswith("UserKnownHostsFile="))
        self.known_hosts_content = Path(argv[idx].split("=", 1)[1]).read_text()
        return SSHRunResult(0, "fixture only", "", False, False)


class SSHTransportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.identity = self.folder / "identity"
        self.identity.write_text("FAKE KEY, NOT A REAL PRIVATE KEY")
        # Well-formed key format only; a fake runner never opens network.
        self.key = "ssh-ed25519 " + base64.b64encode(b"fake-public-key-material" * 3).decode()
        self.config = SSHHostConfig(
            "isolated-test", "test.example.invalid", "testuser", 2222, self.identity, self.key)

    def test_fake_transport_uses_exact_pin_and_strict_ssh_options(self):
        runner = FakeRunner()
        transport = SSHTransport({"isolated-test": self.config}, runner=runner)
        reply = transport.run_command("isolated-test", "/tmp/has space", "printf 'ok'", 8)
        self.assertEqual(reply.stdout, "fixture only")
        argv, timeout, budget = runner.calls[0]
        self.assertEqual(argv[0:3], ["ssh", "-F", "none"])
        self.assertEqual(argv[-2], "testuser@test.example.invalid")
        self.assertEqual(argv[-1], "cd -- '/tmp/has space' && printf 'ok'")
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertIn("IdentitiesOnly=yes", argv)
        self.assertIn("IdentityAgent=none", argv)
        self.assertIn("ClearAllForwardings=yes", argv)
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("ForwardAgent=no", argv)
        self.assertEqual(timeout, 8)
        self.assertEqual(budget, 16384)
        self.assertEqual(runner.known_hosts_content,
                         "[test.example.invalid]:2222 " + self.key + "\n")
        pin_arg = next(arg for arg in argv if arg.startswith("UserKnownHostsFile="))
        self.assertFalse(Path(pin_arg.split("=", 1)[1]).exists())

    def test_default_port_known_hosts_record(self):
        cfg = SSHHostConfig("isolated-test", "test.example.invalid", "testuser", 22,
                            self.identity, self.key)
        self.assertEqual(pinned_known_hosts(cfg), "test.example.invalid " + self.key + "\n")

    def test_unknown_host_fails_before_runner(self):
        runner = FakeRunner()
        transport = SSHTransport({"isolated-test": self.config}, runner=runner)
        with self.assertRaisesRegex(SSHTransportError, "host_not_allowlisted"):
            transport.run_command("nas", "/tmp", "id", 4)
        self.assertFalse(runner.calls)

    def test_invalid_cwd_and_timeout_fail_before_runner(self):
        runner = FakeRunner()
        transport = SSHTransport({"isolated-test": self.config}, runner=runner)
        for cwd in ("relative", "/tmp/../etc", "/tmp\rname", "/tmp\x00name"):
            with self.subTest(cwd=cwd):
                with self.assertRaises(SSHTransportError):
                    transport.run_command("isolated-test", cwd, "id", 4)
        for timeout in (0, 301, True, 3.5):
            with self.subTest(timeout=timeout):
                with self.assertRaises(SSHTransportError):
                    transport.run_command("isolated-test", "/tmp", "id", timeout)
        self.assertFalse(runner.calls)

    def test_untrusted_cwd_is_quoted_but_approved_command_is_unchanged(self):
        self.assertEqual(
            remote_command("/tmp/a'b; touch /tmp/x", "printf 'hello'; id"),
            "cd -- '/tmp/a'\"'\"'b; touch /tmp/x' && printf 'hello'; id")

    def test_incomplete_host_config_rejected(self):
        with self.assertRaisesRegex(SSHTransportError, "identity_file_missing"):
            SSHHostConfig("isolated-test", "test.example.invalid", "testuser", 22,
                          self.folder / "does-not-exist", self.key)
        with self.assertRaisesRegex(SSHTransportError, "invalid_host_public_key"):
            SSHHostConfig("isolated-test", "test.example.invalid", "testuser", 22,
                          self.identity, "SHA256:fakefingerprint")
        with self.assertRaisesRegex(SSHTransportError, "invalid_username"):
            SSHHostConfig("isolated-test", "test.example.invalid", "bad user", 22,
                          self.identity, self.key)
        with self.assertRaisesRegex(SSHTransportError, "invalid_port"):
            SSHHostConfig("isolated-test", "test.example.invalid", "testuser", 0,
                          self.identity, self.key)

    def test_runner_enforces_output_byte_limit_with_fake_process(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = io.BytesIO(b"A" * 8192)
                self.stderr = io.BytesIO(b"B" * 8192)
                self.returncode = 0
                self.killed = False

            def wait(self, timeout=None):
                if self.killed:
                    self.returncode = -9
                return self.returncode

            def kill(self):
                self.killed = True

        fake = FakeProcess()
        with patch("worker.ssh_transport.subprocess.Popen", return_value=fake):
            result = OpenSSHRunner().run(["ssh", "FAKE ONLY"], 5, 1024)
        self.assertTrue(result.truncated)
        self.assertLessEqual(len(result.stdout.encode()) + len(result.stderr.encode()), 1024)
        self.assertTrue(fake.killed)

    def test_utf8_boundary_never_expands_bounded_output(self):
        from worker.ssh_transport import _decode
        self.assertEqual(_decode("ä".encode("utf-8")[:1]), "")
        self.assertLessEqual(len(_decode(b"\\xff" * 100).encode("utf-8")), 100)

    def test_runner_marks_actual_wait_timeout_with_fake_process(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = io.BytesIO(b"")
                self.stderr = io.BytesIO(b"")
                self.returncode = None
                self.killed = False

            def wait(self, timeout=None):
                if not self.killed:
                    raise subprocess.TimeoutExpired("ssh", timeout)
                self.returncode = -9
                return self.returncode

            def kill(self):
                self.killed = True

        fake = FakeProcess()
        with patch("worker.ssh_transport.subprocess.Popen", return_value=fake):
            result = OpenSSHRunner().run(["ssh", "FAKE ONLY"], 1, 1024)
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertTrue(fake.killed)

    def test_runner_rejects_bad_limits_without_spawning(self):
        runner = OpenSSHRunner()
        for timeout, budget in ((0, 1024), (301, 1024), (1, 0), (1, 20000)):
            with self.subTest(timeout=timeout, budget=budget):
                with self.assertRaises(SSHTransportError):
                    runner.run(["ssh"], timeout, budget)


if __name__ == "__main__":
    unittest.main()
