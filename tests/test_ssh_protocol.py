"""Offline schema tests; no SSH execution or browser use."""
import json
import unittest

from worker.ssh_protocol import InvalidSSHRequest, parse_ssh_request


def request(host="lab-nas", commands=None, cwd="/tmp"):
    return json.dumps({
        "schema_version": 1, "kind": "ssh_batch", "request_id": "req-42",
        "target": host, "working_directory": cwd,
        "commands": commands if commands is not None else [
            {"id": "host", "command": "uname -a", "timeout_seconds": 15},
            {"id": "disk", "command": "df -h", "timeout_seconds": 20},
        ], "description": "Systemzustand prüfen",
    })


class SSHProtocolTests(unittest.TestCase):
    def parse(self, text):
        return parse_ssh_request(text, {"lab-nas"})

    def test_valid_whole_batch_digest_and_stable_order(self):
        item = self.parse(request())
        self.assertEqual(item.host_id, "lab-nas")
        self.assertEqual(item.working_directory, "/tmp")
        self.assertEqual(item.commands[0].command, "uname -a")
        self.assertEqual(item.commands[1].timeout_seconds, 20)
        self.assertEqual(item.command_sha256, self.parse(request()).command_sha256)
        modified = json.loads(request())
        modified["commands"].reverse()
        self.assertNotEqual(item.command_sha256, self.parse(json.dumps(modified)).command_sha256)

    def test_digest_changes_with_cwd_timeout_description_and_host(self):
        baseline = self.parse(request())
        self.assertNotEqual(baseline.command_sha256, self.parse(request(cwd="/var")).command_sha256)
        data = json.loads(request())
        data["commands"][0]["timeout_seconds"] = 16
        self.assertNotEqual(baseline.command_sha256, self.parse(json.dumps(data)).command_sha256)
        data = json.loads(request())
        data["description"] = "Geänderte Beschreibung"
        self.assertNotEqual(baseline.command_sha256, self.parse(json.dumps(data)).command_sha256)
        other = parse_ssh_request(request(host="other-nas"), {"other-nas"})
        self.assertNotEqual(baseline.command_sha256, other.command_sha256)

    def test_single_fenced_json_amid_explanation(self):
        item = self.parse("SSH-Auftrag:\n```json\n" + request() + "\n```\nNur nach Freigabe.")
        self.assertEqual(len(item.commands), 2)

    def test_brave_unlabeled_fenced_json_with_surrounding_text(self):
        text = (
            "Die Erweiterung soll diesen Auftrag speichern.\n\n"
            + "```\n" + request() + "\n```\n\n"
            + "Nur nach Freigabe ausfuehren."
        )
        proposal = self.parse(text)
        self.assertEqual(proposal.request_id, "req-42")
        self.assertEqual(proposal.host_id, "lab-nas")

    def test_reject_multiple_unlabeled_json_blocks(self):
        text = ("```\n" + request() + "\n```\n"
                + "```\n" + request() + "\n```")
        with self.assertRaisesRegex(InvalidSSHRequest, "ambiguous_json_blocks"):
            self.parse(text)

    def test_reject_unknown_host_and_bad_cwd(self):
        with self.assertRaisesRegex(InvalidSSHRequest, "host_not_allowlisted"):
            self.parse(request(host="unbekannt"))
        for cwd in ("relative", "/tmp/../etc", "/x\x00y"):
            with self.subTest(cwd=cwd), self.assertRaisesRegex(InvalidSSHRequest, "invalid_working_directory"):
                self.parse(request(cwd=cwd))

    def test_reject_unstructured_and_ambiguous_json(self):
        with self.assertRaises(InvalidSSHRequest):
            self.parse("ssh root@lab-nas uname -a")
        body = request()
        with self.assertRaisesRegex(InvalidSSHRequest, "ambiguous_json_blocks"):
            self.parse("```json\n" + body + "\n```\n```json\n" + body + "\n```")

    def test_reject_model_approval_and_extra_properties(self):
        data = json.loads(request())
        data["approved"] = True
        with self.assertRaisesRegex(InvalidSSHRequest, "unexpected_request_shape"):
            self.parse(json.dumps(data))

    def test_reject_invalid_commands_and_timeouts(self):
        normal = json.loads(request())
        for bad in (
            [], [{"id": "x", "command": "", "timeout_seconds": 5}],
            [{"id": "x", "command": "echo a\x00b", "timeout_seconds": 5}],
            [{"id": "x", "command": "echo ok", "timeout_seconds": True}],
            [{"id": "x", "command": "echo ok", "timeout_seconds": 301}],
            [{"id": "x", "command": "echo ok", "timeout_seconds": 10}] * 33,
            [{"id": "dup", "command": "a", "timeout_seconds": 5},
             {"id": "dup", "command": "b", "timeout_seconds": 5}],
        ):
            with self.subTest(bad=str(bad)[:50]), self.assertRaises(InvalidSSHRequest):
                self.parse(json.dumps({**normal, "commands": bad}))

    def test_duplicate_json_keys_are_rejected(self):
        duplicate = request().replace('"target": "lab-nas"', '"target": "lab-nas", "target": "evil"')
        with self.assertRaisesRegex(InvalidSSHRequest, "duplicate_json_key"):
            self.parse(duplicate)


if __name__ == "__main__":
    unittest.main()
