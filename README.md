# GPT Local LLM Worker

Local Brave/Chromium extension and Python worker for observing completed ChatGPT responses, classifying them with Ollama, and executing explicitly approved SSH command batches.

## Architecture
- Brave MV3 extension: observe the ChatGPT Stop button transition and capture only newly completed assistant messages.
- Local FastAPI service bound to 127.0.0.1, with persistent SQLite queue and audit trail.
- Ollama model configurable; initial benchmark candidate: qwen3:4b for a 6 GB VRAM GPU.
- Explicit JSON command envelopes only. No free-text command extraction in v1.
- SSH executor with host allowlist, pinned host keys, least-privilege credentials, per-batch human approval.
- Side panel: status, pending approvals, execution output and failures.
- After an approved batch completes, automatically submit its bounded, sanitized result to the originating ChatGPT conversation.

## State
The Brave bridge has been smoke-tested in both directions using the isolated mock worker. No live SSH execution, operator-approval UI or real auto-send is deployed.

See [architecture](docs/architecture.md), [security](docs/security.md), [protocol](docs/protocol.md), and [AGENTS.md](AGENTS.md).


## Brave bridge implementation (feature/brave-chat-bridge)
A testable MV3 bridge is implemented in `extension/`, with an isolated FastAPI mock in `mock/backend.py` and Node/Python tests in `tests/`. This is **not** a deployed SSH worker: Ollama, approval UI, persistent production queue and executor are still separate planned components. The side panel currently shows bridge status, not SSH approval controls. An isolated SSH JSON validator and durable SQLite approval state ledger now exist in `worker/`, but are **not connected to a production executor**.

Install the test extra and run both test frameworks from the repository root:
```bash
python -m pip install -e ".[test]"
node --test tests/*.cjs
python -m pytest -q
```

Some legacy tests in `tests/test_contracts.py` are `pytest` functions with a `tmp_path` fixture; `unittest discover -p 'test_*.py'` is **not** the full Python test runner and fails to import that module if `pytest` is absent. Use `pytest` to collect both the legacy test functions and the newer `unittest.TestCase` suites.

See [installation and mock smoke test](INSTALL.md), [bridge API contract](docs/bridge-protocol.md), and [live-test status](docs/work-in-progress/brave-chat-bridge.md). Brave has been tested live for completed-reply capture and STAGE_ONLY text insertion. Real SSH execution and auto-send have **not** been authorized or tested. Auto-send now rejects claims without a matching immutable SSH job/command/result/origin binding; the mock cannot grant genuine human approval.

## SSH-Review im Brave-Panel (nur Mock)

Das Seitenpanel enthält inzwischen einen eingeklappten Bereich für vollständige SSH-Auftragsvorschläge. Ein aktivierter Mock-Worker kann streng validierte `kind:"ssh_batch"`-Antworten mit konfigurierter Host-Allowlist in SQLite als `PROPOSED` speichern. Bestätigung und Ablehnung erfolgen nur per Panel-Aktion und werden vom Backend anhand Origin und Approval-Digest geprüft. **Dies ist keine produktive SSH-Freigabe:** Weder Executor noch automatische ChatGPT-Übertragung werden durch `APPROVED_FOR_MOCK_REVIEW` aktiviert. Anleitung: [INSTALL.md](INSTALL.md#mock-ssh-aufträge-im-seitenpanel-prüfen-ohne-ausführung).

## Offline SSH Fixture-Simulation

Unter `worker/mock_executor.py` liegt ein ausdrücklich nicht-netzwerkfähiger Executor für bereits genehmigte Testaufträge. Er validiert den kompletten gespeicherten Befehls-Digest erneut, erzeugt nur statische `MOCK ONLY`-Ausgaben, setzt Timeouts lediglich als Testkennzeichen, begrenzt UTF-8-Output und verhindert Wiederausführung nach Erfolg/Fehler/Absturz. Kein SSH-Client, keine realen Befehle, kein Auto-Send. Siehe [Windows-Demo](INSTALL.md#bereits-freigegebenen-ssh-auftrag-offline-simulieren) und `tests/test_mock_executor.py`.

## Gespeicherte Mock-Resultate im Brave-Seitenpanel

Der eingeklappte Abschnitt **Simulierte SSH-Ergebnisse** zeigt fertig persistierte `MOCK_ONLY`-Resultate ausschließlich lesend: Auftrag, Originalchat, Host, Status, Command-IDs, Exitcodes, Timeout-/Trunkierungskennzeichen sowie stdout/stderr. Ein authentifizierter GET-Endpunkt liest SQLite, das Background-Script akzeptiert die Abfrage ausschließlich aus der vertrauenswürdigen Panel-Seite, und die UI setzt Output nur als Text. Weder erneute Ausführung noch Auto-Send werden durch das Anzeigen ausgelöst. Anleitung: [INSTALL.md](INSTALL.md#gespeicherte-mock-ergebnisse-im-brave-seitenpanel-anzeigen).

### Vorbereitung eines echten SSH-Transports

`worker/ssh_transport.py` definiert eine später separat zu integrierende OpenSSH-Komponente mit fest konfiguriertem Ziel, tatsächlicher Hostkey-Prüfung über den vollständigen öffentlichen Schlüssel, ohne interaktiven SSH-Agent/TTY, mit Prozess-Timeout und kombinierten Ausgabelimits. **Nicht aktiviert:** kein Live-SSH-CLI, kein produktiver Executor, keine Kopplung an Freigaben und kein Auto-Send. Die Fake-Runner-Vertragstests liegen unter `tests/test_ssh_transport.py`; für echte Verbindungen ist eine getrennte ausdrückliche Freigabe erforderlich.

### Approval-to-Transport Offline-Vertrag
`worker/execution_coordinator.py` verbindet den vorhandenen Approval-Store testweise mit einem **ausschließlich simulierten** Transport. Er erzwingt erneut den vollständigen Digest, genau einen RUNNING-Claim, Stop-on-Failure und UNKNOWN nach unklarem Fehler. Er ist absichtlich **nicht** mit Brave, FastAPI, CLI oder OpenSSH verbunden; eine Mock-Freigabe und eine leicht konstruierbare Fixture-Marke sind keine produktive Autorisierung. Offline-Tests: `py -m pytest -q tests/test_execution_coordinator.py`.

### LIVE-Freigabedomäne (weiterhin deaktiviert)
`worker/live_approval.py` führt ein unabhängiges, unveränderliches LIVE-Vorschlagsjournal ein. Es ist an keine UI, API oder CLI angeschlossen; `approve` und `claim_execution` sind bewusst gesperrt. Die bisherigen `MOCK`-Freigaben werden nicht übernommen. Offline-Vertragstests: `py -m pytest -q tests/test_live_approval.py`.

### Betreiber-Authentifizierung (Offline-Vertrag)
`worker/operator_auth.py` enthält eine isolierte scrypt-Passwortprüfung mit kurzlebigen, nur einmal verwendbaren und auf Auftrag/Ziel/Chat gebundenen Tickets. **Nicht angeschlossen** an UI, API oder LIVE-Approval; keine echten SSH-Verbindungen. Tests: `py -m pytest -q tests/test_operator_auth.py`.

### Offline LIVE-Freigabe mit Audit
`worker/offline_live_gate.py` verbindet Betreiber-Einmaltickets mit dem separaten LIVE-Journal und schreibt Freigabe plus Audit atomar in SQLite. Nur direkter Offline-Python-Bibliotheksaufruf, keine API/CLI-/Brave-Verbindung und ausdrücklich **keine SSH-Ausführung**. Test: `py -m pytest -q tests/test_offline_live_gate.py`.

### Betreiber-Zugangsdaten dauerhaft ablegen (Offline-Baustein)
`worker/operator_credentials.py` hält einen gesalzenen Passwortverifikator dauerhaft vor, ohne Klartextpasswort. Windows nutzt benutzergebundene DPAPI-Verschlüsselung, Linux private Dateirechte. Es gibt bewusst **noch keinen** Installations- oder Anmelde-Endpunkt; auch diese Ablage aktiviert keinen LIVE-SSH. Isolierte Tests: `py -m pytest -q tests/test_operator_credentials.py`.

### Persistente Login-Sperre
`worker/operator_rate_limit.py` ergänzt einen ausschließlich lokalen, SQLite-basierten Verifikations-Wrapper. Nach fünf falschen Passworteingaben bleibt eine 60-Sekunden-Sperre auch bei einem Worker-Neustart erhalten. Der Wrapper besitzt **keinen** Login-Endpunkt, und keine SSH-Ausführung wird freigegeben. Tests: `py -m pytest -q tests/test_operator_rate_limit.py`.

### Offline-Betreiberanmeldung mit persistenter Sperre
`worker/trusted_operator_flow.py` stellt die lokalen Credential-, Rate-Limit- und LIVE-Audit-Komponenten zu einer fail-closed Offline-Freigabe zusammen. Keine UI oder API schaltet echte SSH-Befehle frei. Vertragstest: `py -m pytest -q tests/test_trusted_operator_flow.py`.
