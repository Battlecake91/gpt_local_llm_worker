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
