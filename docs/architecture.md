# Architecture v0.1

## Agreed decisions
1. Brave and Python worker run on the same computer.
2. Approval applies to a complete immutable SSH command batch.
3. After an approved SSH batch, return its result to ChatGPT automatically.
4. Observe only newly completed assistant responses.
5. SSH proposals use explicit JSON envelopes; no free-text extraction initially.
6. SSH targets must be preconfigured in an allowlist.
7. Status and approvals live in a Brave side panel.

## Components
- MV3 content script: tracks ChatGPT Stop button lifecycle (running -> absent), waits for DOM stabilization, extracts the final assistant message, attaches conversation identity and a stable deduplication fingerprint. A stopped generation is not automatically a successful completion; distinguish manual cancellation and unexpected DOM states where possible.
- MV3 background/service worker: authenticated localhost communication, delivery retry and tab routing. No SSH credentials in browser.
- Side panel: pending batch review with full host, user, cwd, command text and risk summary; explicit approve/reject; status and audit history.
- FastAPI backend on loopback: schema validation, message queue, Ollama adapter, persistence and state machine.
- Ollama: text classification and status JSON only. Model configurable, benchmark qwen3:4b against alternatives on actual messages. Never authorizes actions.
- SSH executor: executes only approved immutable batches on allowlisted targets, with host-key pinning and bounded output. Command-level failures stop the batch by default.
- Return channel: result is associated with the original tab/conversation; send automatically only after an actual user-approved batch, with bounded output and explicit success/failure labels.

## State machine
CAPTURED -> ANALYZING -> CLASSIFIED
For explicit command proposal: PROPOSED -> AWAITING_APPROVAL -> APPROVED -> RUNNING -> SUCCEEDED|FAILED|UNKNOWN
Rejection: AWAITING_APPROVAL -> REJECTED
After execution: RESULT_PENDING -> RESULT_SENT|RESULT_SEND_FAILED

Persist transitions before side effects. On restart, RUNNING becomes UNKNOWN until reconciled, never blindly retried. Approval is bound to a hash of the canonical batch. A changed batch requires new approval. Queue deduplicates captured messages and result submissions.

## Constraints
A browser UI is not a stable API. Selectors and completion heuristics must be covered by DOM fixtures and tested against UI changes. Auto-send is disabled for unapproved, inferred, or merely classified content. Never allow automatic model-to-model command execution.

## Implementation sequence
1. JSON schemas, fixtures, state machine, SQLite tests.
2. Extension observation and side panel with mocked backend.
3. Ollama adapter and reproducible model benchmark.
4. SSH mock executor and approval gates.
5. End-to-end integration, explicit opt-in live testing.


## Implemented bridge slice (feature/brave-chat-bridge)
`extension/bridge-core.js` implements IDLE / GENERATING / FINALIZING / COMPLETED / CANCELLED / ERROR and waits 650 ms after the Stop button disappears. The content script observes DOM changes, extracts rendered multiline text, and establishes a baseline so pre-existing messages are not imported. The background service worker queues captures, authenticates on loopback and routes outbound staging to the originating tab and chat. The side panel currently shows connection, generation state, last capture, transfer, outbound status, queue and errors; full approval controls belong to a later worker integration.

`mock/backend.py` is an in-memory fixture only, not the future durable SQLite service. Browser-side `SUBMIT_CLICKED` is distinct from server-confirmed delivery. See [bridge contract](bridge-protocol.md). A real Brave smoke test remains mandatory.

## Security foundation implemented after Brave bridge (2026-11-14)

- `worker/ssh_protocol.py`: parses the **existing** `kind:"ssh_batch"` JSON schema from [protocol](protocol.md), without command inference, shell interpretation or network access. Operator-configured host aliases only. SHA-256 approval digest covers target, working directory, all ordered command IDs/text/timeouts and description.
- `worker/approval_state.py`: independent SQLite proposal/approval ledger; origin tab and conversation immutable. Only a separate, authenticated operator UI may call its `approve()` method. The method is not itself an authentication boundary. `APPROVED → RUNNING` is one-time and persisted; restart reconciliation maps `RUNNING → UNKNOWN`.
- `extension/background.js`: before an auto-send attempt, an authenticated one-use claim must match immutable job ID, human-approval ID, host ID, complete command digest, browser-computed result digest, outbound ID and origin. Invalid bindings become terminal local blocked receipts. Existing STAGE_ONLY operation is unchanged.
- `mock/backend.py`: still an in-memory loopback fixture, but requires claim bindings and locks one-time claim consumption. It cannot create genuine human approval through public endpoints.
- The actual SSH executor, credentials/host-key configuration, operator approval UI, production FastAPI/SQLite integration, output redaction and real auto-send test are **not yet implemented**. Do not conflate successful contract tests with authorization to execute commands.

### Isolierter UI-Freigabeschritt

Das Brave-Seitenpanel besitzt jetzt eine ausdrücklich als Mock bezeichnete SSH-Review-Ansicht. `GET /api/bridge/v1/ssh/proposals` zeigt offene, validierte Vorschläge einschließlich unveränderlichem Digest und vollständig geordnetem Block. `approve/reject` wird nur nach einer separaten Benutzeraktion in der vertrauenswürdigen Extension-Seite weitergeleitet; die Mock-API fordert Bearer-Token und prüft Ursprung und Digest erneut. Ohne konfigurierte `BRIDGE_ALLOWED_HOSTS` und `BRIDGE_APPROVAL_DB` ist diese Review-Funktion inaktiv. Ein bestätigter Vorschlag aktiviert weder Executor noch Auto-Send.

### Offline SSH fixture executor (2026-11-15)

`worker/mock_executor.py` konsumiert `ApprovalStore`-Datensätze nur im Status `APPROVED` mit passender Approval-ID, Hostkonfiguration und frisch nachberechnetem Batch-Digest. Eine Fixture-Map liefert vorgegebene stdout/stderr/Exitcodes/Timeoutflags; der Executor führt die gespeicherten Befehle **niemals** aus. Vor der simulierten Bearbeitung persistiert er `RUNNING`, und schreibt anschließend terminalen Batchstatus sowie begrenzte Resultate atomar nach SQLite. Der optionale explizite Aufruf `worker.mock_cli`/ `windows-brave-simulate.ps1` kann einen bereits im Panel bestätigten Mock-Auftrag genau einmal simulieren. Kein API-Endpoint startet die Simulation automatisch, und kein Browser-Auto-Send ist angeschlossen.

### Read-only mock result observation

The isolated mock backend now exposes authenticated `GET /api/bridge/v1/ssh/mock-results`. It lists a bounded window of completed SQLite fixture results joined to their original host, tab and conversation. The MV3 background permits `LIST_MOCK_RESULTS` only from its exact trusted `panel.html` origin. The side panel renders each result inside a collapsed details element using `textContent`. This path cannot claim an SSH job, simulate one again or enqueue ChatGPT outbound text.

### Unwired OpenSSH transport contract

`worker/ssh_transport.py` defines operator-side pinned `SSHHostConfig`, isolated OpenSSH argv/known_hosts construction and a bounded process runner. It is **not imported or used** by `mock/backend.py`, the Chrome extension, the mock executor or any scheduler. Only fake-runner offline tests are permitted at this stage; real host connectivity, trusted operator authorization and durable result routing are separate forthcoming gates. A local `ssh` kill cannot guarantee the remote shell stopped: uncertain executions must remain `UNKNOWN`, not replayed.

### Offline ApprovalStore-to-Transport Contract (2026-11-15)
`worker/execution_coordinator.py` bridges a previously approved SQLite batch to an injected **fixture-only** transport for test coverage of ordered command execution, immutable digest validation, single-use `APPROVED → RUNNING`, terminal result persistence, fail-stop, and crash recovery to `UNKNOWN`. It deliberately rejects ordinary transport objects and has no endpoint, CLI, or scheduled entry point. An additional `FixtureOnlyPermit` object must be supplied by test code. This marker is not a production authentication mechanism; do not connect it to HTTP, UI or real SSH. A distinct, authenticated real execution authorization and durable audit trail are required for any future live integration.
