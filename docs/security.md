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
