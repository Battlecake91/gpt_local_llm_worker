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
