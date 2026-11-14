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

## Windows-Brave-Befund und Diagnose-Fix, 2026-11-14
- Benutzer bestätigte: Mock-Worker im Seitenpanel **verbunden**; ChatGPT-Tab im Panel sichtbar. Eine neue vollständige Antwort wurde **nicht** als letzte Antwort erfasst. Die Ursache im Live-DOM ist noch nicht nachgewiesen.
- Fix `extension/bridge-core.js`: Wiederholte unveränderte DOM-Mutationen dürfen das FINALIZING-Zeitfenster nicht unbegrenzt verlängern.
- Diagnose `extension/content.js`, `background.js`, `panel.*`: Anzahl erkannter Assistentenantworten, letzte Nachrichtenrolle, Anzahl Textzeichen, Stop-Button-Erkennung (aktuell und jemals), alternative Kandidat-Button-Metadaten und Scan-Zähler je Tab. Diagnose zeigt **keinen Antworttext** und keine Tokens.
- `tests/test_core.cjs`: Regression für wiederholte DOM-Mutationen sowie echte Textänderungen während der Stabilisierung ergänzt.
- Verifiziert im isolierten lokalen Paket mit identischen Git-Blob-Hashes für die geänderten Erweiterungsdateien: `node --test tests/*.cjs` **22/22 PASS**, `python -m unittest discover -s tests -p 'test_mock.py' -v` **3/3 PASS**, `node --check` für alle Erweiterungs-JS-Dateien PASS.
- Realer erneuter Windows-Livetest **ausstehend**: `git pull --ff-only`, Erweiterung über `brave://extensions` neu laden, ChatGPT-Tab mit Strg+R neu laden, neue Antwort erzeugen, Diagnosewerte im Seitenpanel auswerten. Kein Auto-Send.

## Live DOM-Abweichung (2026-11-14)
- Gemessene Werte: Tab 2006233083: `assistantCount=0`, `stopEverSeen=false`, `lastRole=none`, `hasConversation=true`, `scanCount=134`; Tab 2006233101 ebenfalls keine Nachrichten, `hasConversation=false`.
- Ergebnis: Das Content-Script läuft und beobachtet DOM-Mutationen, aber aktuelle Legacy-Selektoren liefern keinen Assistant-Turn und keinen Stop-Button. Der Fehler ist **nicht** die Loopback-Verbindung.
- Fix-Strategie: zuerst nur metadata-only Instrumentierung für alternative Marker, darunter `data-turn-key`, `data-content-search-unit-key`, `data-chatgpt-search-unit-key`, neue App-Shell-Attribute sowie ProseMirror-Composer. Keine automatische Sendefreigabe; keine Chat-Texte in der Diagnose.
- Diagnose-Commit: `1d5acca315df06d988e55b5dc322e2d0e89d5b90`.
- **Nächste Benutzerhandlung**: Git-Pull, Erweiterung und ChatGPT-Tab neu laden, eine neue Antwort erzeugen, den Bereich `selectorCounts` und `attributeHints` weitergeben. Erst danach den korrekten DOM-Adapter implementieren und reale Funktion erneut überprüfen.
- Zusätzlicher Diagnose-Commit wurde nicht in einem realen Windows-Brave ausgeführt. Kein Erfolg der Antwort-Erkennung behauptet.

## Modern-ChatGPT-Adapter (2026-11-14, Live-Fixture-Metadaten)
- Bestätigte DOM-Merkmale: je 5 `[data-content-search-unit-key$=":assistant"]` und `...:user`, 5 `[data-markdown-text-style="assistant-message"]`, 5 `[data-turn-key]`; Legacy-Rollenmarker und `.markdown` jeweils 0.
- `extension/bridge-core.js`: Legacy + moderne Assistant/User-Selektoren, Rollenauflösung aus `data-content-search-unit-key`, Extraktion des modernen Markdown-Containers, moderne stabile Nachricht-ID, zusätzliche explizite Stop-Aria-Labels.
- `extension/content.js`: Baseline verwendet moderne Message-Identität, Abschluss prüft aktuellen letzten Assistant-Turn/ungeänderten Text und fehlenden Stop-Button erneut. Metadaten-Diagnose um Stop-Selektoren erweitert.
- `tests/test_core.cjs`: moderne DOM-Fixture und Gate ohne zuvor beobachtetes Stop-Signal. In lokal reproduziertem Teststand: Node-Testlauf **22/22 PASS** (älterer Paketstand mit nachgestellten Core-Änderungen; **kein vollständiger Test des aktuellen GitHub-Branches**). Der echte Windows-Brave-Test bleibt offen.
- **Wichtiger offener Punkt:** `stopEverSeen=false` in einer Diagnose nach abgeschlossener Antwort bestätigt nicht, ob die neue Stop-Schaltfläche während der Generierung einen erkennbaren Selektor besitzt. Ohne beobachtetes Stop-Signal wird weiterhin **nicht** automatisch als abgeschlossen klassifiziert.
- Neuer Test: Repo pull, Erweiterung neu laden, Chat neu laden, eine neue Antwort generieren; im Panel `assistantCount`, `lastRole`, `lastAnswerLength`, `stopEverSeen` und Zustandsübergänge kontrollieren. Keine Echt-Auto-Sends.

## Stop-Button-Forensik, Windows-Befund 2026-11-14
- Bestätigter Zustand nach vollständiger Antwort: `assistantCount=6`, `lastRole=assistant`, `lastAnswerLength=345`, `modernAssistant=6`, `stopEverSeen=false`. **Der neue Assistant-Adapter erkennt Nachrichten.** Abschluss-Signal weiterhin ungeklärt.
- Neu: `extension/stop-probe.js` verfolgt über den vorhandenen MutationObserver höchstens 12 unterschiedliche Composer-Control-Zustände, ohne Chat-Nachrichtentext, mit Test-ID, Aria-Label, Titel, Disabled-Zustand und Anzahl SVG-Rechtecke/Pfade. Der Verlauf bleibt nach Generierungsende im Panel unter `stopProbe.controlStates` sichtbar. Reset bei Konversationswechsel.
- Keine Änderung an automatischen Sende- oder Freigaberegeln. Insbesondere wird fehlendes Stop-Signal nicht als Antwortabschluss interpretiert.
- Neu: `tests/test_stop_probe.cjs` mit 3 Fixture-Tests. Die 3 neuen Tests wurden am 14.11.2026 in einem isolierten lokalen Node-22-Testverzeichnis ausgeführt: **3/3 PASS**, `node --check extension/stop-probe.js` PASS. Ein vollständiger aktualisierter GitHub-Checkout oder erneuter realer Brave-Test war hier nicht verfügbar.
- Benutzeraktion für erneuten Live-Test: Feature-Branch pullen, Erweiterung und Chat-Tab neu laden, eine neue längere Antwort generieren, danach `DOM neu prüfen` und aus dem Panel `stopProbe` sowie `stopEverSeen` übermitteln.

## Stop-Button durch Windows-Mitschnitt identifiziert
- Benutzer lieferte die `stopProbe.controlStates` mit 11 Zuständen. **Zustand 9/10** enthält das Composer-`button` mit `aria="Stoppen"`; Zustand 11 enthält wieder `Sprachchat starten`. Die aktiven Stop-/Sende-Buttons haben keine `data-testid`-Kennung.
- Root Cause: `core.STOP` enthielt `Stop generating` und `Generierung stoppen`, aber nicht das tatsächlich gemessene, lokalisierte `button[aria-label="Stoppen"]`.
- Änderung: Selektor um exakt diese nachgewiesene Variante erweitert (`2b3e575da6b8d52345efa97f4ae27bdb0045d64e`). Bestehende Click-Cancel-, Generating- und Finalizing-Logik nutzt denselben Selektor.
- Regressionstest für die spezifische Beschriftung, Start, Stabilisierung und vollständigen Abschluss hinzugefügt (`041a4899c714a1b7bc86b4edd936efadae3fa2d2`).
- Testausführung: In einem vorhandenen **älteren lokalen Testverzeichnis** mit angewendetem Stop-Selektor und gezielter Regression `node --test tests/*.cjs`: **24/24 PASS**; `node --check extension/bridge-core.js`: PASS. Der gesamte aktuelle GitHub-Branch konnte in dieser Umgebung nicht geklont und getestet werden (keine DNS-Erreichbarkeit von github.com). Die Regression im Repository ist inhaltlich gleichwertig, der vollständige neue Branch-Test aber noch offen.
- Live-Abnahme: noch nicht erneut in Windows-Brave geprüft. Erweiterung aktualisieren/neuladen, Chat-Tab neu laden, neue Antwort generieren; `stopEverSeen`, `GENERATING → FINALIZING → COMPLETED`, `lastCapture` und `POST /captures` bestätigen. Kein Auto-Send.

## Browser-Smoke: eingehende Antwort erfolgreich, Formatierungsfehler behoben (2026-11-14)
- Windows-Brave bestätigt `Letzte Übertragung.status="accepted"` für Capture-ID `9d39e7356c1bf2f6e6e2467fa7b9f971c93c51730e772600a9fac1ac65d784ab`. Dieselbe ID wurde zweimal im Benutzertext genannt; **keine zweite Backend-Übertragung nachgewiesen**.
- Fehler: `Letzte Antwort` zeigte zusammengezogenen Python-Code (`Python Ausführen import random zahlen ...`) ohne die ursprünglichen Zeilenumbrüche. Das Panel zeigte zudem nur `slice(0,300)`; daraus allein ließ sich keine Server-Trunkierung ableiten.
- Änderung: `extension/extractor.js` traversiert die DOM-Textstruktur, erhält `pre/code` mit Einrückungen und Fences, trennt Absätze und ignoriert Buttons. `bridge-core.readable` bevorzugt den strukturierten Extraktor; Legacy-Fallback bleibt. Manifest lädt den Extraktor vor dem Content-Script. In `background.js` ist die Vorschau auf 8000 Zeichen erweitert und meldet `length` und `truncated`.
- Test: `node --test tests/*.cjs` im lokalen Testverzeichnis: **28/28 PASS**; darunter `tests/test_extractor.cjs` 4/4 Tests für Codeblock-Zeilenumbrüche, Einrückungen, Absatzgrenzen, UI-Button-Ausschluss und Fence-Escaping. Der GitHub-Blob-SHA von `extractor.js` und `test_extractor.cjs` entspricht exakt dem lokal geprüften Stand. **Kein vollständiger aktueller GitHub-Checkout und kein erneuter Windows-Brave-Test**; die Live-Extraktion ist deshalb weiterhin offen.
- Folge: Git-Pull, Erweiterung neu laden, Chat-Tab neu laden, **neue** Antwort mit Python-Codeblock und Absätzen ausgeben lassen, Vorschau mit dem gerenderten Text vergleichen, Status `accepted` und Uvicorn-POST bestätigen. Kein Auto-Send.

## Weitere Live-Prüfung: Extraktion weiterhin strukturell falsch
- Benutzervergleich nach `9e9811b`: Letzte Antwort wurde zu `Pythonimport timedef countdown...` zusammengezogen; original gerenderte Antwort enthält Codeblock mit Einrückungen und mehrere Markdown-Absätze. Damit ist die frühere Formatierungsreparatur für diese DOM-Struktur **nicht ausreichend**.
- Konkreter Defekt in `extractor.js`: Textnodes werden mit `replace(/\\s+/g,' ')` normalisiert, also echte Zeilenumbrüche vernichtet. Das wurde entfernt; CRLF wird zu LF normalisiert. Markdown-Fettschrift/Kursivschrift werden als Formatierungszeichen erhalten.
- Noch ungeklärt: Welches DOM-Element die tatsächlich gezeigten Python-Codezeilen enthält, wenn weder `pre` noch klassische Absatzelemente passend erkannt werden. Deshalb `inspectStructure`: auf `DOM neu prüfen` wird ausschließlich für die letzte Assistentenantwort eine begrenzte Baumübersicht mit Tags, Kindanzahlen und Anzahl direkter Zeilenumbrüche erzeugt; **kein Text und keine Attributwerte**. Verfügbar als `structureTrace` im Seitenpanel.
- Ergänzte Tests: roher Zeilenumbruch in Textnodes, Markdown-Inlineformat, Datenschutzgrenze des Strukturberichts. Testcode committed, aber kompletter GitHub-Branch hier nicht erneut ausgeführt; realer Windows-Test offen.
- Der akzeptierte Capture bestätigt nur **Transport**, nicht semantische Richtigkeit der extrahierten Nutzlast. Keine Echtdaten automatisch zurücksenden.

## Iteration: Code-Editor-Zeilen und Authentifizierung (2026-11-14)
- Benutzeranweisung: Bearer-Token-Authentifizierung ausdrücklich **beibehalten**. Es wurden keine Änderungen an der Authentifizierung, dem API-Claim oder dem Auto-Send-Verhalten vorgenommen.
- `extension/extractor.js`: Codeblock-Erkennung für `pre`, `data-code-block="true"`, `.cm-content`, `.view-lines`; Source-Line-Rekonstruktion aus `.cm-line`, `.view-line`, `[data-code-line]`; wenn `textContent` keine Zeilenumbrüche hat, aber `innerText` welche besitzt, wird `innerText` genutzt. Sprachlabel/Fences und Codeeinrückungen bleiben erhalten.
- Tests in `tests/test_extractor.cjs` ergänzen DOM-Fixture für getrennte Editorzeilen und Fallback für browsergerenderte Zeilenumbrüche.
- Prüfung in lokaler Testkopie mit denselben Extraktor-Änderungen: `node --check extension/extractor.js` PASS; `node --test tests/*.cjs` **30/30 PASS**. **Kein vollständiger Live-Test mit dem aktuellen ChatGPT-DOM**; diese Checks belegen nur die erfassten Strukturfälle.
- Nächste verlässliche Abnahme: Benutzer pullt Branch, lädt Brave-Erweiterung und Chat-Tab neu, startet eine neue Antwort mit Python-Codeblock, vergleicht `Letzte Antwort` und originalen Quellcode. Bleiben Zeilenfehler, `DOM neu prüfen` klicken und `structureTrace` der betroffenen Assistant-Antwort bereitstellen, damit der reale Code-Container erkannt wird.

## Live-Strukturbericht 2026-11-14: konkreter Codeblock-Fix
- Benutzer liefert `structureTrace`: Letzte Antwort hat `div:16`, `p:4`, `span:20`, `strong:2`, `code:6`. Innerhalb des Assistenten-Markdown liegt auf Tiefe 7 ein `div` mit `marker:"code-block"`, dessen zwei direkte Kinder ein Header-`div` und ein Codeinhalt-`div` sind. Fünf direkte Markdown-Kinder: Absatz, Codeblock-Wrapper, drei Absätze. Stop-Button wurde nachweislich gesehen (`stopEverSeen:true`).
- Ursächlicher Fehler: `extractor.js` prüfte `getAttribute('data-code-block') === 'true'`. Der real beobachtete Codeblock war markiert, erfüllte die harte Vergleichsbedingung aber nicht; dadurch wurde er inklusive Header und Zeilen ohne Trennzeichen serialisiert.
- Fix: Prüfen, ob `data-code-block` vorhanden ist, unabhängig von seinem Wert. Für diesen Block gezielt den zweiten Element-Child (Quellcode) statt des ersten (Toolbar/Sprachlabel/Ausführen) auslesen. Vorhandene `.cm-line`-/`.view-line`- und `innerText`-Fallbacks bleiben; klassische `pre/code`-Extraktion wurde bei der Änderung ebenfalls geprüft.
- Regression `tests/test_extractor.cjs`: reale zweigeteilte `data-code-block`-Verschachtelung (Toolbar + Quelle), rekonstruierte Python-Einrückung, Markdown-Erklärung und Ausschluss von `Ausführen`.
- Lokale Testkopie mit dem relevanten Fix und aktualisiertem Regressionstest: `node --test tests/*.cjs` **31/31 PASS**, `node --check extension/extractor.js` PASS. Vollständiger GitHub-Branch- und Windows-Brave-Livetest stehen aus.
- Sicherheit unverändert: Token/Bearer-Authentifizierung, Backend-Claims und Auto-Send-Gate bleiben aktiv.
- Nächste Abnahme: `git pull --ff-only`, Erweiterung und Chat-Tab neu laden, neue Antwort erzeugen. Kein weiterer Countdown notwendig: beliebiger neuer Codeblock genügt. Bestehende `Letzte Antwort` wird beim Reload nicht nachträglich umgeschrieben.
