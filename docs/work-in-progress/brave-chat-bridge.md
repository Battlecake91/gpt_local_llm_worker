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

## Read-only Wiederholungsprüfung ohne erneute Generierung, 2026-11-14
- Der zuletzt gelieferte `structureTrace` zeigt erneut denselben echten Assistenten-Codeblock (`data-code-block`, zwei Unter-DIVs) und die bereits erkannte Stop-Schaltfläche (`stopEverSeen=true`). Die Daten allein enthalten **keinen Vergleich der extrahierten Nutzlast** nach dem jüngsten Parser-Fix.
- Neues Feature: Seitenpanel-Button **Vorhandene Antwort lokal prüfen**. Das Panel fragt ausschließlich beim aktiven ChatGPT-Konversationstab über `PREVIEW_CURRENT_REPLY` die aktuell vorhandene letzte Antwort ab. Es zeigt höchstens 16.000 Zeichen, tatsächliche Länge, Anzahl Zeilenumbrüche und Markdown-Fences. Kein `CAPTURE`, kein POST an den Worker, keine Eingabe in den Composer, kein Senden, keine Änderung des beobachteten Generation-Lifecycle.
- `tests/test_content.cjs`: Negativtest, dass die read-only Anfrage ohne Assistentenantwort weder Capture noch Sendung auslöst.
- Isolierter Offline-Test mit identischer Preview-Implementierung im lokalen Testverzeichnis: `node --check extension/content.js` PASS; `node --test tests/*.cjs` **32/32 PASS**. Vollständiger erneuter Windows-Brave-Test und GitHub-Checkout-Gesamttest noch offen.
- Nach `git pull --ff-only`, Extension-Reload, ChatGPT-Tab-Reload, im bestehenden Chat **Vorhandene Antwort lokal prüfen** anklicken und nur den neuen Preview-Block vergleichen. Alte `Letzte Antwort` bleibt bewusst historische Capture-Vorschau; keine Neubewertung oder Neuübertragung bereits gesendeter Captures.
- Bearer-Authentifizierung ausdrücklich beibehalten und nicht verändert.

## Erfolgreiche lokale Extraktion und Rückkanal-STAGE_ONLY (2026-11-14)
- Benutzer bestätigte im bestehenden Chat die lokale Vorschau: **1517 Zeichen, 25 Zeilenumbrüche, 1 Codeblock**. Der vollständige mehrzeilige Python-Code, Absätze und Inline-Markdown waren in der Vorschau erhalten. Keine neue Generierung nötig. Die doppelte Kopie des Textes im übermittelten Chatbeitrag beweist **keine doppelte POST-Übertragung**.
- Rückkanal vorbereitet: `extension/content.js` sucht zuerst den tatsächlich diagnostizierten modernen Composer `form[data-chatgpt-composer] [contenteditable="true"][role="textbox"]`, mit bisherigen Legacy-Fallbacks. Leere/überlange Stage-Texte werden verweigert; vorhandene Editoreingaben bleiben unangetastet; Chat-ID und laufende Generierung werden nach Einfügung nochmals geprüft. `STAGE_ONLY` klickt weiterhin **nicht** auf Senden.
- `tests/test_content.cjs`: zusätzliche Tests für modernen Composer mit mehreren Zeilen und für leeren Text.
- Gezielter lokaler Teststand: `node --check extension/content.js` PASS; `node --test tests/*.cjs` **34/34 PASS** im lokalen Testverzeichnis mit den entsprechenden Content- und Fixture-Änderungen. Vollständiger Live-Test im Brave steht noch aus.
- Mock-Fixture kann über `scripts/windows-brave-stage.ps1 -ConversationId <ID aus URL> -TabId 2006233083` in den laufenden Mock-Worker eingereiht werden; im Panel `Jetzt synchronisieren`. Erfolg: `Letzte Übertragung` ist für Capture, `Ausgehende Nachricht` meldet `STAGED`, ChatGPT-Eingabefeld enthält mehrzeiligen Testtext, ohne Sendeklick.
- Bearer-Token-Authentifizierung und nur nach Backend-Claim erlaubte Auto-Send-Ausnahme bleiben unverändert; kein tatsächliches SSH-Resultat automatisch versendet.

## Windows-Brave End-to-End-Abnahme STAGE_ONLY (2026-11-14)
- Benutzer bestätigt: Rückkanal funktioniert. `scripts/windows-brave-stage.ps1` hat authentifizierte Mock-Jobs für das konfigurierte Tab eingereiht, und das Seitenpanel hat sie nach Synchronisierung im ChatGPT-Eingabefeld bereitgestellt.
- **Beobachtetes Ergebnis:** Worker → Extension → ChatGPT-Composer erfolgreich, **ohne automatisches Absenden**. Zusätzliche `queued`-Jobs sind nicht mit einer erfolgreichen `STAGED`-Bestätigung gleichzusetzen; es wurde nur die vom Benutzer bestätigte tatsächliche Befüllung als bestandene Live-Abnahme gewertet.
- Bereits zuvor bestätigt: ChatGPT → Extension → Mock-Worker via `/captures` mit Status `accepted`; lokale Antwort-Neuextraktion behielt Python-Codeblock und Zeilenumbrüche korrekt bei.
- **Milestone:** Beide Übertragungsrichtungen in Brave grundsätzlich live bestätigt. Der Code für `AUTO_SEND_APPROVED_RESULT` verfügt über Backend-Claim-Schranken, ist jedoch **nicht** durch eine reale SSH-Freigabe oder End-to-End-Live-Sendung abgenommen.
- Bearer-Token bleibt verbindlich. Als nächste Aufgabe: Audit für `AUTO_SEND_APPROVED_RESULT` inklusive Claim-/Receipt-Abgleich, Race-Schutz, Wiederanlauf sowie Freigabe durch einen vollständigen SSH-Befehlsblock. Bis zur expliziten Freigabe keine realen SSH-Aufträge oder automatischen ChatGPT-Sendungen ausführen.

## Rückkanal-Livetest: sichtbare Befüllung, aber stage_verification_failed (2026-11-14)
- Der Benutzer bestätigt, dass die `STAGE_ONLY`-Nachricht sichtbar im ChatGPT-Eingabefeld erscheint. Dennoch meldete das Panel für `stage-b7a0c5ae00a64f868e80d0c29c84f5e7` `status:"ERROR",error:"stage_verification_failed"`. `Letzte Übertragung.status:"accepted"` für eine SHA-256-ID betraf **den separaten eingehenden Capture**, nicht das ausgehende Staging.
- Ursache derzeit **plausibel, nicht live bewiesen**: ProseMirror formatiert eingefügte Zeilen in Absatzelemente; `innerText` kann zusätzliche Leerzeilen enthalten, obwohl die Benutzeroberfläche die Textzeilen korrekt darstellt. Es gibt noch keinen direkten DOM-Nachweis für die exakten abweichenden Zeichen.
- Für `STAGE_ONLY` vergleicht die Extension zuerst exakte normalisierte Zeilenenden. Wenn das scheitert, darf sie ausschließlich Unterschiede in der Anzahl leerer Zeilen tolerieren, sofern **alle nichtleeren Textzeilen unverändert und in gleicher Reihenfolge** sind. Meldung `STAGED` mit `verification:"EXACT"` oder `verification:"VISUAL_LINES"`.
- Für `AUTO_SEND_APPROVED_RESULT` ist ausschließlich `EXACT` zulässig; bei jeder Abweichung bleibt der Sendeklick gesperrt. Bearer-Token und Backend-Claim unverändert.
- Neue Unit-Fixtures: ProseMirror-Doppelumbrüche für Stage-Only, striktes Auto-Send trotz Claim, Verifikationskennzeichen. Keine Änderung am tatsächlichen Sendeklick.
- Live-Retest: **zuerst vorhandenen Testtext aus ChatGPT-Eingabefeld löschen**, danach nur **einen** neuen Mock-Stage-Auftrag erzeugen und synchronisieren. Bereits mit `ERROR` quittierte IDs nicht erneut verwenden. Im Panel unter `Ausgehende Nachricht` `status`, `error` und `verification` prüfen.
- Neuester Branch-Code committed, **noch nicht in Windows-Brave verifiziert**. Keine unbewiesene PASS-Zahl behaupten.

## Live-Abnahme STAGE_ONLY mit ProseMirror-Verifikation (2026-11-14)
- Benutzer meldet für `stage-f5cd0af3b2eb40b6a8c846dc7dd56bba`: `{"status":"STAGED","error":null,"verification":"VISUAL_LINES"}`.
- Damit ist der vom Benutzer vorher sichtbar bestätigte Rückkanal nun auch **vom Protokoll quittiert**. Die eingebauten Abweichungstoleranzen gelten ausschließlich für `STAGE_ONLY`; der sendende Pfad bleibt mit `EXACT` abgesichert.
- `Noch nicht geprüft` (read-only preview) und `keine` (`Letzte Übertragung`) nach Extension-Neuladen sind keine Fehlerindikatoren für das separate ausgehende Staging.
- **Milestone abgeschlossen:** Beide Transportwege im Browser grundsätzlich live bestätigt, Bearer-Token unverändert. Weiterhin ausstehend: echter SSH-Autorisierungsworkflow, auto-send claim/receipt audit, strikte End-to-End-Texttreue, Restart-/Race-Tests und produktive Worker-Implementierung.

## Panel UX, persistentes Token, Replay-Schutz (2026-11-14)
- Benutzerwunsch: DOM-Diagnose standardmäßig einklappen und per Button **DOM kopieren** vollständig in die Zwischenablage schreiben. `panel.html` verwendet `details/summary` (initial geschlossen), `panel.js` kopiert den sichtbaren Diagnoseblock mit `navigator.clipboard.writeText`, meldet Erfolg/Fehler.
- Authentifizierung **bleibt Pflicht**. `SET_TOKEN` speichert nun das Bearer-Token in `chrome.storage.local.workerBearerToken`; bei MV3-Serviceworker-Neustart wird es vor dem ersten authentifizierten API-Aufruf geladen. `CLEAR_TOKEN` löscht es aus dem Speicher; Statusmeldungen zeigen nur `tokenSaved`, niemals den Klartext. Passwortfeld wird nach erfolgreichem Speichern geleert.
- Sicherheit: `chrome.storage.local.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'})` muss erfolgreich sein, bevor der Worker die gespeicherten Zugangsdaten liest. Bei Fehler fail-closed; Content Scripts erhalten keinen lokalen Storage-Zugriff. **Keine Verschlüsselung im Ruhezustand:** Auf Dateisystem-/Browserprofil-Ebene können lokale Benutzer/Prozesse mit Zugriff auf das Profil diese gespeicherten Credentials potentiell lesen. Kein externer Transport; nur localhost-Bearer-Header.
- Testfälle hinzugefügt in `tests/test_background.cjs`: Speicherung ohne Token-Ausgabe über `GET_STATUS`, Startup-Restore mit Authorization-Header, Löschen + Netzwerkzugriff blockiert, gespeichertes `ATTEMPTING`-Receipt verhindert Retry eines Auto-Sends nach MV3-Neustart, parallele Syncs erzeugen keinen doppelten Send.
- Auto-Send-Policy unverändert: Backend-Claim mit `approved_ssh_result` erforderlich; vor dem DOM-Klick ein `ATTEMPTING`-Receipt dauerhaft schreiben; bei unklarem Ausgang kein Replay. Freigabe aus echtem SSH-Job und realer Auto-Send-Livetest stehen aus.
- Die Änderungen sind committed, **vollständiger aktueller GitHub-Branch/Windows-Brave-Test noch offen**. Vor Test des Token-Restore: Erweiterung neu laden und Token einmalig speichern; nach weiteren Reloads sollte keine erneute Eingabe nötig sein. Der Benutzer kann den lokal gespeicherten Token über **Gespeichertes Token löschen** entfernen.

### Validierung dieser Iteration
- Syntaxprüfung der direkt von GitHub geladenen Fassungen mit dem JavaScript-Parser: `background.js`, `panel.js`, `content.js`, `tests/test_background.cjs` **4/4 PASS**.
- Zusätzlich wurde der aktuelle `background.js` in einer isolierten JavaScript-Simulation mit Chrome-Storage-, Tabs-, Network- und Alarm-Mocks ausgeführt: **4/4 PASS** für persistieren/kein Token im Panelstatus, löschen, Bearer-Header nach MV3-Neustart und Schutz vor wiederholtem Auto-Senden durch persistiertes `ATTEMPTING`-Receipt.
- Repository-Unit-Tests wurden um 5 Fälle erweitert; die komplette Node-Test-Suite des GitHub-Branches konnte **nicht** ausgeführt werden, da der Checkout in der Tool-Umgebung wegen fehlender GitHub-DNS-Erreichbarkeit nicht möglich ist. Diese Tests und Brave-Livetest bleiben noch offen.

## Sicherheitsphase: SSH-JSON, Approval-Store und gebundener Auto-Send (2026-11-14)

**Ziel:** Backend-Freigabe muss vollständig an Nutzerentscheidung, unveränderlichen SSH-Befehlsblock, Originalchat und exakten Ergebnistext gebunden sein. Kein Live-SSH, keine automatische Nachricht gegen eine reale Sitzung.

**Implementiert:**
- `extension/background.js`: Automatisches Absenden nur für ein `approval`-Objekt mit `job_id`, `approval_id`, `host_id`, `command_sha256`, `result_sha256`; gegen vollständig gespiegelte einmalige Claim-Antwort und Ursprung `outbound_id`, `tab_id`, `conversation_id` prüfen. SHA-256 des konkreten UTF-8-Ergebnistexts browserseitig nachrechnen. Alte `allowed/claim_id`-Claims werden verweigert. Ungültiger Payload/Claim erhält terminale lokale `BLOCKED_INVALID_PAYLOAD`/`BLOCKED_INVALID_CLAIM`-Receipts; `ATTEMPTING` wird weiterhin vor DOM-Klick dauerhaft gespeichert. `STAGE_ONLY` und Bearer-Authentifizierung bleiben kompatibel.
- `mock/backend.py`: Claim-Anfrage und Antwort an denselben Job-, Approval- und Result-Digest gebunden; im Mock durch `threading.Lock` atomar gegen gleichzeitige Claims. Der Mock erstellt **keine echten Benutzerfreigaben**.
- `worker/ssh_protocol.py`: reiner Parser für das bereits in `docs/protocol.md` definierte `kind:"ssh_batch"` mit `target`, `working_directory`, vollständigen `commands` (IDs, Kommando, Timeout) und `description`. Keine Shell-Ausführung. Allowlist, Grenzen, eindeutige JSON-Schlüssel, keine freien Textbefehle. Kanonischer Digest umfasst gesamten sichtbaren Befehlsblock samt Ziel, CWD und Timings.
- `worker/approval_state.py`: transaktionale SQLite-Ledger-Funktionen für `PROPOSED`, `APPROVED`, `REJECTED`, `RUNNING`, `UNKNOWN`; Approval-Digest und Ursprungstab/Chat unveränderlich, claim-once vor möglichem SSH-Start, `RUNNING` nach Neustart ohne automatische Wiederholung als `UNKNOWN`. SQLite-Verbindungen explizit geschlossen.
- Regressionstests und Doku in `tests/test_background.cjs`, `tests/test_mock.py`, `tests/test_ssh_protocol.py`, `tests/test_approval_state.py`, `docs/bridge-protocol.md`, `docs/protocol.md`, `docs/security.md`, `README.md`.

**Ausgeführte Tests:**
- Python: `PYTHONWARNINGS=error python -m unittest discover -s tests -p 'test_*.py' -q` in isoliertem lokalen Prüfverzeichnis: **20/20 PASS** (8 SQLite-Tests, 8 SSH-Parser-Tests, 4 FastAPI-Mock-Tests). Die vier geprüften Python-Quell-/Testdateien wurden per `git hash-object` bytegenau gegen die entsprechenden GitHub-Blob-SHAs abgeglichen, ebenso die beiden Mock-Dateien.
- JavaScript: Direkte V8-Ausführung des aus GitHub geladenen `extension/background.js` mit Chrome/FETCH/crypto-Mocks: **5/5 PASS** für gültigen gebundenen Claim, falsche Approval-ID, falschen Chat, fehlende Jobbindung und altes Claim-Format. Nach Receipt-Härtung erneut **5/5**: gültig genau einmal, falsche Freigabe/falscher Ursprung mit terminalem `BLOCKED_INVALID_CLAIM`, fehlende Bindung mit `BLOCKED_INVALID_PAYLOAD`, gespeichertes `ATTEMPTING` ohne Wiederholung. Keine echten Browserklicks.
- Erweiterte Node-Regressionstests committed, vollständige `node --test tests/*.cjs` des aktuellen GitHub-Checkouts **hier noch nicht ausgeführt**. Kein realer SSH- oder Auto-Send-End-to-End-Test.

**Offen vor einer produktiven Freigabe:**
1. Vertrauenswürdiger operatorseitiger Approval-Dialog mit vollständiger Darstellung von Hostalias, konfiguriertem SSH-Benutzer, Arbeitsverzeichnis, allen Befehlen/Timeouts und Nebenwirkungen. `authenticated_operator` in der SQLite-Klasse ist eine **Vertragsannahme**, keine Authentifizierung; kein API-Endpunkt darf ungeprüft `approve()` aufrufen.
2. SQLite-Ledger mit produktivem FastAPI-Worker und persistentem Result-/Audit-System verbinden; Allowlist, SSH-Hostkey-Pinning, Executor, Ausgabelimit und Redaction implementieren. Keine Credentials aus ChatGPT-Text.
3. Nur nach separater Testfreigabe realen Auto-Send-DOM-Pfad prüfen; in Brave hat `STAGE_ONLY` bisher nur `VISUAL_LINES` erreicht, nicht das für Auto-Send nötige `EXACT`.
4. Windows-Branch aktualisieren und `node --test tests/*.cjs` sowie `python -m unittest discover -s tests -p 'test_*.py' -v` auf dem vollständigen Checkout ausführen.

## Windows-Testbericht vom Benutzer (2026-11-14, 23:58 CET)
- `git pull --ff-only origin feature/brave-chat-bridge`: Fast-forward bis `8b39187`, erfolgreich.
- `node --test tests/*.cjs`: **53/53 PASS**, 0 Fehler, 0 übersprungen (direkter Windows-Log).
- `py -m unittest discover -s tests -p 'test_*.py' -v`: **20 reguläre Tests erfolgreich**, aber zusätzlich ein Importfehler bei `test_contracts.py`, weil es `pytest` importiert und im verwendeten Python 3.13 nicht installiert ist; Abschluss `Ran 21 tests ... FAILED (errors=1)`. Der Fehler ist eine **Testumgebungs-/Runnerkonfiguration**, kein gemeldeter Assertion-Fehler in den neuen SSH-Tests.
- `pyproject.toml` definiert ausdrücklich `[project.optional-dependencies].test = ["pytest>=8,<10"]` und `[tool.pytest.ini_options]`, während `tests/test_contracts.py` fünf pytest-Tests mit `tmp_path` enthält. Gemischte `unittest.TestCase`- und pytest-Funktionstests müssen durch `pytest` ausgeführt werden. `README.md` korrigiert.
- Windows-Nachprüfung:
  `py -m pip install -e ".[test]"`
  `node --test tests/*.cjs`
  `py -m pytest -q`
  Nur den letzten Befehl erneut ausführen genügt nach der Installation, denn die 53 JS-Tests sind bereits bestätigt.
- Vollständiger Python-pytest-Lauf unter Windows **noch offen**. Keine echten SSH-Ausführungen oder Auto-Send-Aktionen wurden durchgeführt.

## Windows-Tests vollständig grün; Mock-SSH-Freigabedialog (2026-11-14)

**Vom Benutzer übermittelte Abnahme vor dieser Iteration:** `py -m pip install -e ".[test]"` erfolgreich; `py -m pytest -q` → **25 passed, 10 subtests passed**, 0.60 s. Die zuvor gemeldeten **53/53 Node-Tests** waren bereits bestanden. Python-Importfehler durch fehlendes `pytest` beseitigt.

**Implementiert, noch ohne produktive SSH-Ausführung:**
- `worker/approval_state.py` besitzt `pending()`, liefert unveränderliche vollständige Review-Daten (Hostalias, Ursprungschat/Tab, CWD, Beschreibung, Command-ID/Text/Timeout, SHA-256) aus SQLite.
- `mock/backend.py` erkennt `kind:"ssh_batch"` bei eingehendem Capture nur bei explizit gesetzten `BRIDGE_ALLOWED_HOSTS` und `BRIDGE_APPROVAL_DB`. Unbekannte Hosts oder unstrukturierter Antworttext bleiben wirkungslos. Review-Routen `GET /api/bridge/v1/ssh/proposals` und `POST /api/bridge/v1/ssh/proposals/{request_id}/approve|reject` erfordern Bearer-Token und vergleichen Origin, Digest und Status. Ein `APPROVED_FOR_MOCK_REVIEW`-Eintrag **gibt keine SSH-Ausführung und keinen Browser-Auto-Send frei**. Speicherung vor Capture-ACK, Request-ID-Kollision → 409.
- `extension/background.js` nimmt `LIST_SSH_PROPOSALS` und `DECIDE_SSH_PROPOSAL` ausschließlich von der eigenen `panel.html`-Extension-URL an (keine `sender.tab`), prüft zusätzlich Originalchat/Tab und nutzt weiterhin den gespeicherten Bearer-Token. Webseiten-/Content-Script-Aktionen werden abgewiesen.
- `extension/panel.html`/`panel.js`: standardmäßig eingeklappter Abschnitt mit vollständigem Befehlsblock, untrusted Beschreibung, bestätigungspflichtiger Gesamtfreigabe-Checkbox und separatem Ablehnen. Inhalte werden ausschließlich über `textContent` eingefügt, nicht als HTML. Nicht konfigurierte reale SSH-Benutzer/Hostkeys werden ausdrücklich als fehlend angezeigt.
- `scripts/windows-brave-mock.ps1 -ReviewHosts @('lab-nas')` aktiviert Review-Modus und legt lokale Mock-DB unter `%LOCALAPPDATA%\gpt-local-llm-worker\mock-review.sqlite3` ab. `scripts/windows-brave-review.ps1` erzeugt nur den synthetischen Vorschlag (uname -a, id), ohne SSH-Verbindung. PowerShell 5.1 unterstützt.
- Neue Tests: `tests/test_review_api.py` (6 API-/Sicherheitsfälle), `tests/test_approval_state.py` (vollständige Pending-Daten), `tests/test_background.cjs` (4 negative/positive Panel-Origin-Fälle). `INSTALL.md` aktualisiert.

**Ausgeführte gezielte Prüfungen:** V8-JavaScript-Parser `panel.js`, `background.js`, `test_background.cjs`: **3/3 PASS**. Direkte isolierte Hintergrunddienst-Simulation: vertrauenswürdiges Panel darf Mock-Entscheidung abschicken, nicht vertrauenswürdiger ChatGPT-Tab wird abgewiesen: **2/2 PASS**. Die vollständige Node-/pytest-Testsuite **nach diesen neuen Änderungen** und der neue Brave-Dialog müssen unter Windows noch abgenommen werden.

**Wichtige Grenze:** Der Mock prüft nur, ob eine Aktion vom authentifizierten lokalen Extension-Transport stammt. Ein echter produktiver Operator-Login, eigener Freigabekanal, konfigurierter SSH-Benutzer, Hostkey-Pinning, Executor, Redaction und Auto-Send-Zustellkontrolle bleiben offen. Produktives Ausführen wird durch diesen Dialog nicht aktiviert.

## Windows-Mock-Launcher Syntaxregression (2026-11-15)
- Benutzer meldete PowerShell `MissingEndParenthesisInExpression` und nicht abgeschlossene String-Literale in `scripts/windows-brave-mock.ps1` Zeile 9/56. GitHub-Datei bestätigte abgeschnittenes `[ValidatePattern(...` und doppelt angehängten Skriptteil (59 Zeilen).
- Vollständiger Ersatz des PowerShell-Launchers durch 44 gültig strukturierte Zeilen; `ExtensionId`, `Token`, `ReviewHosts` sauber im `param(...)`-Block. Unveränderte Loopback-, Mock- und Host-Allowlist-Gates, keine SSH-Ausführung.
- Nach GitHub-Update neu geladen: strukturelle Kontrollen für vollständigen Parameterblock/Host-Pattern und genau eine `param`, `ErrorActionPreference`, `uvicorn`-Startstelle **5/5 PASS**. Ein echter PowerShell-AST-Parse auf Windows ist noch ausstehend (in der Tool-Umgebung kein `pwsh`). Benutzer erhält einen direkt ausführbaren `[System.Management.Automation.Language.Parser]::ParseFile(...)`-Check vor dem Start.

## Brave-Mock-Review: Benutzer-Rückmeldung (2026-11-15)
- Windows-Fixture `windows-brave-review.ps1` meldete `Mock SSH proposal submitted: review-498c904027c04f54beecb5c87cb7b9f3`. Benutzer meldete anschließend zur Brave-Freigabeoberfläche: **„Scheint zu funktionieren“**.
- Damit ist die grundlegende Anzeige/Bedienbarkeit des Mock-Review-Pfads **vorläufig durch den Benutzer bestätigt**. Die genaue Backend-Antwort `APPROVED_FOR_MOCK_REVIEW`, vollständige Ablehnungs-/Manipulationsfälle und Neustart des UI wurden vom Benutzer nicht gesondert protokolliert; daher keine vollständige E2E-Sicherheitsfreigabe behaupten.
- Nächster Arbeitsblock: separater simuliert ausführender SSH-Executor mit konfiguriertem Host-/Benutzer-/Hostkey-Vertrag, Timeouts und Ausgabelimits; zunächst keine echten SSH-Verbindungen oder automatischen ChatGPT-Sendungen.

## Simulierter SSH-Executor ohne Netzwerk (2026-11-15)

**Branch:** `feature/brave-chat-bridge`. Keine produktive SSH-Verbindung, kein automatisches ChatGPT-Senden.

**Implementierung:**
- `worker/mock_executor.py`: ausdrücklicher `MockSSHExecutor` ohne SSH-, Socket- oder Subprocess-Import. Hostalias, Mock-Benutzer und syntaktischer Hostkey-Platzhalter sind konfiguriert, aber **keine realen SSH-Credentials oder kryptografische Hostkey-Prüfung**. Frisch berechneter Digest prüft die komplette persistierte Proposal-Payload unmittelbar vor dem Claim. Eine pro Kommando-ID fest vorgegebene `FixtureReply` enthält stdout, stderr, Exitcode und simuliertes Timeoutflag. Bei Nichtnull-Exit, Timeout oder Output-Trunkierung werden weitere Befehle nicht simuliert. UTF-8-sicheres Ausgabelimit 16 KiB je Batch.
- `worker/approval_state.py`: Tabelle `mock_execution_results`; `finish_mock_execution` speichert terminalen Zustand und Ergebnis in **einer SQLite-Transaktion** und verweigert erneute Ergebnisse. `recover_unknown`/einmaliges `APPROVED → RUNNING` bleiben bestehen.
- `worker/mock_cli.py`: **ausschließlich** bewusst gestartete Mock-Simulation eines bereits freigegebenen Batches. Ergebnistext jedes Kommandos ausdrücklich `MOCK ONLY`, keine Ausführung des Befehlstexts. Kein API-Endpoint startet diesen Simulator autonom.
- `scripts/windows-brave-simulate.ps1`: Windows-Wrapper für die lokale SQLite-Mock-Datenbank unter `%LOCALAPPDATA%\gpt-local-llm-worker\mock-review.sqlite3`; verlangt vorhandene virtuelle Python-Umgebung und Auftrags-ID.
- `tests/test_mock_executor.py`: Tests für Erfolg, terminalen Status, Blockabbruch bei Exitfehler/Timeout/Trunkierung, UTF-8-Grenze, fehlende und falsche Approval-/Host-Bindung, Datenbank-Manipulation, Crash/UNKNOWN, Replay-Sperre, explizite CLI-Nutzung und Hostkonfiguration.
- `INSTALL.md`, `README.md`, `docs/security.md`, `docs/architecture.md` angepasst.

**Wichtige Grenzen:** Das Timeout ist **ein Fixture-Flag**, keine wirkliche Zeitüberwachung; der Mock-Hostkey ist **kein** verifizierter SSH-Fingerabdruck; kein Kommando wird ausgeführt, kein SSH-Transport importiert und kein ChatGPT-Auto-Send angestoßen. Für Produktion fehlen tatsächliche Authentifizierung/SSH-Pinning/Real-Timeouts/Redaction/Result-Routing.

**Tests:** Windows-Nachprüfung für die neu hinzugefügten Python-Module ist noch offen. Der vorherige Benutzerstand `25 passed, 10 subtests passed` stammt **vor** dieser Änderung. Nach Pull `py -m pytest -q tests/test_mock_executor.py tests/test_approval_state.py`, danach optional vollständige `py -m pytest -q`. Keine Zahl für neue Tests behaupten, bevor sie ausgeführt wurden.

## Brave read-only Mock-Resultate (2026-11-15)

- **Windows-Live-Beleg:** Der Benutzer meldete den einmaligen Offline-Aufruf von `windows-brave-simulate.ps1` für `review-498c904027c04f54beecb5c87cb7b9f3`: `mode=MOCK_ONLY`, `status=SUCCEEDED`, Kommando-IDs `host` und `user`, je Exitcode 0, `timed_out=false`, `truncated=false`, nur gekennzeichnete synthetische stdout-Ausgaben. Kein echtes SSH, kein ChatGPT-Versand. Eine zweite Simulation und der vollständige neue Python-Testlauf wurden vom Benutzer noch nicht nachgewiesen.
- **Neu:** `ApprovalStore.recent_mock_results()` liest begrenzte, dauerhaft gespeicherte Resultate mit Ursprungschat/-tab. Der Mock-Backend-Endpunkt `GET /ssh/mock-results` unter `/api/bridge/v1` ist Bearer-authentifiziert und nur lesend. Die Background-Nachricht `LIST_MOCK_RESULTS` ist für das vertrauenswürdige Extension-Panel reserviert. `panel.html`/`panel.js` zeigen Resultate eingeklappt mit Exitcodes und stdout/stderr via `textContent`; kein Auto-Send.
- Tests ergänzt: `tests/test_approval_state.py` (SQLite-Historie nach Neustart), `tests/test_review_api.py` (401 ohne Token, read-only GET mit Originalbindung), `tests/test_background.cjs` (Content-Script verweigert; Panel erlaubt Abfrage).
- Gezielt ausgeführt: V8-JS-Syntaxcheck der GitHub-Fassungen von `background.js`, `panel.js`, `test_background.cjs` **3/3 PASS**. Vollständige `node --test tests/*.cjs`-/`py -m pytest -q`-Läufe der **neuen Änderungen** sowie Live-Prüfung des Panels noch offen. Container kann GitHub wegen DNS-Ausfall nicht klonen.
- Bedienung: Repo aktualisieren, Mock-Server und Brave-Erweiterung neu laden, im Panel **Simulierte SSH-Ergebnisse → Gespeicherte Ergebnisse anzeigen → Ergebnisse aktualisieren**; alten Erfolg `review-498c...` suchen.

## Windows-Abnahme Mock-Resultate und gezielter Testfix (2026-11-15)

- Benutzer `git pull` bis `ae87fcd` erfolgreich.
- `node --test tests/*.cjs`: **57/58 PASS**, einzig `mock history retrieval is restricted to the extension sidepanel` scheiterte bei `tests/test_background.cjs:155` mit `1 !== 0` beim Vergleich von `h.calls.length` vor/nach einer untrusted Anfrage.
- Ursache: Der MV3-Harness führt beim Start selbst einen asynchronen `/outbound`-Synchronisierungslauf aus. Der Test setzte seine Baseline unmittelbar nach `harness()` auf `0` und zählte den späteren, **unabhängigen** Startup-HTTP-Call fälschlich als Zugriff des ChatGPT-Content-Scripts. Die eigentliche Berechtigungsprüfung im Background war erfolgreich (`untrusted_review_sender`).
- Fix: Baseline und Nachprüfung zählen nur `/ssh/mock-results`-Requests, damit keine fremden Startup-/Capture-Calls das Ergebnis beeinflussen. Produktiver Background-Code unverändert; nur `tests/test_background.cjs` angepasst.
- `py -m pytest -q`: **48 passed, 10 subtests passed**, 1.23 s. Keine Python-Korrektur erforderlich.
- Nach Fix kompletter Node-Testlauf auf Windows **noch offen**; keine Behauptung über 58/58 ohne erneuten Lauf.

## Windows-Abnahme nach Testfix (2026-11-15)
- Benutzer führte `node --test tests/*.cjs` nach `520f8ef` erfolgreich aus: **58 Tests, 58 PASS, 0 FAIL, 0 SKIP**, 686.6183 ms. Auch `mock history retrieval is restricted to the extension sidepanel` ist PASS.
- Letzter übermittelter vollständiger Python-Lauf: `py -m pytest -q` → **48 passed, 10 subtests passed**, 1.23 s.
- Damit sind die automatisierten JS-/Python-Suites im Windows-Checkout grün. Noch offen bleibt **Live-UI-Abnahme** für den neuen eingeklappten Abschnitt `Simulierte SSH-Ergebnisse` mit dem bereits persistierten erfolgreichen Mock-Auftrag `review-498c904027c04f54beecb5c87cb7b9f3` nach Neustart des Mock-Servers und Reload der Erweiterung. Keine echte SSH-Verbindung oder Auto-Send-Freigabe daraus ableiten.

## Brave zeigt 0 Mock-Resultate trotz erfolgreicher Offline-Simulation (2026-11-15)

- Benutzer zeigt im Seitenpanel **0 gespeicherte Mock-Ergebnisse**, Backend-Konnektivität und Capture-ACK `accepted` vorhanden. Die vorherige lokale Offline-Simulation derselben festen Request-ID hatte `SUCCEEDED` geliefert; sie persistiert in `%LOCALAPPDATA%\\gpt-local-llm-worker\\mock-review.sqlite3`.
- Bei Inspektion zeigte sich: `GET /ssh/mock-results` gab bei fehlendem `BRIDGE_APPROVAL_DB` einfach `{"items":[]}` zurück und täuschte eine leere Historie vor. Korrigiert auf HTTP 503 mit expliziter Meldung `Mock approval database is not configured; restart with -ReviewHosts`. Passender Regressionstest in `tests/test_review_api.py` ergänzt.
- Die tatsächliche Ursache auf dem Windows-Rechner ist noch **nicht verifiziert**. Nächste Diagnose: dieselbe lokale SQLite-Datei mit `sqlite3` auslesen, `GET /api/bridge/v1/ssh/mock-results` direkt per PowerShell abfragen; Mock-Prozess gegebenenfalls mit `-ReviewHosts @('lab-nas')` neu starten. Wenn die direkte API Daten liefert, aber das Panel nicht, ist es ein Anzeigeproblem. Wenn die API leer liefert und die Datei Einträge enthält, stimmt die DB-Verbindung oder der Prozess nicht.
- Kein automatischer ChatGPT-Versand und keine echten SSH-Befehle freigegeben.

## Brave-Mock-Resultat-End-to-End abgenommen (2026-11-15)

- Nach gezieltem Neustart des Mock-Uvicorn-Servers mit `-ReviewHosts @('lab-nas')` lieferte die lokale API `GET /api/bridge/v1/ssh/mock-results` den persistierten Datensatz `review-498c904027c04f54beecb5c87cb7b9f3`, `SUCCEEDED`, `lab-nas`.
- Der Benutzer bestätigte denselben Datensatz **sichtbar im Brave-Seitenpanel**: Originalchat `6af8aaad-be34-83eb-89bb-ccc8b58ac1f3`, Tab `2006233083`, `Mock-Benutzer mockuser`, `SUCCEEDED`, Befehle `host` und `user`, jeweils Exitcode 0, `Timeout: false`, `Ausgabe gekürzt: false`; stdout ausschließlich `MOCK ONLY`-Fixtures.
- Ursache des anfänglichen Leerstands war offenbar die fehlende/falsche DB-Konfiguration des zuvor laufenden Servers: lokale SQLite enthielt den abgeschlossenen Datensatz, API vor Neustart lieferte `items: []`; nach Neustart beide korrekt. Nicht separat bestätigt, mit welchen Umgebungsvariablen die alte PID genau gestartet wurde.
- **Abnahmestand:** Mock-Persistenz → authentifizierter API-Read → Brave-Panel-Liveanzeige funktioniert. Keine Live-SSH-Verbindung, kein tatsächlicher Command-Run, kein Auto-Send. Die beiden weiteren Mock-Vorschläge `review-a35ca9e7cd04444a85e36a880443a0e0` und `review-08aa48e9365f47ed9685401cfc6fb9b5` bleiben `APPROVED` ohne Ausführung.
- Nächste Phase: realen SSH-Transport nur auf isoliertem Testziel mit fest konfigurierter User-/Hostkey-Pin-Liste und ohne automatisches Aktivieren oder produktives NAS-Ziel entwickeln; vor Live-Test separate Betreiberfreigabe einholen.

## Sicherheitsphase: isolierter echter SSH-Transport, noch ohne Live-Verbindung (2026-11-15)

- **Ziel:** OpenSSH-Befehlstransport als unabhängigen, bislang nicht benutzten Baustein vorbereiten. Keine produktiven Hosts oder echte Netzwerkverbindung im aktuellen Test.
- **Neu:** `worker/ssh_transport.py` mit `SSHHostConfig` (Alias, Hostname, Benutzer, Port, absoluter Identitätsdateipfad, vollständiger öffentlicher Hostkey). Ein Fake-Runner prüft aus der Host-Allowlist erzeugtes `ssh -F none -T ...` argv, `BatchMode=yes`, `StrictHostKeyChecking=yes`, isolierte temporäre `known_hosts`-Datei, Passwort-/Agent-/Forwarding-Sperren. Der eigentliche Runner startet nur bei einem **expliziten direkten Bibliotheksaufruf**, nicht durch Panel/Mock/API. Timeout wird mit `Popen.wait` behandelt; stdout/stderr teilen sich einen synchronisierten 16-KiB-Puffer, Overlimit beendet den SSH-Prozess. Ordnerpfad wird remote zitiert, volle Befehle bleiben exakt wie genehmigt. Keine Remote-Sandbox.
- **Neue Tests:** `tests/test_ssh_transport.py`, mit absichtlich nicht auflösbarem `test.example.invalid`, Fake-Identity- und Fake-Public-Key-Dateien. Host/Port/Username/Pin/Path-Validierung, argv-Flags, temporäre Dateireinigung, Directory-Quoting, unbekanntes Ziel, Timeout-/Output-Fail-Closed. Für Process-Reader/-Wait sind ausschließlich mit `unittest.mock.patch` simulierte `Popen`-Objekte vorgesehen, **niemals echte SSH-Verbindungen**.
- **Noch ausstehend:** Aktueller vollständiger Python-Testlauf nach diesen Änderungen auf Windows. Auch echte Hostkey-/SSH-Binary-Kompatibilität nicht getestet. Keine bestehende Mock-Freigabe wird als produktive Ausführungsberechtigung wiederverwendet. Noch keine Integration in Audit, SQLite-RUNNING/UNKNOWN, Redaction oder Result-Auto-Send.
- **Sicherheitshinweis:** `ssh`-Prozess-Kill ist keine Garantie für das Ende des Remote-Kommandos. Für den späteren echten Executor ist Crash/Wiederanlauf **UNKNOWN**, keine automatische Wiederholung.

### Stand nach letzter Prüfung
- Zusätzliche Korrektur: parallele stdout/stderr-Reader synchronisieren ihr gemeinsames Bytebudget; unvollständige Reader werden nicht als Erfolg zurückgemeldet. UTF-8-Decoder verwirft abgeschnittene/ungültige Bytefolgen, sodass `errors="replace"` das Bytelimit nicht überschreiten kann. Passender Test ergänzt.
- Source-Review der zuletzt vom Repository neu geladenen `worker/ssh_transport.py` und `tests/test_ssh_transport.py` erfolgte; **Python-Ausführung nach diesen Commits noch nicht durchgeführt**, insbesondere kein Windows-Test und keine echte Hostkey-Prüfung am Ziel. Erwarteter Windows-Aufruf: `py -m pytest -q tests/test_ssh_transport.py`, danach `py -m pytest -q`.
- Live-Test weiterhin gesperrt. Der Transport ist keinem Mock- oder Browser-Handler zugeordnet; keine Hostidentitäten, privaten Schlüssel, Credentials oder IP-Adressen des produktiven NAS wurden konfiguriert oder kontaktiert.

## Windows-Test: UTF-8-Fixture-Literal korrigiert (2026-11-15)
- Windows-Checkout nach Pull bis `ebe9faa`: `py -m pytest -q tests/test_ssh_transport.py` **9 passed, 12 subtests passed, 1 failed**; vollständiger `py -m pytest -q` **57 passed, 22 subtests passed, 1 failed**.
- Fehler in `tests/test_ssh_transport.py::test_utf8_boundary_never_expands_bounded_output`: Test übergab `b"\\\\xff" * 100` (vier ASCII-Zeichen pro Element, 400 Bytes), statt 100 ungültigen UTF-8-Bytes. `_decode` verhielt sich korrekt, die Längenannahme im Test war falsch.
- Fix: Fixture auf `bytes([0xff]) * 100` umgestellt. Isolierte direkte Python-Checks der beiden UTF-8-Assertions: **2/2 PASS**. Volle Windows-Regression nach Fix noch offen; keine Produktivcodeänderung, keine SSH-Verbindung.

## Offline-Koordinator ApprovalStore → Fake-Transport (2026-11-15)
- **Windows-Baseline vom Benutzer:** Nach Pull bis `7955882` `py -m pytest -q` → **58 passed, 22 subtests passed**, 0.95 s. Damit ist die bisherige Python-Regression vollständig grün.
- **Neu:** `worker/execution_coordinator.py` mit `OfflineExecutionCoordinator`, `FixtureOnlyPermit` und einem nur für Tests injizierbaren Fake-`run_command`-Transport. Die bestehenden SQLite-Approval-IDs und der frisch validierte vollständige SHA-256 werden vor dem einmaligen Claim geprüft. Danach ausschließlich geordnete Fixture-Antworten; Nichtnull-Exit, Timeout oder `truncated` beendet den Block. Erfolgs-/Fehler-Resultate werden atomar in die bestehende Mock-Resultat-Tabelle geschrieben. Unklare Transport-Ausnahme lässt `RUNNING` bestehen, spätere `recover_unknown()` markiert `UNKNOWN` und verhindert erneute Durchführung.
- `tests/test_execution_coordinator.py`: 8 Offline-Sicherheitsfälle (Erfolg, Reihenfolge, Wiederholungssperre, Fehlerrückgabe, fehlende/falsche zweite Fixture-Berechtigung, Persistenz-Manipulation, Absturz-Unbekanntstatus, Fake-Transport-Pflicht und Resultatgrößenlimit). Testcode verwendet kein Netzwerk und keinen OpenSSH-Prozess.
- **Bewusste Sperre:** `FixtureOnlyPermit` und Fake-Transport-Marker sind **nur Testkontrakte**, keine echte Betreiber-Authentifizierung. Kein Browser- oder FastAPI-Endpunkt und kein CLI importiert oder startet diesen Koordinator. Vor allem dürfen die existierenden `mock-sidepanel-confirmation`-Freigaben nicht für echte SSH-Aufträge wiederverwendet werden. Der reale `SSHTransport` wird ausdrücklich verweigert.
- **Teststatus:** Neue Python-Tests auf Windows noch nicht ausgeführt; `py -m pytest -q tests/test_execution_coordinator.py`, danach kompletter `py -m pytest -q`. Kein echter SSH-Zugriff und kein Auto-Send.

## SQLite-Freigabedomänen gegen Mock→Live-Eskalation (2026-11-15)
- **User-Testbasis:** Nach `git pull` bis `e981a93` meldete der Nutzer für den neuen Offline-Koordinator `py -m pytest -q tests/test_execution_coordinator.py` → **8 passed, 0.14 s** und vollständige `py -m pytest -q` → **66 passed, 22 subtests passed, 1.13 s**.
- **Implementiert:** `worker/approval_state.py` führt `approval_scope` mit Default `MOCK`, CHECK(`MOCK`/`LIVE`) und Upgrade alter 11-Spalten-Datenbanken auf `MOCK` ein. SQLite-Trigger untersagt Scope-Änderungen. Die existierende SQLite-Mock-API und der Offline-Koordinator nutzen weiterhin nur diese Mock-Zeilen; Listing, Approve, Reject, Claim, Recovery, Finish und Mock-Historie sind auf `MOCK` beschränkt. Bestehende `APPROVED`-Datensätze bleiben `MOCK` und sind für echte SSH-Ausführung unbrauchbar.
- **Tests ergänzt:** `tests/test_approval_state.py` prüft Neuanlage, immutable Scope, Live-scope-Ausblendung, Ablehnung aller Mock-Methoden auf LIVE-Datensätzen, alte SQLite-Schema-Migration bei bereits bestätigten Aufträgen und erhaltene Idempotenz.
- **Offen:** neue fokussierte und vollständige Windows-Python-Tests nach Scope-Migration; noch kein `LIVE`-Approval, echte Betreiber-Identitätsprüfung, API-Route, produktiver SSH-Executor oder Auto-Send. Keine produktiven NAS-Verbindungen.

## Windows-Dateihandle bei SQLite-Migrationstest (2026-11-15)
- Nach Pull bis `05e9f39`: `py -m pytest -q tests/test_approval_state.py` → **12 passed, 1 failed**; vollständig `py -m pytest -q` → **68 passed, 22 subtests passed, 1 failed**.
- Ausschließlich `ApprovalStateTests.test_old_database_migrates_existing_rows_to_mock_scope` scheiterte in `TemporaryDirectory.cleanup()` mit Windows `PermissionError [WinError 32]` für `old.sqlite`. Die Test-Fixture erzeugte die SQLite-Verbindung über `with sqlite3.connect(legacy)`, was den Commit ausführt, **aber keine explizite Schließung**.
- Fix in `tests/test_approval_state.py`: `from contextlib import closing` und `with closing(sqlite3.connect(legacy)) as connection, connection:`. Verbindung wird vor dem Tempdir-Cleanup deterministisch geschlossen. Keine Änderungen an produktiven SQL-/SSH-Funktionen.
- Nach Fix noch zu verifizieren: `py -m pytest -q tests/test_approval_state.py`, anschließend `py -m pytest -q`. Keine Live-SSH-/Browser-Aktion.

## LIVE-Vorschlagsjournal ohne Autorisierung und Ausführung (2026-11-15)
- **Bestätigte Windows-Baseline:** `py -m pytest -q tests/test_approval_state.py` **13 passed, 0.20 s**, vollständiges `py -m pytest -q` **69 passed, 22 subtests passed, 1.15 s**. Damit war die vorherige Mock-/SQLite-Migration vollständig grün.
- **Neu:** `worker/live_approval.py` als eigenständiger `LiveApprovalLedger` mit Tabelle `live_proposals`, die nicht vom Mock-Backend, Brave oder CLI verwendet wird. Immutable Felder: Request-ID, kompletter Befehlsblock mit SHA-256, Ursprungschat, Tab, Hostalias und SHA-256 der fest konfigurierten Zielidentität (Hostname, Port, Benutzer, öffentlicher Hostkey). SQLite-Trigger verhindert Änderungen des LIVE-Vorschlags nach Anlage. Idempotente Wiederholung nur für **exakt identische** Vorschläge.
- Das LIVE-Journal implementiert **keinerlei** Approval-/Ausführungsfreigabe. `approve` wirft `live_authenticator_not_integrated`, `claim_execution` wirft `live_executor_not_enabled`. Ein echtes Betreiberauthentifizierungsverfahren, echter Hostkey-Vertrauensanker, Audit und separater Live-Executor müssen vor jedem Lauf zusätzlich folgen. Die Persistenz einer vom Caller gelieferten Hostkey-Zeichenfolge beweist deren Echtheit nicht.
- `tests/test_live_approval.py`: 7 neue Offline-Fälle, u. a. Mock-vs-LIVE-Datentrennung, vorhandene MOCK-Freigabe bei gleicher Request-ID ohne Übergang, fehlende Freigabe, immutables Ziel, Idempotenz und UNKNOWN-Recovery. Kein SSH- oder Netzwerk-Test, keine Browseraktion.
- **Noch offen:** Windows-Test `py -m pytest -q tests/test_live_approval.py`, danach `py -m pytest -q`. Vorheriger grün bestätigter Stand 69 Python-Tests + 22 Subtests. Echte SSH-Ausführung und ChatGPT-Auto-Send bleiben deaktiviert.

## Betreiber-Authentifizierung als Offline-Vertrag (2026-11-15)
- **Windows-Tests vom Benutzer:** `py -m pytest -q tests/test_live_approval.py` **7 passed, 0.14 s**, vollständige Suite `py -m pytest -q` **76 passed, 22 subtests passed, 1.23 s**. Bisheriges LIVE-Journal bestätigt.
- **Neu:** `worker/operator_auth.py` mit gesalzenem scrypt-Passwortverifikator, zufälligen und kurzlebigen Einmal-Tickets, präziser Bindung an Request-ID, Befehlsdigest, Ziel-Digest, Ursprungschat und Tab, Prozess-Sperre nach fünf Fehlversuchen. Kein Import in `worker/live_approval.py`, keine produktive Verknüpfung, kein HTTP-/CLI-/Browser-Einstieg, keine SSH-Ausführung und kein ChatGPT-Auto-Send.
- `tests/test_operator_auth.py` enthält acht Offline-Vertragstests (Erfolg, falsches Passwort, jede Bindungsdimension, Ablauf/Neustart, Sperre, fehlerhafte Metadaten, Fehlversuch verbraucht Ticket). **Neue Tests noch nicht auf Windows ausgeführt**. Erwarteter Gesamttest nach erfolgreicher Ausführung: 84 Python-Tests und 22 Subtests.
- Noch offen: Nachweis der Windows-Python-Regression, persistente Betreiber-Konfiguration außerhalb des Browsers, Rate-Limiting über Neustarts, definierte Fehler-/Audit-Provenienz und sichere Kopplung von Einmal-Ticket-Verbrauch und LIVE-SQLite-Freigabe. `LiveApprovalLedger.approve` und `claim_execution` bleiben ausdrücklich deaktiviert.

- Nachträgliche Typ-Härtung: `OperatorPasswordRecord` akzeptiert für Salt und Hash ausschließlich `bytes`, nicht ähnlich lange Zeichenketten. Acht Tests einschließlich ungültiger Credential-Record-Typen. **Noch kein Windows-Testlauf dieser neuen Fassung.**

## Offline LIVE-Operator-Ticket → Freigabe + SQLite-Audit (2026-11-15)
- **Windows-Baseline:** Der Benutzer meldete `py -m pytest -q tests/test_operator_auth.py` → **8 passed, 5 subtests passed**, und den kompletten `py -m pytest -q`-Lauf → **84 passed, 27 subtests passed, 2.18 s**.
- **Neuer Code:** `worker/offline_live_gate.py` mit `OfflineLiveApprovalGate`. Liest ausschließlich `live_proposals`, revalidiert den kanonischen Befehlsdigest, verbraucht ein kurzlebiges exakt gebundenes Ticket aus `OperatorAuthenticator` und aktualisiert `PROPOSED → APPROVED` zusammen mit einer Audit-Zeile in einer SQLite-Transaktion. Audit-Zeilen besitzen Trigger gegen UPDATE/DELETE. Bei DB-Fehler rollt Approval zurück, Ticket bleibt unverwendbar.
- **Tests:** `tests/test_offline_live_gate.py` ergänzt 9 reine Offline-Fixture-Tests: Erfolg mit unveränderter MOCK-Trennung, fehlendes Ticket, Replay, falscher Ursprung, vorhandene Mock-Freigabe, Audit-Fehler/Rollback, Audit-Änderungssperre, Manipulation des Befehlsdigest und Fortbestehen der direkten LIVE-Approve-/Claim-Sperre.
- **Sicherheitsgrenze:** Der Gate wird **nirgendwo automatisch aufgerufen** und hat keinen HTTP-/Brave-/SSH-Einstieg. `LiveApprovalLedger.claim_execution` bleibt gesperrt, auch wenn LIVE offline im Test zu `APPROVED` wechselt. SQLite-Trigger allein sind kein manipulationssicheres Audit gegenüber einem privilegierten Datenbankbesitzer. Eigene Betreiber-Konfiguration, echtes Enrollment/OS-Bindung, Audit außerhalb des schreibbaren SQLite-Files, LIVE-Runner und Live-Testfreigabe bleiben offen.
- **Windows-Regressionsprüfung nach Änderungen ausstehend:** `py -m pytest -q tests/test_offline_live_gate.py`, danach `py -m pytest -q`. Erwartet bei vollständigem Erfolg: 93 Python-Tests, 27 Subtests. Kein SSH oder ChatGPT-Auto-Send.

- **Race-Härtung:** `OfflineLiveApprovalGate` startet jetzt `BEGIN IMMEDIATE` **vor** dem ersten SELECT und dem Ticketverbrauch. Ein lediglich auf `isolation_level='IMMEDIATE'` konfigurierter SQLite-Connect hatte vor dem ersten DML noch keinen Writer-Lock, daher konnte zwischen Status-Read und Update eine Parallelität entstehen. Der neue 9. Test startet zwei Operator-Tickets konkurrierend und verlangt exakt eine erfolgreiche Freigabe mit einer Audit-Zeile. Vollständiger Python-Testlauf auf Windows weiterhin ausstehend; keine echte SSH-Verbindung.

## Dauerhafte Betreiber-Credential-Ablage (2026-11-15)
- **Verifizierte Windows-Baseline:** Der Benutzer meldete `py -m pytest -q tests/test_offline_live_gate.py` → **9 passed, 2 subtests passed, 0.93 s**, vollständige Suite `py -m pytest -q` → **93 passed, 29 subtests passed, 3.07 s**. Vorangehender LIVE-Freigabe-/Audit-Vertrag grün.
- **Neu:** `worker/operator_credentials.py` mit `OperatorCredentialFile`, binärem `OperatorPasswordRecord`-JSON, strenger Typ-/Versions-/Größenvalidierung, Dateierzeugung `O_CREAT|O_EXCL` mit fsync, Symlink-Sperren, keiner automatischen Überschreibung. Windows nutzt DPAPI `CryptProtectData`/`CryptUnprotectData` im Kontext des lokalen Benutzers; POSIX verlangt privaten `0600`-Modus, eigenen Datei-/Verzeichnisbesitzer und kein fremdes Verzeichnis-Schreibrecht. Keine Verbindung zu Brave/API/CLI oder SSH.
- **Neue Offline-Tests:** `tests/test_operator_credentials.py` mit 8 Testfällen für Schreibschutz, Neustart-Laden, Geheimnisfreiheit im gespeicherten Record, ungültige Dateien, Pfadvalidierung, POSIX-Rechte, Symlink-Sperre, Authentifizierung aus erneut geladenem Record und echten DPAPI-Rundlauf **nur auf Windows**. Testprotokolle enthalten kein Betreiberpasswort aus der Produktivumgebung, sondern ausschließlich synthetische Fixtures.
- **Noch offen:** Windows-Testlauf `py -m pytest -q tests/test_operator_credentials.py`, danach gesamte `py -m pytest -q`; erwarteter grüner Stand **101 Python-Tests, 29 Subtests** (plattformabhängige Skips möglich). Weiterhin kein Passwort-Enrollment, kein persistentes Rate-Limit über Neustarts und kein LIVE-SSH-/Auto-Send-Pfad. Insbesondere verschafft DPAPI **keinen Schutz gegen einen Angreifer im selben Windows-Benutzerkontext**.

## Persistente Operator-Fehlversuchssperre (2026-11-15)
- **Verifizierte Windows-Baseline vom Benutzer:** Credential-Dateitests `7 passed, 1 skipped, 5 subtests passed, 0.50s`; vollständiges `py -m pytest -q` → **100 passed, 1 skipped, 34 subtests passed, 3.56s**. Der übersprungene Test prüft POSIX-Dateimodi; die native Windows-DPAPI-Runde wurde durchgeführt.
- **Neu:** `worker/operator_rate_limit.py` mit `PersistentOperatorVerifier`. Jeder Passwortversuch läuft unter `BEGIN IMMEDIATE` auf einer separaten SQLite-Rate-Limit-Tabelle, pro Betreiberkennung und mit 5-Versuche-/60-Sekunden-Sperre. Die Sperre wird nach Neustart und über parallel gestartete Instanzen wiedergefunden; rückwärts laufende Uhrzeit wird blockiert. Fehlende/beschädigte DB verweigert, statt ein gültiges Ticket zurückzugeben. Keine Persistenz von Passwörtern oder Ticket-Tokens.
- **8 neue Offline-Tests:** `tests/test_operator_rate_limit.py` für Neustart, erfolgreichen Reset, parallele Instanzen, Uhrzeit-Rücksprung, ungültige Bindungen, Datenbankfehler, relative Pfade und Passwort-/Token-Geheimnisfreiheit im DB-File.
- **Noch offen:** Windows-Lauf `py -m pytest -q tests/test_operator_rate_limit.py` und danach `py -m pytest -q`. Erwarteter Stand bei erfolgreichem Lauf: **108 passed, 1 skipped, 34 subtests passed**. Kein neuer Login-Endpunkt und keine SSH-Verbindung. Die Verifikations-Wrapper-Instanz ist nicht automatisch in den bisherigen `OfflineLiveApprovalGate` integriert; das muss ein künftiger vertrauenswürdiger Betreiber-Einstieg erzwingen.

## Windows-pytest-Abschlussfehler im Temp-Verzeichnis (2026-11-15)

- Nutzer meldete beim vollständigen Python-Lauf nach dem neuen Rate-Limit-Block: Testfortschritt **100 % ohne sichtbare einzelne Test-Failures**, aber `pytest_sessionfinish` bricht beim Aufräumen von `C:\\Users\\steve\\AppData\\Local\\Temp\\pytest-of-Steven\\pytest-current` mit `PermissionError [WinError 5]` ab. Wegen des Abbruchs **kein erfolgreiches abschließendes Testresultat** für diesen Lauf behaupten; PowerShell `$LASTEXITCODE` war ungleich 0.
- Traceback stammt aus `_pytest/pathlib.py:cleanup_dead_symlinks` → `Path.resolve().exists()` → Windows `os.stat()`; kein unmittelbarer Beleg für einen Fehler in `worker/operator_rate_limit.py`.
- Sichere Wiederholung: einmaliges privates Basisverzeichnis außerhalb von `pytest-of-Steven` wählen und explizit `py -m pytest -q --basetemp="$testTemp"` ausführen, mit `$testTemp = Join-Path $env:LOCALAPPDATA ('gpt-local-llm-worker\\pytest-' + [guid]::NewGuid().ToString('N'))`. Zuerst gezielte Rate-Limit-Tests, anschließend Gesamtsuite. Kein Löschen oder Rechteändern an bestehenden pytest-Verzeichnissen.
- Der neue vollständige Windows-Lauf mit eigenem `--basetemp` ist **noch offen**. Keine echte SSH-Verbindung, kein Login-Endpunkt und kein Auto-Send.

## Offline Operator Login → LIVE-Audit-Gate (2026-11-15)
- **Windows-Basis bestätigt:** isoliertes `py -m pytest -q tests/test_operator_rate_limit.py --basetemp=...` → **8 passed, 1.15 s**; vollständige Suite mit eigenem Basisverzeichnis → **108 passed, 1 skipped, 34 subtests passed, 4.61 s**. Die alte pytest-Temp-Verzeichnis-Aufräumstörung trat nicht wieder auf.
- **Implementiert:** `worker/trusted_operator_flow.py` setzt `OperatorCredentialFile.load()`, `OperatorAuthenticator`, `PersistentOperatorVerifier`, `LiveApprovalLedger` und `OfflineLiveApprovalGate` zu einem isolierten Python-Aufruf zusammen. Exakt ein persistierter LIVE-Antrag liefert Command-/Target-Digest sowie Chat/Tab; der Aufrufer kann nur Request-ID und Passwort übergeben. Jeder Passwortversuch nutzt die dauerhaft gespeicherte Fehlversuchssperre. Nach Erfolg erzeugtes Ticket wird sofort für transaktionale Freigabe plus Audit verwendet. Kein Vertrauen in Mock-Bearer oder Modellantwort als Passwort.
- **Tests:** `tests/test_trusted_operator_flow.py` umfasst 7 Offline-Fälle: gültige Genehmigung/Audit ohne SSH, Neustart-Sperre, Mock-Approval-Token als ungültiges Passwort, fehlende Credential-Datei, keine Client-Zielüberschreibung, Doppelapprove-Sperre, kaputte Rate-Limit-Datenbank fail-closed. Konstrukt ist **nicht** in FastAPI, Brave oder Worker-CLI verdrahtet; `LiveApprovalLedger.claim_execution` bleibt deaktiviert.
- **Windows-Prüfung noch offen:** `py -m pytest -q tests/test_trusted_operator_flow.py --basetemp=...`, anschließend `py -m pytest -q --basetemp=...`. Erwartet bei Erfolg: **115 passed, 1 skipped, 34 subtests passed**. Keine Live-SSH-Verbindung, kein automatischer ChatGPT-Versand.

## Windows-Testfehler: offenes SQLite-Handle im Trusted-Flow-Test (2026-11-15)
- Nutzer-Test nach Pull bis `28c10a2`: `tests/test_trusted_operator_flow.py` **6 passed, 1 failed**, vollständige Suite **114 passed, 1 skipped, 34 subtests passed, 1 failed**. Der einzige Fehler entsteht während der `TemporaryDirectory.cleanup()` bei `throttle.sqlite` mit Windows `PermissionError [WinError 32]`.
- Ursache: `test_corrupt_throttle_database_denies_approval` benutzte `with sqlite3.connect(self.rate_path) as db:`; `Connection.__exit__` führt lediglich Commit/Rollback durch und schließt den Datei-Handle nicht. Die produktive `PersistentOperatorVerifier._connect`-Implementierung schließt ihre Verbindungen im `finally` korrekt.
- Fix in `tests/test_trusted_operator_flow.py`: `from contextlib import closing` und `with closing(sqlite3.connect(self.rate_path)) as db, db:`, sodass das Test-Handle vor temporärer Verzeichnisbereinigung geschlossen wird.
- **Tests nach Fix noch nicht durchgeführt**. Nächste Abnahme: fokussiert `py -m pytest -q tests/test_trusted_operator_flow.py --basetemp="$testTemp"`, vollständig `py -m pytest -q --basetemp="$testTemp"`. Erwartet 115 passed, 1 skipped, 34 subtests passed. Keine produktive SSH-Verbindung und keine Änderung der echten Freigabelogik.

## Eigenständiger lokaler LIVE-Freigabedialog (2026-11-15)
- **Vorherige Windows-Abnahme durch Nutzer:** `py -m pytest -q tests/test_trusted_operator_flow.py --basetemp=...` → **7 passed, 0.93 s**; komplette Suite → **115 passed, 1 skipped, 34 subtests passed, 5.51 s**. Kein offenes SQLite-Testhandle mehr.
- **Neu:** `worker/operator_review.py` mit `OperatorReviewController` und unveränderlichem `LiveReview`. Prüft vollständigen Kommando-SHA256 sowie die an den ursprünglichen Vorschlag gebundene SSH-Zielidentität aus separater konfigurierter Allowlist. Ein Review enthält Hostalias, Hostname, Port, SSH-Benutzer, öffentlichen Hostkey, CWD, Beschreibung, alle Befehle/Timeouts sowie Chat/Tab. Freigabe verlangt den unveränderten Review, explizite Full-Batch-Bestätigung, gleichen Digest und separates Betreiberpasswort über den bereits neustartfest gesperrten Authentifizierungsweg.
- **Neu:** `worker/operator_review_gui.py` bietet ein nur auf expliziten manuellen Aufruf gestartetes Tkinter-Fenster, schreibgeschützte scrollbare Befehlsanzeige, Checkbox, maskiertes Passwort und Abbruch. Separate lokale JSON-Host-Allowlist wird geprüft, keinerlei ChatGPT-Modelltext darf automatisch als Host-/Freigabeanweisung dienen. **Keine Browser-/HTTP-Anbindung, keine Live-SSH-Ausführung und kein Rückversand.** Das GUI-Programm erfordert bereits vorhandenes Credential-File, LIVE-DB, Rate-Limit-DB, Host-Konfiguration und Request-ID; es gibt noch keinen produktiven Enrollment-/Erstellungsweg. Kein Nutzer-Host wurde konfiguriert.
- **Tests hinzugefügt:** `tests/test_operator_review.py` mit 9 Headless-Vertragstests (vollständige Anzeige, exakte Bestätigung, Digest-/Target-Mismatch, fehlender Host, manipulierte DB, Zustandswechsel, falsches Passwort). `tests/test_operator_review_gui.py` mit 7 zusätzlichen Headless-Validierungen (lokale Allowlist, unbekannte Felder, doppelte Hosts, unvollständige CLI-Daten). Der echte Tk-Dialog wurde nicht geöffnet, kein echter Host oder Schlüssel verwendet.
- **Teststatus:** Neue Windows-Python-Tests noch offen; `py -m pytest -q tests/test_operator_review.py tests/test_operator_review_gui.py --basetemp=...`, danach Gesamtsuite. Erwarteter Windows-Stand bei Erfolg: **131 passed, 1 skipped, 34 subtests passed**. Keine echte SSH-Verbindung, kein Browser-Auto-Send.

## Separater Windows-GUI-Smoke mit synthetischen Testdaten (2026-11-15)
- **Windows-Baseline bestätigt:** `py -m pytest -q tests/test_operator_review.py tests/test_operator_review_gui.py --basetemp=...` → **16 passed, 0.79 s**; vollständige Suite → **131 passed, 1 skipped, 34 subtests passed, 6.28 s**.
- **Neu:** `scripts/operator-review-gui-smoke.py` erzeugt einen kurzlebigen, rein synthetischen LIVE-Vorschlag, separate Betreiber-Credentials, Rate-Limit-DB und Ziel-Allowlist im Speicher, alles innerhalb eines `TemporaryDirectory`. Verwendet den echten lokalen Tk-Dialog und die echten Offline-Audit-/Passwortmodule, aber **keinen SSHTransport**, kein real auflösbares SSH-Ziel und kein Browser-/HTTP-/ChatGPT-Frontend. Gibt ausschließlich ein bekanntes synthetisches Fixture-Passwort für eine manuelle Prüffreigabe aus. Abbruch lässt `PROPOSED`; eine Testfreigabe erzeugt genau einen Audit-Eintrag. Beide Pfade entfernen die temporären Daten nach Schließen.
- **Neue Tests:** `tests/test_operator_gui_smoke.py` mit 4 Headless-Smoketests für Vorschau, Abbruch, gültige einmalige Offline-Genehmigung und falsches Testpasswort. Es wird in pytest **kein Tk-Fenster gestartet**. Das echte Fenster benötigt einen manuellen Windows-Test.
- **Ausstehend:** `py -m pytest -q tests/test_operator_gui_smoke.py --basetemp=...`, danach `py -m pytest -q --basetemp=...` (erwartet **135 passed, 1 skipped, 34 subtests passed**), anschließend `py scripts/operator-review-gui-smoke.py` und Sichtkontrolle von Fensterlayout, Checkbox, Passwort, Abbrechen und Erfolgsmeldung. Keine produktiven Credentials installieren und keine SSH-Freigabe.

## Windows GUI-Smoke: Headless bestanden, Dialog startet sichtbar (2026-11-15)
- Nutzer nach Pull bis `09204fa`: `py -m pytest -q tests/test_operator_gui_smoke.py --basetemp=...` → **4 passed, 0.39 s**; vollständige Suite → **135 passed, 1 skipped, 34 subtests passed, 6.92 s**. Exitcode der Python-Regression 0.
- Manuell `py scripts/operator-review-gui-smoke.py` gestartet. Terminal bestätigt: `OFFLINE GUI SMOKE: Keine SSH-Verbindung, keine Browseraktion.` und zeigt das synthetische Fixture-Passwort. Nutzer-Screenshot zeigt ein tatsächlich geöffnetes Windows-Tk-Fenster mit den zwei exakten Fixture-Befehlen, Hostalias und `fixture.example.invalid`, Zielbenutzer/Port, Hostkey-Platzhalter, CWD, Ursprungschat/Tab, Command-/Target-Digests, Checkbox, maskiertem Passwortfeld, Abbrechen und Freigabe-Button.
- **Manueller Freigabeklick noch nicht bestätigt:** Ein GUI-Screenshot des offenen Fensters und ein gestarteter Prozess beweisen nicht, dass die tatsächliche Passwortprüfung/Bestätigung/SQLite-Audit-Erfolgsmeldung durchgeklickt wurde. Für die GUI-Abnahme noch Testpasswort eingeben, Checkbox aktivieren und im Terminal `OFFLINE PASS: genau eine Testfreigabe und ein Audit-Eintrag.` prüfen; Abbruchpfad separat in einem weiteren Start.
- Keine echten SSH-Hosts konfiguriert, kein Live-SSH gestartet und keine ChatGPT-Nachricht automatisch versandt. Produktiver Rollout und Branch-Merge weiterhin gesperrt.

## Tkinter-Cleanup nach erfolgreichem Freigabeklick (2026-11-17)
- Nutzer führte den manuellen Test `py scripts/operator-review-gui-smoke.py` mit synthetischem Testpasswort aus. Ergebnis: `OFFLINE PASS: genau eine Testfreigabe und ein Audit-Eintrag.`, also erfolgreiche persistierte Testgenehmigung ohne SSH. Gleichzeitig warf der Tkinter-Callback nach Freigabe `_tkinter.TclError: can't invoke "winfo" command: application has been destroyed`.
- Ursache: `open_local_review.approve()` rief im Erfolgszweig `root.destroy()` und danach im `finally`-Block noch `root.winfo_exists()` auf. Nach zerstörter Tcl-App darf kein Widget-Aufruf mehr erfolgen.
- Fix in `worker/operator_review_gui.py`: Passwortfeld im jeweiligen Erfolgs-/Fehlerpfad **vor** weiteren GUI-Operationen löschen; nach `root.destroy()` keinerlei Tcl-Methoden mehr aufrufen. Ein neuer Headless-Regressionstest in `tests/test_operator_review_gui.py` simuliert einen Tk-Root, der jeden `winfo_exists()`-Aufruf nach `destroy()` verweigert, und prüft die Reihenfolge Passwort-Löschen → Fenster zerstören.
- **Neue Tests nach Commit noch nicht unter Windows ausgeführt.** Erwartet: gezielte `tests/test_operator_review_gui.py` **8 passed**, Gesamtsuite **136 passed, 1 skipped, 34 subtests passed**. Danach manueller synthetischer Freigabeklick ohne Tkinter-Traceback prüfen. Keine echte SSH-Verbindung, keine produktive Freigabe und kein Auto-Send.

## Offline-GUI bestätigt; lokales Operator-Enrollment (2026-11-17)
- **Manuelle GUI-Bestätigung:** Nach Fix des Tkinter-Cleanup-Bugs meldet der Benutzer beim erneuten `py scripts/operator-review-gui-smoke.py`: `OFFLINE PASS: genau eine Testfreigabe und ein Audit-Eintrag.` sowie `Kein SSH gestartet; temporäre Testdateien werden bereinigt.`; diesmal **ohne Tkinter-Traceback**. Der Fix des realen GUI-Lebenszyklus ist damit manuell unter Windows bestätigt. Der vollständige pytest-Lauf nach dem GUI-Fix wurde separat nicht berichtet; zuletzt 135 passed/1 skipped/34 subtests vor dem GUI-Fix.
- **Neues tatsächliches Feature statt weiterer reiner Guards:** `worker/operator_setup.py` stellt ein lokales CLI-Enrollment bereit. Der Betreiber gibt ein separates Passwort zweimal über `getpass` ein; der bestehende DPAPI/0600-Store schreibt einen nicht überschreibbaren Credential-Datensatz, und die separate Rate-Limit-SQLite-DB wird angelegt. Kein Passwort in Argumentliste, kein Host und keine SSH-Ausführung. Keine automatische Kopplung mit Brave.
- **Tests:** `tests/test_operator_setup.py` enthält 8 fokussierte Tests zu Enrollment, Passwortbestätigung, nicht überschreibbarer Credential- und Rate-Datenbank, ungültigem Passwort/Pfad und interaktivem Terminal-Contract.
- **Nächste Windows-Abnahme:** `py -m pytest -q tests/test_operator_setup.py tests/test_operator_review_gui.py --basetemp=...`, anschließend `py -m pytest -q --basetemp=...`. Erwartet **144 passed, 1 skipped, 34 subtests passed**, sofern kein weiterer plattformbedingter Skip erfolgt. Danach **erst** bewusstes produktives Enrollment mit einem vom Betreiber selbst gewählten Passwort; weiterhin keine realen SSH-Targets/Browser-Auto-Send.

## Windows-Abnahme Operator-Enrollment (2026-11-17)
- Nutzer hat nach Pull bis `5d159fa` `py -m pytest -q tests/test_operator_setup.py tests/test_operator_review_gui.py --basetemp=...` mit **16 passed, 0.28 s** bestätigt.
- Die komplette Python-Regression `py -m pytest -q --basetemp=...` war **144 passed, 1 skipped, 34 subtests passed, 6.93 s**, Exitcode 0.
- Der manuelle GUI-Smoke mit synthetischer Freigabe war bereits erfolgreich (exakt ein Audit-Eintrag, kein Tkinter-Traceback). Das bedeutet **nicht**, dass ein reales Betreiberkonto angelegt oder ein SSH-Ziel konfiguriert wurde.
- **Nächster praktischer Operator-Schritt:** Einmaliges interaktives Enrollment mit `py -m worker.operator_setup --state-dir "$env:LOCALAPPDATA\\gpt-local-llm-worker\\operator" --operator-id local-operator` in einem PowerShell-Terminal; das Betreiberpasswort nie im Chat oder als Argument veröffentlichen. Setup erzeugt Credential und Rate-Limit-SQLite, keinen Host, keine LIVE-Ausführung.
- Vor produktiver SSH-Nutzung stehen weiterhin lokale Host-Allowlist und vertrauenswürdige Hostkey-Verifikation, LIVE-Proposal-Eingang, explizit freigegebene Live-Testdurchführung und sichere Browser-Rückkopplung aus. Keine Freigabe für SSH oder Auto-Send erfolgt.

## Mindestlänge auf 8 Zeichen abgesenkt (2026-11-22)
- Nutzer möchte statt der bisherigen 16-Byte-Untergrenze nur noch **8 Zeichen** für das lokale Betreiberpasswort. Der erste Enrollment-Versuch unter Windows meldete `invalid_operator_secret`; Credential-/Rate-Limit-Anlage geschah vor der Passwortvalidierung noch nicht.
- `worker/operator_auth.py`: `_MIN_SECRET_CHARS = 8`, Prüfung per `len(secret)` (Unicode-Zeichen), Maximalgröße weiter 1024 UTF-8-Bytes. Alle scrypt-/DPAPI-/Persistenz-/Audit-Schutzmaßnahmen bleiben unverändert; kein echter SSH- oder Browser-Send-Pfad aktiv.
- Neue Tests in `tests/test_operator_auth.py` für genau 8 ASCII-/Unicode-Zeichen und Ablehnung von 7 Unicode-Zeichen. Neuer Setup-Test in `tests/test_operator_setup.py` prüft Enrollment mit genau 8 Zeichen.
- **Windows-Tests nach Änderung noch offen:** `py -m pytest -q tests/test_operator_auth.py tests/test_operator_setup.py --basetemp=...` und danach gesamte Regression. Bisherige bestätigte Basis: **144 passed, 1 skipped, 34 subtests passed**; erwartet nach neuen Testfällen **147 passed, 1 skipped, 36 subtests passed** (durch zwei Unicode-Subtests). Das echte Konto wurde noch nicht eingerichtet; Benutzer sollte Passwort niemals im Chat posten.

## Erstmaliges Betreiber-Enrollment unter Windows erfolgreich (2026-11-22)
- Benutzer hat `py -m worker.operator_setup --state-dir (Join-Path $env:LOCALAPPDATA 'gpt-local-llm-worker\\operator') --operator-id local-operator` interaktiv ausgeführt; Meldung: `Betreiber-Credential und Rate-Limit-Datenbank eingerichtet.` Ablage: `C:\\Users\\steve\\AppData\\Local\\gpt-local-llm-worker\\operator`. Das separate Betreiberpasswort wurde **nicht** im Chat veröffentlicht.
- Ergebnis bestätigt Anlegen der lokalen Credentials und Rate-Limit-Datenbank über den produktiven Setup-Einstieg unter Windows; es handelt sich nicht um die vollständige Abnahme eines produktiven LIVE-SSH-Flows.
- Weiterhin **kein SSH-Ziel hinterlegt**, keine SSH-Ausführung, keine Brave-Auto-Send-Anbindung. Nächster Schritt: vertrauenswürdige separate SSH-Host-Allowlist mit geprüftem öffentlichen Hostkey, zunächst ohne Verbindungen oder Live-Deployment.

## Lokale SSH-Host-Allowlist, create-only (2026-11-22)
- **Implementiert:** `worker/operator_hosts.py` mit CLI und `enroll_host` legt eine neue, dem LIVE-Review-Format entsprechende JSON-Allowlist mit genau einem Host an. Geprüft werden Alias, Hostname, SSH-Benutzer, Port, vollständiger öffentlicher OpenSSH-Hostkey inklusive eingebettetem Algorithmus und ein separat bestätigter SHA-256-Fingerprint. Ausschließlich bestehende **lokale** Schlüsseldateien; es gibt keine Netzabfrage und keinen Aufruf von `ssh-keyscan`. Vorhandene Hostliste wird nicht überschrieben. Die Ausgabe enthält Alias/Ziel und den angegebenen Fingerprint, niemals ein Passwort oder einen privaten Schlüssel.
- **10 Headless-Tests:** `tests/test_operator_hosts.py` mit synthetischem ED25519-Wireformat, positivem Review-Format-Rundlauf, falschem Fingerprint, manipuliertem Keytyp/Schlüsselblob, No-Overwrite-Sperre, fehlerhaften Zielparametern, relativen/fehlenden Dateipfaden und CLI-Aufruf.
- **Noch offen:** Windows-Tests `py -m pytest -q tests/test_operator_hosts.py --basetemp=...` und gesamte `py -m pytest -q --basetemp=...`. Die nach Passwortänderung hinzugekommenen 3 Tests wurden ebenfalls noch nicht per Windows-Log bestätigt. Erwarteter Stand bei erfolgreichem vollständigem Lauf: **157 passed, 1 skipped, 36 subtests passed**.
- **Nutzeraktion erforderlich:** ersten echten SSH-Zielhost festlegen und dessen **öffentlichen Hostkey mitsamt Fingerprint unabhängig** an der Serverkonsole auslesen/verifizieren. Keine automatische Hostentdeckung, kein Hinterlegen erfundener NAS-Adressen, keine realen SSH-Verbindungen, keine Privatschlüssel-Erzeugung oder Änderung vorhandener SSH-Dienste. Weitere Hosts erfordern ein späteres ausdrücklich abgesichertes Update-Verfahren.

- **Ergänzung:** Der Hostkey-Parser unterstützt den üblichen optionalen OpenSSH-Kommentar nach dem Schlüssel und entfernt diesen aus der gespeicherten kanonischen Identität. Mehrzeilige Schlüsseldateien werden verweigert. Regressionstest in `tests/test_operator_hosts.py`; Windows-Teststatus weiterhin offen.

## Vorhandene OpenSSH-Aliase übernehmen (2026-11-22)
- Nutzer hat lokale `ssh -G`- und `ssh-keygen -F`-Ausgaben vorgelegt. Genau drei Ziele: `nas` → `steven@192.168.0.100:22` mit `~/.ssh/id_ed25519_nas`; `backup-nas` → `steven@192.168.0.101:22` mit `~/.ssh/id_ed25519_backup-nas`; `vserver` → `steven@87.106.7.53:22` mit `~/.ssh/id_ed25519_vserver`. Lokale `known_hosts` enthalten jeweils ED25519, RSA und ECDSA. Die Ausgabe ist noch **kein unabhängiger Nachweis** der Hostidentität.
- **Implementiert:** `worker/operator_ssh_import.py` übernimmt die Alias-/Host-/User-/Port-Auflösung ausschließlich mittels lokaler `ssh -G`-Abfragen, den jeweiligen ED25519-Hostkey über `ssh-keygen -F`; für jeden Alias muss ein unabhängig bestätigter SHA256-Fingerprint übergeben werden. Erst bei vollständiger Prüfung aller drei wird eine neue, nicht überschreibbare JSON-Allowlist im bestehenden `LiveTargetBinding`-Format erzeugt. Kein privater Schlüssel wird gelesen, keine SSH-Verbindung gestartet. Bei mehreren verschiedenen ED25519-Einträgen oder einer vorhandenen Datei gilt fail-closed.
- **Neue Tests:** `tests/test_operator_ssh_import.py` mit 6 Mock-Tests: konsistente Drei-Host-Datei, falscher Fingerprint, unvollständige Bestätigung, No-Overwrite, mehrdeutige Hostkey-Einträge und Einzel-Alias-Inspektion. Netzwerk-/SSH-Execution-Tests finden nicht statt.
- **Ausstehend:** Windows-Tests für die bereits zuvor implementierte Hostverwaltung und den Import: `py -m pytest -q tests/test_operator_hosts.py tests/test_operator_ssh_import.py --basetemp=...`; danach `py -m pytest -q --basetemp=...`. Nach den Passworttests und Hosttests werden bei Erfolg **163 passed, 1 skipped, 36 subtests passed** erwartet. Für tatsächliches Anlegen der drei Hosts sind zunächst deren Fingerprints unabhängig an den Serverkonsolen zu verifizieren. Keine automatisch konfigurierte Live-SSH-Ausführung, keine Änderung an SSH-Konfiguration oder bestehenden Schlüsseln.

## Windows-Regression der Hostverwaltung (2026-11-22)
- Benutzer meldet vollständigen Lauf `py -m pytest -q --basetemp="$testTemp"` nach Einführung des Drei-Alias-Importers: **163 passed, 1 skipped, 41 subtests passed, 7.53 s**, ohne Exceptions; anschließende Exitcode-Prüfung ohne Fehler. Die tatsächliche Zahl der Subtests beträgt **41**, nicht die zuvor prognostizierten 36.
- Fokussierter Testlauf für `tests/test_operator_hosts.py tests/test_operator_ssh_import.py` wurde in dieser Nachricht nicht separat berichtet. Der gesamte Lauf deckt sie nach dem gezeigten Branchstand ab.
- Noch offen: Die unabhängig an den Serverkonsolen ausgelesenen ED25519-Fingerprints von `nas`, `backup-nas` und `vserver` abgleichen, erst danach lokale `targets.json` einmalig anlegen. Keine SSH-Ausführung oder automatische Browser-Nachricht autorisiert.

## Drei produktive SSH-Hostidentitäten lokal angelegt (2026-11-22)
- Nutzer hat den Offline-Importer `py -m worker.operator_ssh_import` auf Windows erfolgreich ausgeführt, inklusive der drei zuvor bereitgestellten ED25519-SHA256-Fingerprints. Ausgabe: `Host-Allowlist angelegt. Kein SSH gestartet; LIVE-Executor bleibt deaktiviert.` und Exitcode 0.
- Lokale Allowlist liegt unter `C:\\Users\\steve\\AppData\\Local\\gpt-local-llm-worker\\operator\\targets.json` mit genau diesen Einträgen: `nas` → `steven@192.168.0.100:22`, `backup-nas` → `steven@192.168.0.101:22`, `vserver` → `steven@87.106.7.53:22`. Alle enthalten einen öffentlichen `ssh-ed25519`-Hostkey. Die Schlüssel selbst sind nur öffentliche Hostidentitäten; private SSH-Identitätsdateien verbleiben in der bestehenden Benutzer-SSH-Konfiguration.
- Das erfolgreiche Matching belegt Konsistenz mit den lokalen `known_hosts`-Einträgen und den eingegebenen Fingerprints; ob die Fingerprints unabhängig an einer vertrauenswürdigen Serverkonsole ermittelt wurden, ist aus dem Log allein nicht technisch nachweisbar.
- **Nächste Implementierungsaufgabe:** Bridge-Eingang für explizite, abgeschlossene JSON-SSH-Batches mit Host-Allowlist und LIVE-Proposal-Ledger verbinden. Den GUI-Review nur über bewusst lokale Nutzeraktion starten; Freigabe und Audit müssen weiterhin atomar und origin-/digest-gebunden bleiben. Vor einer echten SSH-Ausführung: getrennte Prüfung der vorhandenen IdentityFile-Konfiguration und ausdrückliche Freigabe zum LIVE-Test. Kein Browser-Auto-Send ohne geprüfte Ursprungskonversation.

## Bridge → LIVE Intake → lokale Operator-Freigabe (2026-11-23)
- Ausgangspunkt: Betreiber-Credential unter `%LOCALAPPDATA%\\gpt-local-llm-worker\\operator` und Host-Allowlist mit `nas`, `backup-nas`, `vserver` bereits erfolgreich unter Windows eingerichtet. Frühere GUI-Smokes und die 163+41-Regression bestanden.
- **Implementiert:** separater opt-in FastAPI-Eingang `worker/live_capture_api.py` mit `POST /api/bridge/v1/captures`, deduplizierter `live_captures`-Tabelle und unveränderlichen `live_proposals`-Einträgen für explizite JSON-Aufträge. Beide Datensätze entstehen in einer SQLite-Transaktion. Kein Speichern gewöhnlicher ChatGPT-Antworttexte, sondern nur SHA-256; LIVE-Aufträge enthalten weiterhin die zur Prüfung nötigen vollständigen Befehle.
- Nur lokaler Prozess auf 127.0.0.1, separates Token mit mindestens 32 Zeichen und konkret erlaubte Extension-Origin. **Keine** LIVE-Approve-/Reject-/Execution-/Outbound-Claim-Route; die Mock-Approval-Panelliste wird im LIVE-Backend absichtlich leer gemeldet. Bestehende Mock-Simulation unverändert.
- **Manueller GUI-Einstieg:** `worker/live_review_launcher.py --list` zeigt offene Proposals, `--request-id` öffnet bestehenden echten Operator-Review. Passwortprüfung, Einmalticket, persistente Sperre und Audit bleiben am bisherigen Offline-Gate. Freigabe ist **kein** SSH-Start; spätere Bridge-Rücksendung nicht aktiviert.
- Neue Tests `tests/test_live_capture_api.py` (11 API-Vertragstests) und `tests/test_live_review_launcher.py` (3 CLI-Vertragstests), keine Netzverbindung oder echten Server. **Windows-Verifizierung und Browser-LIVE-E2E stehen aus**. Bei Erfolg wäre die Vollsuite mindestens **177 passed, 1 skipped, 41 subtests passed**, sofern weitere plattformbedingte Skips unverändert bleiben.
- **Nächste Testaktion:** `py -m pytest -q tests/test_live_capture_api.py tests/test_live_review_launcher.py --basetemp=...`, danach vollständiges `py -m pytest -q --basetemp=...`. Für einen echten Browser-Capture-Test die LIVE-API nur explizit und getrennt vom bisherigen Mock auf Port 8765 starten, ein eigenes neues Token im Brave-Panel hinterlegen; ohne den Betreiber-Test nicht behaupten, die echte Brave-Auftragsübergabe sei bereits unter Windows abgenommen.
- **Weiterhin offen:** Trusted-Origin-Tab-Provenienz unabhängig vom untrusted Client, sichere GUI-/Panel-Handoff-Bedienung, Behandlung von Neustart-/Capture-Retries, spätere ausdrücklich genehmigte SSH-Identitätsbindung an die vorhandene `~/.ssh/config`, endgültiger LIVE-Executor und ausschließlich geprüfte Ergebnis-Rücksendung. Keine realen SSH-Aufrufe, keine Änderungen an NAS/Backup-NAS/vserver, kein Branch-Merge.

- **Härtung:** SQLite `BEGIN IMMEDIATE` vor jeder Capture-/Request-ID-Prüfung, um parallele Client-Retries zu serialisieren. Neue Tests prüfen, dass unstrukturierter Capture-Text nicht im SQLite-Body gespeichert wird und CORS ausschließlich die konfigurierte Extension-Origin freigibt. Windows-PowerShell-5.1-kompatible Zufallstoken-Erzeugung im README dokumentiert. Weiterhin keine Laufzeitabnahme der neuen API unter Windows.
