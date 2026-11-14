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
