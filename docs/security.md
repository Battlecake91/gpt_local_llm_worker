# Security contract v0.1

## Trust boundaries
All web page content, assistant replies, Ollama results, SSH output and external documents are untrusted. No model can grant authorization. No command inferred from prose may execute.

## Execution gate
- A batch must be valid protocol JSON, from the currently observed assistant response, with a unique request ID.
- Display every exact command and target (host alias, username, working directory), plus expected side effects, before approval.
- Store a canonical content hash. User approval applies only to that exact batch, once.
- Execute sequentially by default; stop on failure; prohibit implicit retries.
- Use an explicit allowlist of SSH host aliases, pinned host keys and dedicated limited accounts.
- No agent forwarding, interactive TTY, shell interpolation by the worker, or arbitrary target supplied outside the allowlist. Commands remain inherently dangerous even if displayed; approval is mandatory.
- Enforce concurrency limits, timeouts, output byte limits and audit logging.
- Never put SSH private keys or service tokens in extension storage or logs.

## Browser and API
Bind to 127.0.0.1 only. Authenticate extension requests with a locally provisioned token, validate Origin where applicable, use strict CORS, reject untrusted websites, and protect approval endpoints against CSRF. No wildcard permissions. Scope content scripts to ChatGPT domains and limit host permissions to the local service. Treat browser automation as an authenticated client, not as authorization.

## Automatic return
Only send after explicit batch approval and execution attempt. Bind result to originating tab and conversation; verify identity immediately before sending. Strip credentials and sensitive content, truncate large output, include exit codes and distinguish failure/unknown. Never auto-send if the conversation changed or identity is uncertain.

## Recovery
Write state before launching commands. On crash, ambiguous execution is UNKNOWN and needs operator reconciliation; no at-least-once execution. Keep an append-only audit record of approvals, execution attempts and result delivery.

## Deployment
Default dry-run. No production SSH connections or automatic sending enabled until separate integration tests and explicit operator enablement.


## Implemented bridge safety boundary
The MV3 extension only accesses `https://chatgpt.com/*` and `http://127.0.0.1/*`; API requests use a required Bearer token stored in extension-local storage restricted to trusted contexts. It is **not encrypted at rest**. Auto-send requires a one-use backend claim that matches the exact approved SSH job, operator approval ID, allowlisted host, command digest, result digest, tab and conversation. The extension recomputes the outgoing UTF-8 text digest; absent or legacy claims are rejected. Invalid binding receipts are terminal, while an `ATTEMPTING` receipt is persisted before any click to block retries after ambiguous failure. The mock adapter validates bindings but has **no authentic user-approval UI**, executor, output redaction or durable backend audit log. Never expose it outside loopback, use it for real SSH approvals, or enable live auto-send without separate operator authorization. Its stage fixture endpoint is disabled unless `BRIDGE_MOCK_FIXTURES=1`. See [bridge protocol](bridge-protocol.md).

## Offline SSH boundary and persistent approval ledger

`worker/ssh_protocol.py` only parses explicit JSON protocol envelopes, rejects unknown/duplicate fields and unknown host aliases, enforces command and payload bounds, and computes a canonical SHA-256 over **target host alias, working directory, full ordered command list with IDs and timeouts, and description**. It **does not execute** any commands and never interprets `approved` in model content as authority.

`worker/approval_state.py` is an isolated SQLite ledger: it persists immutable proposal text/digest, originating tab/conversation and approval identity. The application must authorize an **actual operator** before calling `approve()`, and its UI must show every exact command, configured SSH username and working directory, and relevant side effects. The Python method's `authenticated_operator` argument is a trust-boundary *contract*, not an authentication mechanism. There is no operator-facing approval endpoint yet, and no executor is wired to the ledger.

`APPROVED` → `RUNNING` is an atomic, one-time transition intended to precede SSH launch. On process restart `RUNNING` → `UNKNOWN` requires reconciliation, not automatic replay. Successful tests of this isolated ledger do **not** authorize live SSH, shell evaluation, or browser auto-send.

### Sicherheit der Mock-Review-Oberfläche

Die Review-API ist lokal und Bearer-token-geschützt. Die Browser-Extension akzeptiert `LIST_SSH_PROPOSALS`/`DECIDE_SSH_PROPOSAL` nur von `chrome.runtime.getURL('panel.html')` ohne Content-Script-Tab-Kontext. Das Panel verwendet `textContent`, keine Auswertung von Modell-HTML. Die Checkbox bestätigt den **vollständigen** sichtbaren Block; Backend prüft bei jeder Aktion erneut Freigabe-Digest, Ursprungschat, Tab und `PROPOSED`-Status. Der Mock speichert nur eine Entscheidung, keine Ausführung und keine automatische Antwort. Das gemeinsame lokale Bearer-Token ist **kein eigenständiger Operator-Identitätsnachweis**. Ein produktives Approval-System benötigt eine eigene authentifizierte Benutzerfreigabe mit Host-Benutzer-/Hostkey-Konfiguration und persistenter Audit-Kette.

### Offline-Executor-Fail-Closed (2026-11-15)

`worker/mock_executor.py` ist ein reiner Fixture-Interpreter, kein SSH-Client. Er importiert weder Netzwerk- noch Prozessausführungsbibliotheken. Auch der optionale CLI-Aufruf `worker/mock_cli.py` erzeugt nur explizit mit `MOCK ONLY` markierte Antworten und versendet **nichts** an ChatGPT. Hostalias, Benutzer und `SHA256:`-Hostkey sind für diesen Modus ausschließlich syntaktisch validierte **Testmetadaten**, keine echte Hostkey-Verifizierung. Zeitüberschreitungen werden durch Fixture-Werte simuliert, nicht anhand verstrichener Laufzeit gemessen.

Vor dem einmaligen Statuswechsel `APPROVED → RUNNING` wird der gesamte in SQLite gespeicherte Befehlsblock einschließlich Ziel, CWD, Beschreibung, Befehlsreihenfolge und Timeouts erneut kanonisch gehasht. Fehlender Host, falsche Freigabe-ID, veränderter Digest oder unvollständige Fixtures werden ohne Claim abgewiesen. Die statische Fixture-Antwort wird auf maximal 16 KiB UTF-8 je Batch begrenzt und mit `truncated` markiert; ein Nonzero-Exit, Timeout-Flag oder gekürzte Ausgabe beendet den Batch. Resultat und terminaler Batchstatus werden gemeinsam in SQLite gespeichert. Ein nach Absturz unklarer `RUNNING`-Batch wird zu `UNKNOWN` und darf nicht wiederholt werden.

**Keiner dieser Tests ist eine reale SSH-Sicherheitsabnahme.** Vor produktiver Ausführung fehlen Hostkey-Kryptoprüfung, SSH-Transport, wirkliche Timeout-Durchsetzung, Log-/Output-Redaction, Operator-Authentifizierung und echte Audit-/Result-Routing-Integration.

### Read-only result visibility

A bounded `GET /api/bridge/v1/ssh/mock-results` endpoint returns persisted mock fixtures only and requires the same local Bearer authentication. The extension forwards `LIST_MOCK_RESULTS` only from its own trusted side panel; no content script may call it. Model/fixture stdout and stderr are rendered with `textContent`, never `innerHTML`. This is **not** output redaction: real SSH output and secrets must not be routed into this mock view without separate sanitization, authentication and audit controls. The result view never triggers SSH or automated ChatGPT submission.

### Vorbereiteter OpenSSH-Transport (2026-11-15, noch nicht verdrahtet)

`worker/ssh_transport.py` enthält einen isolierten Transportadapter für einen **später separat freizugebenden** Live-Test. Die bestehende Brave-/Mock-API importiert oder startet ihn **nicht**. Es gibt weder CLI-Einstieg zum Live-SSH noch automatische Ausführung bereits mit dem Mock-Panel freigegebener Datensätze. Der Adapter nutzt vorab definierte `SSHHostConfig`-Objekte mit Hostalias, Zielname, dediziertem SSH-Benutzer, Port, absolutem Identity-Dateipfad und komplettem **Host-Public-Key** (nicht nur einem ungeprüften Fingerprint). Die Hostidentität prüft OpenSSH per isolierter temporärer `known_hosts`-Datei, `StrictHostKeyChecking=yes`, `GlobalKnownHostsFile=none`, `UserKnownHostsFile=<isoliert>`, `CheckHostIP=no` und `UpdateHostKeys=no`. User-SSH-Konfiguration ist durch `-F none` deaktiviert; TTY, SSH-Agent, Weiterleitungen, Passwortnachfragen, ControlMaster und X11 sind deaktiviert.

OpenSSH wird ausschließlich als argv-Liste mit `shell=False` gestartet; das genehmigte Kommando wird unverändert an die **Remote-Shell** übergeben. Nur das Remote-Arbeitsverzeichnis wird mit `shlex.quote()` geschützt. Damit kann ein genehmigtes SSH-Kommando weiterhin gefährliche Shell-Operationen enthalten: Der Transport ist **kein Sandbox- oder Read-only-Mechanismus** und ersetzt keinesfalls Freigabedialog und restriktiven SSH-Account.

Der subprocess-Adapter begrenzt die Summe aus stdout+stderr auf 16 KiB und beendet den lokalen SSH-Prozess beim Überschreiten; Timeout erfolgt über `Popen.wait(timeout=...)` mit anschließendem `kill` und Reader-Reconciliation. Ein lokales Prozess-Kill beweist **nicht**, dass ein möglicherweise bereits gestarteter Remote-Prozess beendet wurde. Bei Crash oder Verbindungsabbruch muss der Auftragszustand unklar bleiben und darf nicht automatisch neu ausgeführt werden. Die echte Integration in `ApprovalStore`, belastbarer Auditlog, Redaction und Live-Hostkey-Test sind noch ausstehend.

### Offline Integration Coordinator (2026-11-15)
`worker/execution_coordinator.py` is a test-only approval-to-transport coordinator. It rejects the real `SSHTransport`, requires a fixture-marked fake runner, and refuses to consume an `APPROVED` row without a distinct `FixtureOnlyPermit` object. It re-parses SQLite command data and recomputes the SHA-256 binding *before* the atomic one-use `claim_execution`. After the claim, exceptions leave `RUNNING`, which becomes `UNKNOWN` on restart; no automatic retry. Terminal fixture results are stored with the batch's terminal status in a single transaction. The marker and permit are deliberately **not considered security credentials** and can be constructed by arbitrary Python code: never surface this coordinator to HTTP, content scripts or a live SSH path. A separate authenticated production operator credential, host/identity binding, output redaction, and append-only audit are still mandatory.

### Dauerhafte Trennung der Freigabe-Domänen (2026-11-15)
`ApprovalStore` hat jetzt eine persistente, unveränderliche Spalte `approval_scope` (`MOCK` oder später `LIVE`). Eine idempotente SQLite-Migration setzt **alle bestehenden Datensätze ohne diesen Typ** auf `MOCK`, ausdrücklich auch bereits bestätigte Aufträge. Ein Trigger `ssh_batches_scope_immutable` verbietet nachträgliche Änderungen des Scopes. `propose`, `approve`, `reject`, `pending`, `claim_execution`, `recover_unknown`, `finish_mock_execution` und Mock-Historienfunktionen arbeiten nur mit `MOCK`-Datensätzen. Eine gleichnamige `LIVE`-Zeile wird vom Mock-Frontend nicht angezeigt und kann mit dem Mock-Bearer-Token nicht genehmigt werden. Es existiert **noch kein** produktiver `LIVE`-Freigabe- oder Ausführungsweg. Der Scope ist eine notwendige zusätzliche Schranke, kein Ersatz für dedizierte Betreiber-Authentifizierung, Audit und abgesicherte SSH-Credentials.
