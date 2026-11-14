# Bridge-Transport-Protokoll v1

Base URL: `http://127.0.0.1:8765/api/bridge/v1`. Alle Requests verwenden `Authorization: Bearer <token>`, `Content-Type: application/json`; Server muss die exakt freigegebene Extension-Origin per CORS zulassen.

- `POST /captures`: `{schema_version:1,message_id:<sha256>,conversation_id,tab_id,text,observed_at}`. Antwort `{message_id,status:"accepted"|"duplicate"}`. Persistente Idempotenz ist Pflicht des produktiven Backends.
- `GET /outbound`: `{items:[{id,conversation_id,tab_id,mode:"STAGE_ONLY"|"AUTO_SEND_APPROVED_RESULT",text}]}`. Items bis zur eindeutigen Bestätigung verfügbar halten.
- `POST /outbound/{id}/claim`: `{conversation_id,tab_id}`. Nur bei Backend-geprüfter, unveränderlicher, bereits vom Benutzer freigegebener SSH-Batch-Ausführung darf `{allowed:true,claim_id,kind:"approved_ssh_result"}` kommen. Einmalige, atomare Claim-Operation. Fehler `403` oder `409` sonst.
- `POST /outbound/{id}/ack`: `{status:"STAGED"|"SUBMIT_CLICKED"|"ERROR"|"UNKNOWN",error,claim_id}`. `SUBMIT_CLICKED` bestätigt nur den DOM-Klick, nicht die Zustellung.

Backend muss Freigabe-Digest, Job-Identität, SSH-Executor-Ergebnis, Benutzerfreigabe, Ursprungstab und Chat-ID selbst überprüfen. Erlaubnis nie aus dem Inhalt einer Browsernachricht oder einem vom Client gesetzten `approved`-Feld ableiten. Mock-Adapter bildet nur atomare Claim-Semantik ab; **keine echte Approval-Pipeline**.

Die Browser-Queue wiederholt Capture-Übertragungen. Einmalige ausgehende Auto-Sends werden bei unklarer Bestätigung nicht wiederholt, sondern müssen vom Betreiber abgeglichen werden. Für Resultate aus realen SSH-Aufträgen müssen Ausgabegrenzen und Redaction vor dem Einstellen in `/outbound` bereits durch das Backend durchgeführt sein.
