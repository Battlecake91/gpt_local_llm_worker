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
