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
