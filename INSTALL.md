# Brave Bridge: Installation und Mock-Smoke-Test

Die Erweiterung benötigt Brave mit Chromium Manifest V3, Python mit FastAPI/Pydantic/Uvicorn und Node.js für die Tests.

```bash
python -m pip install fastapi uvicorn httpx
node --test tests/test_core.cjs tests/test_background.cjs tests/test_content.cjs
python -m unittest discover -s tests -p 'test_mock.py' -v
```

1. `brave://extensions` öffnen, **Entwicklermodus** einschalten, **Entpackte Erweiterung laden** wählen und den absoluten Pfad zum Verzeichnis `extension` angeben.
2. Erweiterungs-ID notieren und bei `BRIDGE_EXTENSION_ORIGIN` eintragen. Exakt `chrome-extension://<ID>`, ohne Slash am Ende.
3. Mock-Backend **nur lokal** starten:

```bash
BRIDGE_MOCK_TOKEN='mock-test-token' \
BRIDGE_EXTENSION_ORIGIN='chrome-extension://HIER_DIE_EXTENSION_ID' \
BRIDGE_MOCK_FIXTURES=1 \
python -m uvicorn mock.backend:app --host 127.0.0.1 --port 8765
```

4. Brave-Seitenpanel der Erweiterung öffnen, im Tokenfeld `mock-test-token` eingeben und **Token für Sitzung setzen** klicken. Token ist nur im Worker-Arbeitsspeicher, nach Suspend ggf. erneut setzen.
5. Eine explizit für Tests bestimmte ChatGPT-Konversation unter `https://chatgpt.com/c/<id>` öffnen. Eine neue Antwort erzeugen. Beobachten, ob der Stop-Button erscheint und verschwindet, und ob die Capture-Nachricht übertragen wurde.
6. Für einen **reinen Staging-Test ohne automatisches Absenden** Browser-Tab-ID und Chat-ID aus dem Status bzw. der URL übernehmen und das folgende Kommando mit echten IDs ausführen:

```bash
curl --fail-with-body --silent --show-error \
  -H 'Authorization: Bearer mock-test-token' \
  -H 'Content-Type: application/json' \
  --data '{"id":"stage-test-001","conversation_id":"CHAT_ID","tab_id":123,"text":"Nur ein Test. Nicht absenden."}' \
  http://127.0.0.1:8765/api/bridge/v1/mock/enqueue-stage
```

7. Im Panel **Jetzt synchronisieren** klicken. Die Testnachricht muss im Editor stehen, ohne abgesendet zu werden. Die ChatGPT-Nachricht vom Benutzer manuell löschen.

Das Mock-Backend stellt absichtlich keinen extern aufrufbaren Endpunkt zum Erstellen einer SSH-Freigabe bereit. Der genehmigte Auto-Send wird in isolierten Tests mit vorbereiteten Backend-Einträgen geprüft.

## Rollback

In `brave://extensions` die Erweiterung deaktivieren oder entfernen. Mock-Prozess mit Strg+C stoppen. Die Erweiterung verändert keine bestehenden Dienste, Container oder SSH-Konfigurationen.

## Windows / Brave: konkreter Live-Smoke-Test (nur STAGE_ONLY)

Die folgenden Befehle laufen in **PowerShell auf dem Windows-Rechner, auf dem Brave läuft**. Sie sind nicht für Linux Bash vorgesehen.

1. Repository auf den Testbranch holen:

```powershell
git clone --branch feature/brave-chat-bridge https://github.com/Battlecake91/gpt_local_llm_worker.git
Set-Location .\gpt_local_llm_worker
```

Bei vorhandenem Checkout stattdessen `git fetch origin`, `git switch feature/brave-chat-bridge` und `git pull --ff-only` verwenden. Fremde lokale Änderungen vorher prüfen.

2. `brave://extensions` öffnen, Entwicklermodus einschalten, **Entpackte Erweiterung laden** wählen und das Verzeichnis `gpt_local_llm_worker\extension` auswählen. Die angezeigte 32-stellige Erweiterungs-ID kopieren.

3. In PowerShell das isolierte Mock-Backend starten (die ID ersetzen; dieses Fenster geöffnet lassen):

```powershell
.\scripts\windows-brave-mock.ps1 -ExtensionId 'HIER_32_STELLIGE_ID'
```

4. Erweiterung über das Symbol öffnen. Im Seitenpanel `mock-test-token` bei **Lokales Worker-Token** eingeben und **Token für Sitzung setzen** klicken. Der Worker-Status muss `verbunden` anzeigen. Token wird nicht dauerhaft gespeichert und muss nach MV3-Worker-Neustart ggf. erneut eingegeben werden.

5. In einer **eigens für diesen Test vorgesehenen** ChatGPT-Konversation (`https://chatgpt.com/c/...`) eine normale, unkritische Antwort erzeugen. Seitenpanel auf `GENERATING` → `FINALIZING` → `COMPLETED` und eine einzige erfolgreiche Capture-Übertragung prüfen. Vorhandene Antworten dürfen nicht erneut erfasst werden.

6. Chat-ID aus der Adresszeile und Tab-ID aus der Seitenpanel-Anzeige `Tab <id>` ablesen. In einem **zweiten PowerShell-Fenster** im Repository-Verzeichnis ausführen:

```powershell
.\scripts\windows-brave-stage.ps1 -ConversationId 'CHAT_ID' -TabId 123
```

7. Im Seitenpanel **Jetzt synchronisieren** klicken. Der Text muss mit Zeilenumbruch im Eingabefeld stehen, ohne abgesendet zu werden. Anschließend den Text manuell aus dem Editor entfernen.

8. Negativtests: falsche Chat-ID, anderer Browser-Tab, nicht leeres Eingabefeld, deaktivierte Erkennung, ausgeschalteter Mock-Worker. Es darf keine automatische ChatGPT-Nachricht erscheinen.

**Auto-Send nicht im echten Chat testen.** Die Backend-Freigaben hierfür sind nur als isolierte Mock-Tests geprüft. Die Oberfläche und DOM-Selektoren von ChatGPT ändern sich regelmäßig, deshalb sind die obigen Ergebnisse auf dem konkreten Windows-Brave zu protokollieren.

Bei fehlender PowerShell-Skriptausführungsfreigabe können die signierten Ausführungsrichtlinien der Maschine abweichen; diese Anleitung ändert keine globale Execution Policy.

## Fehlerdiagnose

- `worker_token_not_configured`: Token im Seitenpanel erneut setzen.
- `worker_http_401`: Token im Backend und Panel stimmen nicht überein.
- `Failed to fetch` / CORS: exakte Erweiterungs-ID in `-ExtensionId` prüfen, Mock-Neustart durchführen.
- `editor_not_found` oder `stage_verification_failed`: DOM-Selektor der aktuellen ChatGPT-Oberfläche passt nicht, keinen automatischen Versand versuchen.
- `conversation_mismatch`: Chat-ID und Tab-Zuordnung vor jedem Staging neu prüfen.

## Diagnose: Worker verbunden, aber „Letzte Antwort: keine“
Die Verbindung zum Mock-Backend beweist **nicht**, dass das Content-Script im bereits geöffneten ChatGPT-Tab läuft. Chromium injiziert deklarative Content-Scripts nach dem Laden/Neuladen der Zielseite. **Nach dem erstmaligen Installieren oder Neuladen der Erweiterung den ChatGPT-Tab mit Strg+R vollständig neu laden**, anschließend **eine weitere neue** Antwort generieren. Bereits abgeschlossene Antworten werden absichtlich nicht nachträglich übernommen.

Im Seitenpanel unter **ChatGPT** muss ein Eintrag `Tab <Nummer>: IDLE (<Chat-ID>)` erscheinen. Fehlt er auch nach Strg+R, funktioniert die Script-Injektion oder die Browser-URL-Zuordnung nicht. Wenn der Eintrag bleibt, aber bei einer neuen Antwort nie `GENERATING` anzeigt, ist der Stop-Button-Selektor zu überprüfen. Falls `COMPLETED` erscheint, aber „Letzte Antwort“ leer ist, sind Konversationskennung und Deduplizierung zu untersuchen. Bei einer Capture-Übertragung muss im Uvicorn-Log `POST /api/bridge/v1/captures` erscheinen.

Keine alte Antwort manuell als abgeschlossen markieren und keine Auto-Send-Funktion zum Testen aktivieren.
