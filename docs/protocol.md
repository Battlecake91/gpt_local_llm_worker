# Message protocol v1

ChatGPT must provide a fenced JSON object explicitly labeled as a worker request. Only exact schema-compliant requests become proposals. Natural-language commands remain inert.

Example:
```json
{
  "schema_version": 1,
  "kind": "ssh_batch",
  "request_id": "example-001",
  "target": "nas",
  "working_directory": "/tmp",
  "commands": [
    {"id": "check-host", "command": "uname -a", "timeout_seconds": 15}
  ],
  "description": "Read-only host identification"
}
```

The server validates IDs, command lengths, target allowlist, max commands and timeout bounds. It canonicalizes the batch and computes an approval digest. Approval never accepts edited command text. Future prose recognition may suggest a draft proposal, but it cannot bypass explicit schema validation and user approval.

Example execution result:
```json
{
  "schema_version": 1,
  "kind": "ssh_batch_result",
  "request_id": "example-001",
  "status": "succeeded",
  "commands": [
    {"id": "check-host", "exit_code": 0, "stdout": "...", "stderr": ""}
  ]
}
```

Never interpret an assistant's claim of successful execution as an actual execution result. Only executor-generated results may be returned as such.


## Browser transport (separate from SSH batch protocol)
The versioned `/api/bridge/v1` transport carries completed assistant messages and outbound stage/send requests. It does not change the `ssh_batch` schema or authorize SSH commands. See [bridge transport protocol](bridge-protocol.md). The mock backend exposes a one-use claim fixture but does not implement actual human approval. A browser send-click acknowledgement must not be mistaken for ChatGPT server acceptance.
