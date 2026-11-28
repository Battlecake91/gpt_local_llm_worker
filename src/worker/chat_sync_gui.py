"""PySide6 desktop viewer for active ChatGPT tabs.

Run: python -m worker.chat_sync_gui --extension-id <32-letter extension ID>
No browser automation, LLM inference, or SSH execution occurs here.
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import threading
from pathlib import Path

import uvicorn

from worker.chat_sync import ChatStore, create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extension-id", required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--db", type=Path, default=Path(os.environ.get(
        "LOCALAPPDATA", str(Path.home()))) / "gpt-local-llm-worker" / "active-chats.sqlite3")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import (
            QApplication, QHBoxLayout, QLabel, QListWidget, QMainWindow,
            QMessageBox, QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
        )
    except ImportError:
        print("PySide6 fehlt: py -m pip install -e '.[gui]'", file=sys.stderr)
        return 2

    token = secrets.token_hex(32)
    store = ChatStore(args.db)
    api = create_app(store, token, args.extension_id)
    config = uvicorn.Config(api, host="127.0.0.1", port=args.port,
                            access_log=False, log_level="warning")
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("GPT Local Worker | Aktive Chats")
            self.resize(1150, 710)
            root = QWidget()
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            description = QLabel(
                "Phase 1: Nur explizit aktivierte, geöffnete Chats. "
                "Keine Aktionen, kein LLM, kein SSH.")
            description.setWordWrap(True)
            layout.addWidget(description)

            token_row = QHBoxLayout()
            self.status = QLabel(f"Bridge: http://127.0.0.1:{args.port} | "
                                 f"Extension: {args.extension_id}")
            token_row.addWidget(self.status)
            copy_button = QPushButton("Bridge-Token kopieren")
            copy_button.clicked.connect(
                lambda: QApplication.clipboard().setText(token))
            token_row.addWidget(copy_button)
            layout.addLayout(token_row)

            split = QSplitter(Qt.Horizontal)
            self.chats = QListWidget()
            self.chats.setMinimumWidth(340)
            self.chats.currentRowChanged.connect(self.render_messages)
            self.messages = QTextEdit()
            self.messages.setReadOnly(True)
            self.messages.setFont(QFont("Consolas", 10))
            split.addWidget(self.chats)
            split.addWidget(self.messages)
            split.setSizes([360, 780])
            layout.addWidget(split)

            self.items = []
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1500)
            self.refresh()

        def refresh(self):
            selected = (self.items[self.chats.currentRow()]["tab_id"]
                        if 0 <= self.chats.currentRow() < len(self.items) else None)
            updated = store.list()
            self.items = updated
            self.chats.blockSignals(True)
            self.chats.clear()
            for chat in updated:
                state = "● LIVE" if chat["online"] else "○ Tab nicht erreichbar"
                generating = " | generiert" if chat["generating"] else ""
                self.chats.addItem(
                    f'{state}{generating} | Tab {chat["tab_id"]}\n'
                    f'{chat["title"][:85]}')
            target = next((i for i, item in enumerate(updated)
                           if item["tab_id"] == selected), 0 if updated else -1)
            self.chats.setCurrentRow(target)
            self.chats.blockSignals(False)
            self.render_messages(target)

        def render_messages(self, index):
            if not 0 <= index < len(self.items):
                self.messages.clear()
                return
            chat = self.items[index]
            records = store.messages(chat["tab_id"])
            # Preserve scroll position on periodic updates.
            scrollbar = self.messages.verticalScrollBar()
            previous = scrollbar.value()
            lines = []
            for m in records:
                flag = " [noch nicht abgeschlossen]" if not m["complete"] else ""
                lines.append(f'===== {m["role"].upper()} #{m["ordinal"]+1}{flag} =====\n{m["text"]}')
            result = "\n\n".join(lines)
            if self.messages.toPlainText() != result:
                self.messages.setPlainText(result)
                scrollbar.setValue(previous)

        def closeEvent(self, event):
            server.should_exit = True
            super().closeEvent(event)

    app = QApplication(sys.argv[:1])
    window = Window()
    window.show()
    if not server.started:
        QMessageBox.information(window, "Bridge", "Lokaler Server startet auf Port "
                                + str(args.port) + ".")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
