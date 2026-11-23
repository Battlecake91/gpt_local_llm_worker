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

## Implementierter Offline-Validator und Freigabekatalog

Der Parser `worker/ssh_protocol.py` implementiert **exakt das obige `kind:"ssh_batch"`-Schema**. Einmaliger JSON-Fence oder reines JSON; keine Befehlsinterpretation aus gewöhnlichem Text. `target` muss ein vorab konfigurierter Alias sein. `working_directory` muss absolut sein und darf keine `..`-Segmente enthalten. Maximal 32 Befehle; jeder benötigt eindeutige `id`, nichtleeren `command` (bis 8192 Zeichen) und ganzzahligen `timeout_seconds` von 1 bis 300. Mehrdeutige doppelte JSON-Schlüssel und unbekannte Felder sind verboten.

Der `command_sha256` wird gebildet aus kanonischem UTF-8-JSON (mit sortierten Schlüsseln, kompakten Separatoren und `ensure_ascii=False`) über **`schema_version`, `target`, `working_directory`, die vollständig geordnete `commands`-Liste mit IDs/Befehlen/Timeouts und `description`**. `request_id` ist ein eigenständiger persistenter Identitätsschlüssel; Ursprungstab und Chat-ID werden separat mit diesem Schlüssel gespeichert. Jede Änderung an einem dieser Inhaltsfelder erzeugt einen anderen Digest.

`worker/approval_state.py` legt diese Aufträge in SQLite als `PROPOSED` ab, verhindert `request_id`-Kollisionen, erlaubt eine spätere explizite Einmalfreigabe **nur** mit exakt passendem Digest, und hält `RUNNING` über den Transaktionsabschluss vor jedem möglichen Ausführungsstart fest. Nach Neustart kann `RUNNING` zu `UNKNOWN` überführt werden, niemals automatisch erneut zu `RUNNING`.

**Noch nicht implementiert:** authentifizierte operatorseitige Freigabe-UI, produktiver API-Endpunkt, SSH-Executor, Hostkey-Pinning, Ausgabelimits, vollständiger Audit-Log und tatsächliche resultierende Browser-Auto-Send-Integration. Die Klasse `ApprovalStore.approve()` setzt voraus, dass ihr Aufrufer zuvor eine menschliche, authentifizierte Aktion geprüft hat; sie führt diese Prüfung nicht selbst durch.

### SSH-Transportstatus (2026-11-15)

Ein eigenständiger OpenSSH-Adapter erzeugt argv-Aufrufe mit isoliertem Hostkey-Pin, nichtinteraktiver Anmeldung und realer Prozess-Timeout-Grenze. **Er ist nicht mit dem Protokoll-Parser, dem Freigabe-Store oder der Brave-API verbunden.** Ein gültiger `kind:"ssh_batch"`-Auftrag oder eine Mock-Freigabe lösen daher nach wie vor **keine reale SSH-Verbindung** aus.

### Brave-Extraktion und unbeschriftete JSON-Codeblöcke (2026-11-23)
Die Brave-Erweiterung kann einen gerenderten JSON-Codeblock als `\`\`\` ... \`\`\`` ohne Sprachlabel extrahieren. Der Validator akzeptiert deshalb jetzt neben reinem JSON und `\`\`\`json` auch **einen einzigen unbeschrifteten JSON-Fence** innerhalb einer erklärenden Antwort. Das innere JSON muss weiterhin das vollständige `schema_version:1`, `kind:"ssh_batch"`-Schema erfüllen. Bei mehreren unbeschrifteten/JSON-Fences wird die Verarbeitung als mehrdeutig abgelehnt. Gewöhnlicher Fließtext bleibt inert. Die Erkennung schreibt nur einen `PROPOSED`-Vorschlag ins LIVE-Journal; keine SSH-Ausführung oder Browser-Auto-Send-Freigabe wird dadurch möglich. Ein bereits mit `accepted` quittierter Capture wird nicht rückwirkend neu geparst: nach Worker-Neustart muss eine **neue** vollständig abgeschlossene Antwort gesendet werden.
