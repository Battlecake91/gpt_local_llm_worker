"""No SSH, no browser, no network: durable gate and restart tests."""
import tempfile
import sqlite3
import unittest
from pathlib import Path

from worker.ssh_protocol import parse_ssh_request
from worker.approval_state import ApprovalStore, ApprovalStateError


def batch(commands=None, request_id="req-1", host="lab-nas"):
    import json
    data = dict(schema_version=1, kind="ssh_batch", request_id=request_id,
                target=host, working_directory="/tmp", description="Diagnose",
                commands=commands if commands is not None else [
                    {"id":"one","command":"uname -a","timeout_seconds":15},
                    {"id":"two","command":"df -h","timeout_seconds":30}
                ])
    return parse_ssh_request(json.dumps(data), {host})


class ApprovalStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "worker.sqlite"
        self.db = ApprovalStore(self.db_path)
        self.request = batch()
        self.db.propose(self.request, tab_id=7, conversation_id="chat-abc")

    def test_all_new_proposals_are_mock_scoped(self):
        self.assertEqual(self.db.get("req-1")["approval_scope"], "MOCK")
        self.assertEqual(len(self.db.pending()), 1)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "approval_scope_immutable"):
            with self.db._connect() as db:
                db.execute("UPDATE ssh_batches SET approval_scope='LIVE' WHERE request_id='req-1'")
        self.assertEqual(self.db.get("req-1")["approval_scope"], "MOCK")

    def test_live_scoped_row_cannot_be_handled_by_mock_methods(self):
        with self.db._connect() as db:
            db.execute(
                "INSERT INTO ssh_batches "
                "(request_id,host_id,working_directory,description,command_sha256,"
                "commands_json,tab_id,conversation_id,status,approval_id,approved_by,approval_scope) "
                "SELECT 'live-test',host_id,working_directory,description,command_sha256,"
                "commands_json,tab_id,conversation_id,'PROPOSED',NULL,NULL,'LIVE' "
                "FROM ssh_batches WHERE request_id='req-1'"
            )
        self.assertEqual([x["request_id"] for x in self.db.pending()], ["req-1"])
        with self.assertRaisesRegex(ApprovalStateError, "approval_denied"):
            self.db.approve("live-test", command_sha256=self.request.command_sha256,
                            authenticated_operator="local-user")
        with self.assertRaisesRegex(ApprovalStateError, "rejection_denied"):
            self.db.reject("live-test")
        with self.db._connect() as db:
            db.execute("UPDATE ssh_batches SET status='APPROVED',approval_id='future-live-only' "
                       "WHERE request_id='live-test'")
        with self.assertRaisesRegex(ApprovalStateError, "execution_denied"):
            self.db.claim_execution("live-test", "future-live-only")
        with self.db._connect() as db:
            db.execute("UPDATE ssh_batches SET status='RUNNING' WHERE request_id='live-test'")
        self.assertEqual(self.db.recover_unknown(), 0)
        self.assertEqual(self.db.get("live-test")["status"], "RUNNING")

    def test_old_database_migrates_existing_rows_to_mock_scope(self):
        legacy = Path(self.tmp.name) / "old.sqlite"
        with sqlite3.connect(legacy) as connection:
            connection.execute(
                "CREATE TABLE ssh_batches ("
                "request_id TEXT PRIMARY KEY, host_id TEXT NOT NULL,"
                "working_directory TEXT NOT NULL, description TEXT NOT NULL,"
                "command_sha256 TEXT NOT NULL, commands_json TEXT NOT NULL,"
                "tab_id INTEGER NOT NULL, conversation_id TEXT NOT NULL,"
                "status TEXT NOT NULL, approval_id TEXT UNIQUE, approved_by TEXT)"
            )
            connection.execute(
                "INSERT INTO ssh_batches VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("legacy-approved", "lab-nas", "/tmp", "Diagnose",
                 self.request.command_sha256,
                 '[{"id":"one","command":"uname -a","timeout_seconds":15},'
                 '{"id":"two","command":"df -h","timeout_seconds":30}]',
                 7, "chat-abc", "APPROVED", "old-mock-approval", "mock-sidepanel-confirmation")
            )
        upgraded = ApprovalStore(legacy)
        self.assertEqual(upgraded.get("legacy-approved")["approval_scope"], "MOCK")
        self.assertEqual(upgraded.get("legacy-approved")["approval_id"], "old-mock-approval")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "approval_scope_immutable"):
            with upgraded._connect() as db:
                db.execute(
                    "UPDATE ssh_batches SET approval_scope='LIVE' WHERE request_id='legacy-approved'"
                )
        self.assertEqual(
            upgraded.propose(batch(request_id="legacy-approved"),
                             tab_id=7, conversation_id="chat-abc"),
            "legacy-approved")
        self.assertEqual(upgraded.get("legacy-approved")["approval_scope"], "MOCK")

    def test_approval_is_for_exact_complete_command_block(self):
        with self.assertRaisesRegex(ApprovalStateError, "approval_denied"):
            self.db.approve("req-1", command_sha256=batch([{"id":"two","command":"df -h","timeout_seconds":30}]).command_sha256,
                            authenticated_operator="local-user")
        self.assertEqual(self.db.get("req-1")["status"], "PROPOSED")
        self.assertEqual(self.db.get("req-1")["working_directory"], "/tmp")
        approval_id = self.db.approve("req-1", command_sha256=self.request.command_sha256,
                                      authenticated_operator="local-user")
        self.assertEqual(self.db.get("req-1")["approval_id"], approval_id)
        self.assertEqual(self.db.get("req-1")["approved_by"], "local-user")
        with self.assertRaisesRegex(ApprovalStateError, "approval_denied"):
            self.db.approve("req-1", command_sha256=self.request.command_sha256,
                            authenticated_operator="local-user")

    def test_reject_prevents_approval_and_execution(self):
        self.db.reject("req-1")
        with self.assertRaises(ApprovalStateError):
            self.db.approve("req-1", command_sha256=self.request.command_sha256,
                            authenticated_operator="local-user")
        with self.assertRaises(ApprovalStateError):
            self.db.claim_execution("req-1", "any")

    def test_one_time_claim_survives_restart_and_crash_becomes_unknown(self):
        approval_id = self.db.approve("req-1", command_sha256=self.request.command_sha256,
                                      authenticated_operator="local-user")
        self.db.claim_execution("req-1", approval_id)
        restarted = ApprovalStore(self.db_path)
        self.assertEqual(restarted.recover_unknown(), 1)
        self.assertEqual(restarted.get("req-1")["status"], "UNKNOWN")
        with self.assertRaisesRegex(ApprovalStateError, "execution_denied"):
            restarted.claim_execution("req-1", approval_id)

    def test_request_id_collision_does_not_replace_batch(self):
        changed = batch([{"id":"changed","command":"echo changed","timeout_seconds":15}])
        with self.assertRaisesRegex(ApprovalStateError, "request_id_collision"):
            self.db.propose(changed, tab_id=7, conversation_id="chat-abc")
        self.assertEqual([x["command"] for x in self.db.get("req-1")["commands"]], ["uname -a", "df -h"])

    def test_origin_is_immutable(self):
        with self.assertRaisesRegex(ApprovalStateError, "request_id_collision"):
            self.db.propose(self.request, tab_id=8, conversation_id="chat-abc")
        with self.assertRaisesRegex(ApprovalStateError, "request_id_collision"):
            self.db.propose(self.request, tab_id=7, conversation_id="other-chat")

    def test_pending_review_contains_full_immutable_command_block(self):
        proposals = self.db.pending()
        self.assertEqual(len(proposals), 1)
        item = proposals[0]
        self.assertEqual(item["host_id"], "lab-nas")
        self.assertEqual(item["working_directory"], "/tmp")
        self.assertEqual(item["tab_id"], 7)
        self.assertEqual(item["conversation_id"], "chat-abc")
        self.assertEqual(item["command_sha256"], self.request.command_sha256)
        self.assertEqual([c["timeout_seconds"] for c in item["commands"]], [15, 30])
        self.db.reject("req-1")
        self.assertEqual(self.db.pending(), [])

    def test_mock_history_is_read_only_and_persists_result_origin(self):
        approval_id = self.db.approve(
            "req-1", command_sha256=self.request.command_sha256,
            authenticated_operator="mock-sidepanel-confirmation")
        self.db.claim_execution("req-1", approval_id)
        self.db.finish_mock_execution("req-1", approval_id, {
            "status": "SUCCEEDED", "mode": "MOCK_ONLY",
            "commands": [{"id": "one", "stdout": "offline fixture"}]})
        restarted = ApprovalStore(self.db_path)
        history = restarted.recent_mock_results()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["request_id"], "req-1")
        self.assertEqual(history[0]["conversation_id"], "chat-abc")
        self.assertEqual(history[0]["tab_id"], 7)
        self.assertEqual(history[0]["result"]["mode"], "MOCK_ONLY")
        self.assertEqual(restarted.get("req-1")["status"], "SUCCEEDED")
        self.assertEqual(restarted.recent_mock_results(limit=1), history)

    def test_duplicate_proposal_is_idempotent(self):
        self.db.propose(self.request, tab_id=7, conversation_id="chat-abc")
        self.assertEqual(self.db.get("req-1")["status"], "PROPOSED")

    def test_wrong_approval_id_cannot_claim_execution(self):
        self.db.approve("req-1", command_sha256=self.request.command_sha256,
                        authenticated_operator="local-user")
        with self.assertRaisesRegex(ApprovalStateError, "execution_denied"):
            self.db.claim_execution("req-1", "incorrect")
        self.assertEqual(self.db.get("req-1")["status"], "APPROVED")

    def test_missing_operator_identity_denied(self):
        with self.assertRaisesRegex(ApprovalStateError, "missing_operator"):
            self.db.approve("req-1", command_sha256=self.request.command_sha256,
                            authenticated_operator="")


if __name__ == "__main__":
    unittest.main()
