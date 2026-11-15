"""One-shot Windows/local GUI smoke fixture. Does NOT make any SSH connection.

Run from repository root: py scripts/operator-review-gui-smoke.py
All files reside in a temporary directory and are removed when the GUI closes.
The synthetic password printed on startup is not a real credential.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Scripts execute from scripts/; include repository root for worker imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.live_approval import LiveApprovalLedger, LiveTargetBinding
from worker.operator_auth import create_password_record
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_review import OperatorReviewController
from worker.operator_review_gui import open_local_review
from worker.ssh_protocol import parse_ssh_request
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


TEST_PASSWORD = "offline-fixture-only-passphrase-2026"
TEST_REQUEST = "gui-offline-fixture-1"


def prepare_smoke(root: Path):
    """All state is synthetic and confined to a dedicated temporary root."""
    live_db = root / "live.sqlite"
    credentials = root / "credentials.json"
    throttle = root / "throttle.sqlite"

    # Real host keys and real hostnames are deliberately absent.
    target = LiveTargetBinding(
        host_id="offline-fixture",
        hostname="fixture.example.invalid",
        port=2222,
        username="fixtureuser",
        host_public_key="ssh-ed25519 SYNTHETIC-KEY-NOT-VALID",
    )
    batch = parse_ssh_request(json.dumps({
        "schema_version": 1,
        "kind": "ssh_batch",
        "request_id": TEST_REQUEST,
        "target": "offline-fixture",
        "working_directory": "/tmp/offline-only",
        "description": "GUI-Smoketest, keine SSH-Ausführung",
        "commands": [
            {"id": "first", "command": "printf 'fixture only'",
             "timeout_seconds": 4},
            {"id": "second", "command": "printf 'no connection'",
             "timeout_seconds": 5},
        ],
    }), {"offline-fixture"})
    ledger = LiveApprovalLedger(live_db)
    ledger.propose(batch, target, tab_id=4321,
                   conversation_id="offline-fixture-chat-not-real")

    # Windows protects the test verifier using the native user-scoped DPAPI.
    # The credential is thrown away with the temporary directory afterwards.
    stored = OperatorCredentialFile(credentials)
    stored.create(create_password_record("fixture-operator", TEST_PASSWORD))
    flow = TrustedOfflineOperatorFlow(stored, throttle, ledger)
    controller = OperatorReviewController(
        ledger, flow, {"offline-fixture": target})
    return controller, ledger


def run_smoke(show_gui=open_local_review):
    with tempfile.TemporaryDirectory(prefix="llm-worker-gui-smoke-") as temp:
        controller, ledger = prepare_smoke(Path(temp))
        preview = controller.prepare(TEST_REQUEST).render_text()
        if "fixture.example.invalid" not in preview or "no connection" not in preview:
            raise RuntimeError("smoke_preview_invalid")
        print("OFFLINE GUI SMOKE: Keine SSH-Verbindung, keine Browseraktion.")
        print("Synthetisches Testpasswort:", TEST_PASSWORD)
        print("Im Fenster entweder abbrechen oder Checkbox und Testpasswort nutzen.")
        show_gui(controller, TEST_REQUEST)
        result = ledger.get(TEST_REQUEST)
        audit = controller._flow.audit_for(TEST_REQUEST)
        if result["status"] == "APPROVED":
            if len(audit) != 1:
                raise RuntimeError("smoke_audit_missing")
            print("OFFLINE PASS: genau eine Testfreigabe und ein Audit-Eintrag.")
        elif result["status"] == "PROPOSED":
            if audit:
                raise RuntimeError("smoke_unexpected_audit")
            print("OFFLINE PASS: GUI ohne Freigabe beendet.")
        else:
            raise RuntimeError("smoke_unexpected_state")
        print("Kein SSH gestartet; temporäre Testdateien werden bereinigt.")


if __name__ == "__main__":
    run_smoke()
