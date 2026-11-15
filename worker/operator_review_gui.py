"""Explicitly launched local Tk LIVE-review dialog. Never performs SSH or auto-send.

Usage: python -m worker.operator_review_gui --live-db ... --credentials ...
    --rate-db ... --targets ... --request-id ...

Requires an already provisioned operator record, LIVE proposal and trusted
local target list. The existing Brave mock UI never invokes this module.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worker.live_approval import LiveApprovalLedger, LiveAuthorizationError, LiveTargetBinding
from worker.operator_credentials import OperatorCredentialFile
from worker.operator_review import OperatorReviewController
from worker.trusted_operator_flow import TrustedOfflineOperatorFlow


def load_local_targets(file_path: Path) -> dict[str, LiveTargetBinding]:
    """Strict local operator-maintained allowlist, no network discovery."""
    if not file_path.is_absolute() or file_path.is_symlink() or not file_path.is_file():
        raise LiveAuthorizationError("trusted_target_file_required")
    if file_path.stat().st_size > 65536:
        raise LiveAuthorizationError("target_file_too_large")
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        if type(raw) is not list or not 1 <= len(raw) <= 32:
            raise ValueError("invalid_target_count")
        targets = {}
        for item in raw:
            if type(item) is not dict or set(item) != {
                "host_id", "hostname", "username", "port", "host_public_key"
            }:
                raise ValueError("invalid_target_shape")
            target = LiveTargetBinding(**item)
            if target.host_id in targets:
                raise ValueError("duplicate_host")
            targets[target.host_id] = target
        return targets
    except (ValueError, TypeError, UnicodeError, KeyError) as exc:
        raise LiveAuthorizationError("trusted_target_file_invalid") from exc


def open_local_review(controller: OperatorReviewController, request_id: str):
    """Blocking local review only; never reads passwords from argv or stdout."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    review = controller.prepare(request_id)
    root = tk.Tk()
    root.title("LLM Worker - LIVE-Auftragsfreigabe (KEIN SSH-START)")
    root.geometry("900x750")
    root.minsize(650, 450)

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="LIVE-Freigabe: alle Befehle vor Bestätigung prüfen",
              font=("TkDefaultFont", 12, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Die Freigabe startet KEINE SSH-Verbindung und sendet nichts an ChatGPT.").pack(anchor="w")

    preview = scrolledtext.ScrolledText(frame, wrap="none", height=24, font=("Consolas", 10))
    preview.pack(fill="both", expand=True, pady=(10, 8))
    preview.insert("1.0", review.render_text())
    preview.configure(state="disabled")

    confirmed = tk.BooleanVar(value=False)
    ttk.Checkbutton(frame,
                    text="Ich habe den vollständigen Befehlsblock und das SSH-Ziel geprüft.",
                    variable=confirmed).pack(anchor="w", pady=(5, 8))

    ttk.Label(frame, text="Separates Betreiberpasswort (nicht das Brave-Mock-Token):").pack(anchor="w")
    password = ttk.Entry(frame, show="*")
    password.pack(fill="x", pady=(2, 10))

    status = tk.StringVar(value="Keine Freigabe erteilt.")
    ttk.Label(frame, textvariable=status).pack(anchor="w")

    button_row = ttk.Frame(frame)
    button_row.pack(anchor="e", pady=(10, 0))
    approve_button = ttk.Button(button_row, text="LIVE-Batch freigeben")

    def approve():
        if not confirmed.get() or not password.get():
            messagebox.showwarning("Bestätigung erforderlich",
                                   "Befehle prüfen, Checkbox aktivieren und Passwort eingeben.",
                                   parent=root)
            return
        approve_button.configure(state="disabled")
        try:
            approval_id = controller.approve(
                review, password.get(), full_batch_confirmed=True,
                command_sha256=review.command_sha256)
        except Exception:
            # Keep backend-specific failures and operator secrets out of GUI
            # diagnostics. Persistent lockout still records wrong passwords.
            status.set("Freigabe verweigert. Auftrag und Anmeldung prüfen.")
            messagebox.showerror("Freigabe verweigert",
                                 "Keine Freigabe erteilt. Details lokal im Audit prüfen.",
                                 parent=root)
            approve_button.configure(state="normal")
        else:
            status.set("LIVE-Freigabe protokolliert. Keine SSH-Ausführung.")
            messagebox.showinfo("Freigabe protokolliert",
                                "Der Auftrag ist freigegeben, wird aber nicht ausgeführt.",
                                parent=root)
            root.destroy()
        finally:
            password.delete(0, tk.END)

    approve_button.configure(command=approve)
    approve_button.pack(side="right")
    ttk.Button(button_row, text="Abbrechen", command=root.destroy).pack(side="right", padx=8)
    password.focus_set()
    root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Offline LIVE review UI (never executes SSH)")
    for field in ("live-db", "credentials", "rate-db", "targets"):
        parser.add_argument("--" + field, required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)

    # Fail closed if any path is missing or relative. No automatic setup.
    for path in (args.live_db, args.credentials, args.rate_db, args.targets):
        if not path.is_absolute():
            parser.error("All file paths must be absolute")
    if not args.live_db.is_file() or not args.credentials.is_file() or not args.rate_db.is_file():
        parser.error("LIVE database, credential and lockout database must already exist")

    ledger = LiveApprovalLedger(args.live_db)
    flow = TrustedOfflineOperatorFlow(OperatorCredentialFile(args.credentials),
                                      args.rate_db, ledger)
    review = OperatorReviewController(ledger, flow, load_local_targets(args.targets))
    open_local_review(review, args.request_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
