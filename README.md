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
Architecture and safety contracts are documented. No live SSH execution or browser automation has been deployed.

See [architecture](docs/architecture.md), [security](docs/security.md), [protocol](docs/protocol.md), and [AGENTS.md](AGENTS.md).


## Brave bridge implementation (feature/brave-chat-bridge)
A testable MV3 bridge is implemented in `extension/`, with an isolated FastAPI mock in `mock/backend.py` and Node/Python tests in `tests/`. This is **not** a deployed SSH worker: Ollama, approval UI, persistent production queue and executor are still separate planned components. The side panel currently shows bridge status, not SSH approval controls.

Run tests from the repository root:
```bash
node --test tests/*.cjs
python -m unittest discover -s tests -p 'test_mock.py' -v
```

See [installation and mock smoke test](INSTALL.md), [bridge API contract](docs/bridge-protocol.md), and [live-test status](docs/work-in-progress/brave-chat-bridge.md). Actual Brave runtime support is **not verified**. Auto-send is disabled except for mock-tested backend-approved result claims; do not use it with a real ChatGPT session without separate explicit authorization.
