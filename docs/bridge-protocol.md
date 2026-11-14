# Bridge-Transport-Protokoll v1

Base URL: `http://127.0.0.1:8765/api/bridge/v1`. Alle Requests verwenden `Authorization: Bearer <token>`, `Content-Type: application/json`; Server muss die exakt freigegebene Extension-Origin per CORS zulassen.

- `POST /captures`: `{schema_version:1,message_id:<sha256>,conversation_id,tab_id,text,observed_at}`. Antwort `{message_id,status:"accepted"|"duplicate"}`. Persistente Idempotenz ist Pflicht des produktiven Backends.
- `GET /outbound`: `{items:[{id,conversation_id,tab_id,mode:"STAGE_ONLY"|"AUTO_SEND_APPROVED_RESULT",text}]}`. Items bis zur eindeutigen Bestätigung verfügbar halten.
- `POST /outbound/{id}/claim`: `{conversation_id,tab_id}`. Nur bei Backend-geprüfter, unveränderlicher, bereits vom Benutzer freigegebener SSH-Batch-Ausführung darf `{allowed:true,claim_id,kind:"approved_ssh_result"}` kommen. Einmalige, atomare Claim-Operation. Fehler `403` oder `409` sonst.
- `POST /outbound/{id}/ack`: `{status:"STAGED"|"SUBMIT_CLICKED"|"ERROR"|"UNKNOWN",error,claim_id}`. `SUBMIT_CLICKED` bestätigt nur den DOM-Klick, nicht die Zustellung.

Backend muss Freigabe-Digest, Job-Identität, SSH-Executor-Ergebnis, Benutzerfreigabe, Ursprungstab und Chat-ID selbst überprüfen. Erlaubnis nie aus dem Inhalt einer Browsernachricht oder einem vom Client gesetzten `approved`-Feld ableiten. Mock-Adapter bildet nur atomare Claim-Semantik ab; **keine echte Approval-Pipeline**.

Die Browser-Queue wiederholt Capture-Übertragungen. Einmalige ausgehende Auto-Sends werden bei unklarer Bestätigung nicht wiederholt, sondern müssen vom Betreiber abgeglichen werden. Für Resultate aus realen SSH-Aufträgen müssen Ausgabegrenzen und Redaction vor dem Einstellen in `/outbound` bereits durch das Backend durchgeführt sein.

## Verbindlicher Auto-Send-Vertrag (Version 1, fail-closed)

`AUTO_SEND_APPROVED_RESULT` ist **nicht** durch die Existenz einer `claim_id` allein autorisiert. Das Backendergebnis von `GET /outbound` muss zusätzlich folgende Struktur enthalten:

```json
{
  "id": "outbound-id",
  "mode": "AUTO_SEND_APPROVED_RESULT",
  "conversation_id": "original-chat-id",
  "tab_id": 123,
  "text": "unveränderter SSH-Ergebnistext",
  "approval": {
    "job_id": "ssh-job-id",
    "approval_id": "separate-user-approval-id",
    "host_id": "konfigurierter-host",
    "command_sha256": "64 lowercase hex digits",
    "result_sha256": "64 lowercase hex digits"
  }
}
```

Der SHA-256 `command_sha256` beschreibt **den vollständigen und kanonisch serialisierten SSH-Befehlsblock samt Zielhost**; `result_sha256` ist SHA-256 über die unveränderten UTF-8-Bytes von `text`. Der Browser berechnet den Ergebnis-Digest selbst und verlangt eine genaue Übereinstimmung.

`POST /outbound/{id}/claim` enthält neben `conversation_id` und `tab_id` nun auch `job_id`, `approval_id` und `result_sha256`. Eine erfolgreiche Antwort muss die Felder `allowed:true`, `kind:"approved_ssh_result"`, `claim_id`, `outbound_id`, `conversation_id`, `tab_id`, `job_id`, `approval_id`, `host_id`, `command_sha256` und `result_sha256` unverändert zurückliefern. Fehlende oder abweichende Daten sperren die automatische Sendung.

Diese Spiegelung beweist **nicht selbst**, dass der Benutzer zugestimmt hat. Das produktive Backend muss die Freigabe in einer separat authentifizierten Handlung des Benutzers für den **gesamten Befehlsblock** erfassen und dauerhaft an den konkreten Auftrag binden; ChatGPT-Ausgabetext darf keine Freigabe erzeugen. Der Mock-Adapter besitzt weiterhin **keinen** öffentlichen Weg zur Erstellung solcher Freigaben.

Nach einem gültigen Claim wird vor dem DOM-Klick ein dauerhaftes `ATTEMPTING`-Receipt geschrieben. Nach Neustart oder unklarem Status **nicht erneut automatisch senden**. Eine positive `SUBMIT_CLICKED`-Quittung beweist nur den Klick, nicht die Zustellung an ChatGPT. `STAGE_ONLY` benötigt keine SSH-Freigabe und klickt nie.

**Migration:** Backend-Versionen, die nur `allowed/claim_id/kind` liefern, sind absichtlich inkompatibel mit Auto-Send und werden abgewiesen. Die bestätigte manuelle STAGE_ONLY-Strecke bleibt kompatibel.
