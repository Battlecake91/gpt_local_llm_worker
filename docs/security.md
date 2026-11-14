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
