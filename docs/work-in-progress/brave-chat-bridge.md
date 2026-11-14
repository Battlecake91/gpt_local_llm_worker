# Brave Chat Bridge, Entwicklungsauftrag 001

Stand: 2026-11-14. Ausgangsbranch `feature/worker-mvp`; Implementierung auf `feature/brave-chat-bridge`. **Code, Tests und Dokumentation auf GitHub committed; realer Brave-Test offen.**

## Implementierte Komponenten
- `extension/manifest.json`: Manifest V3, chatgpt.com Content-Script, Loopback-Hostberechtigung, Status-Seitenpanel.
- `extension/bridge-core.js`: Stop-Button-Zustandsmaschine (IDLE, GENERATING, FINALIZING, COMPLETED, CANCELLED, ERROR), 650-ms-Stabilisierung.
- `extension/content.js`: MutationObserver, SHA-256-Nachrichtenidentität, Tab-/Chatprüfung, Editor-Staging und bedingter Sendeklick.
- `extension/background.js`: authentifizierte Loopback-API, Capture-Queue, Retry, Tab-Routing, einmalige Claims und persistierte Sendereceipts.
- `extension/panel.*`: Status, Aktivierung und flüchtige Token-Eingabe.
- `mock/backend.py`: FastAPI-Fixture ohne SSH-Ausführung oder echte Benutzerfreigabe.
- `tests/`: deterministische Node-Fixtures und FastAPI-TestClient.
- `docs/bridge-protocol.md` und `INSTALL.md`: API-Vertrag und Installation.

## Sicherheitsentscheidungen
- Eingehende Inhalte sind Daten, keine Berechtigungen; die Erweiterung interpretiert keine SSH-Aufträge.
- Auto-Send erfordert einen serverseitigen, einmalig vergebenen Claim für einen genehmigten SSH-Resultatauftrag mit derselben Chat-ID und Tab-ID.
- `SUBMIT_CLICKED` bestätigt lediglich einen DOM-Klick, nicht die Annahme durch ChatGPT.
- Versandversuche werden vor dem Klick gespeichert; unklare Ergebnisse dürfen nicht automatisch wiederholt werden.
- Authentifizierungstoken nur im flüchtigen Speicher des MV3-Service-Workers.
- Nur `https://chatgpt.com/c/<id>` wird als eindeutig identifizierte Konversation unterstützt.

## Tatsächlich ausgeführte Offline-Tests
- `node --test tests/*.cjs`: **20/20 PASS** (lokaler Paketstand am 14.11.2026).
- `python -m unittest discover -s tests -p 'test_mock.py' -v`: **3/3 PASS**.
- `node --check extension/*.js` einzeln: **PASS**.
- Prüfung der GitHub-Übertragung erfolgt über GitHub-Dateiabruf; kein echter Browser-Smoke-Test durchgeführt.

## Grenzen und offene Tests
1. **Realer Brave/ChatGPT-Test offen**: DOM-Selektoren, Stop-Signal, Staging, Seitenpanel und CORS müssen mit einer ausdrücklich dafür bestimmten Testkonversation geprüft werden.
2. Stop-Button-Verschwinden kann bei Plattformfehlern einem regulären Ende ähneln. Die Erweiterung kann dies nicht immer zuverlässig unterscheiden.
3. Inhaltshash ohne eindeutige DOM-Nachrichten-ID kann identische Antworten in derselben Konversation deduplizieren.
4. React/ProseMirror kann `execCommand` je nach ChatGPT-Version unterschiedlich verarbeiten; ein Verification-Failure verhindert Weiterleitung.
5. Das Mock-Backend simuliert einen atomaren Claim, **nicht** die eigentliche SSH-Freigabeprüfung und nicht deren Persistenz.
6. Die Queue des Mock-Backends ist im Speicher; Neustarts verlieren Mock-Nachrichten.
7. Bis zum Browser-Test **keine produktive Nutzung und kein echter Auto-Send**.
8. Die Tests sind keine vollständigen DOM-Integrationstests eines echten Brave-Browsers.

## Außerhalb des Scopes
Keine Änderungen an SSH-Executor, Ollama, Docker oder anderen Feature-Branches. Kein Merge nach main.

## Nächste Schritte
`INSTALL.md` für das Laden der Erweiterung und Mock-Backend verwenden. Ausschließlich `STAGE_ONLY` im Live-Browser manuell testen. Auto-Send nur mit separater ausdrücklicher Freigabe für isolierten Browser-Test.

## Windows-Testvorbereitung, Nachtrag 2026-11-14
- `scripts/windows-brave-mock.ps1` erstellt und committed: richtet einen lokalen Python-Venv ein, führt Mock-Tests aus und startet den FastAPI-Mock ausschließlich auf `127.0.0.1:8765`.
- `scripts/windows-brave-stage.ps1` erstellt und committed: stellt ausschließlich eine `STAGE_ONLY`-Testnachricht ein.
- `INSTALL.md` um PowerShell-Anleitung, tab- und konversationsgebundenen Staging-Test, Negativfälle und Fehlersuche erweitert.
- Ausführungsstatus: **PowerShell-Skripte und realer Windows-Brave noch nicht auf dem Benutzerrechner gestartet**. Dieser isolierte Ausführungsraum hat keinen Zugriff auf den dort laufenden Browser.
- Bestehende lokale Node-/Python-Fixture-Tests: 20/20 und 3/3 PASS; das ist kein Ersatz für einen Windows-Brave-Smoke-Test.
- Folge-Commit der Windows-Installationsanleitung: `33a6de43677fee3850461d478259c8e6ea247771`.
