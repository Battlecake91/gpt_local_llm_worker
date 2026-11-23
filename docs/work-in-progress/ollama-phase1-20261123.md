# Ollama-Analyse normaler ChatGPT-Antworten (2026-11-23)

## Scope und Branch
- Branch: `feature/brave-chat-bridge`
- Ziel: Klassifikation normaler ChatGPT-Antworten in überprüfbare interne SSH-Vorschläge, weiterhin ohne SSH-Ausführung und ohne Browser-Auto-Send.
- Ursprung: Entwicklungsauftrag für Ollama/Brave/SSH, Phase 1.
- Ausgangs-HEAD: `b27606887f91af887f27f6813aa83f5fbb1ef742`.

## Umgesetzt
- `worker/ollama_analysis.py`: Profile für Windows-Ollama, NAS und zusätzliche konfigurierte Hosts, validierte Konfiguration, HTTPX-Anbindung mit JSON-Modus, optionaler Bearer-Token ausschließlich aus Worker-Umgebung, Risiko-/Hostbewertung.
- Extraktion vollständiger vorhandener `bash`, `sh`, `shell` oder `console`-Codeblöcke, unbeschrifteter Fences und explizit markierter `$ befehl`-Terminalzeilen. Kein Hinzufügen, Kürzen oder Ersetzen durch das LLM. Kein Codeblock bedeutet keinen LLM-Aufruf. Nicht erkannter Host erzeugt keinen LIVE-Proposal.
- `worker/live_capture_api.py`: Opt-in mit `--ollama-profiles`, deduplizierte Erfassung und transaktionale Ablage von unveränderlichem LIVE-Vorschlag und separat gespeicherter LLM-Risikoeinschätzung. Ohne Opt-in bleibt alter JSON-Parser unverändert verfügbar.
- Authentifiziert: `GET /api/bridge/v1/ollama/profiles`, `POST /api/bridge/v1/ollama/select`, `GET /api/bridge/v1/ollama/suggestions`. Profilwechsel ohne Prozessneustart.
- Bewusst **nicht** gekoppelt: freie LLM-Einstufung zu automatischer Freigabe, SSH-Executor, Sudo oder Rückkanal.
- Neue Offline-Fälle in `tests/test_ollama_analysis.py`, zusätzlich CI-Workflow für Python/Node-Regressionssuiten.

## Integration
Eine Vorlage liegt in `config/ollama-profiles.example.json`. Für die Verwendung eine lokale Kopie außerhalb des Git-Repositories anlegen und mit `--ollama-profiles ABSOLUTER_PFAD` starten. `auth_env` ist der Name einer lokal gesetzten Umgebungsvariablen für das Profil-Token, niemals das Token selbst.

Die vorhandene LIVE-API bleibt explizit separat und standardmäßig ohne Ollama. Konfigurationsfehler verhindern den Start; LLM-Fehler verhindern die Annahme eines daraus abzuleitenden Auftrags (HTTP 503). Nur vollständig validierte interne Batches können in `live_proposals` gelangen. Resultate aus `ollama_suggestions` werden noch nicht im Brave-Seitenpanel angezeigt.

## Einschränkungen
- Fenced Shell-Codeblöcke werden blockweise, nicht zeilenweise extrahiert. Unmarkierte Fließtext-Befehle sind noch nicht unterstützt; explizite `$ befehl`-Terminalzeilen dagegen schon. Das vermeidet unsichere Kommandorekonstruktion.
- Modellbewertung ist keine verlässliche Sicherheitsentscheidung, insbesondere bei Beispieltext. Keine automatische Freigabe in Phase 1.
- Profilkonfiguration ist vom lokalen Betreiber zu schützen; Profilauswahl über bestehende Token-API beschränkt sich auf bereits konfigurierte Endpunkte.
- Keine live Ollama-/Windows-/Brave-Tests und keine echten SSH-Verbindungen. GitHub Actions run 45192345783 auf Commit 9306a64: erfolgreich. Der Job hat sowohl `python -m pytest -q` als auch `node --test tests/*.cjs` erfolgreich abgeschlossen. Ein echter Ollama-/Windows-/Brave-Lauf bleibt offen.
- WIP in den nächsten Phasen: Profil-/Modellwahl im Panel, Modellabfrage und Verbindungstest, unmarkierte eindeutige Befehle, robustere Beispiel-/Zitatklassifikation, Ampel-UI und Zielkorrektur, separate Freigabe- und Sudo-Logik.

## Testbefehle
```powershell
py -m pip install -e ".[test]"
py -m pytest -q tests/test_ollama_analysis.py tests/test_live_capture_api.py
py -m pytest -q
node --test tests/*.cjs
```

## CI-Abnahme
- [GitHub Actions: Python- und Brave-JavaScript-Regressionen bestanden](https://github.com/Battlecake91/gpt_local_llm_worker/actions/runs/45192345783), Commit `9306a64f15547f0835c0dde99133edb841c2a0b1`.
- Der vorangehende CI-Lauf `45192260869` war wegen fehlerhafter Escape-Zeichen in einer neuen Test-Fixture fehlgeschlagen. Die Fixture wurde korrigiert und der vollständige nächste Lauf war erfolgreich.

## Reproduzierbarer echter Ollama-Risikobenchmark (2026-11-23)
- `worker/ollama_benchmark.py`: 19 unveränderliche Testfälle, standardmäßig zwei Durchläufe (=38 Ollama-Anfragen). Grün/Gelb/Rot, Sudo-Lesediagnose, destruktive Operationen, NAS/Backup-NAS/VServer, Hostkonflikt, fehlender Host, bloße Beispielanweisung, unmarkierte Prosa und gemischte Risikostufen.
- Der Runner verwendet ausschließlich `OllamaAnalyzer.analyze`; keinerlei SSH-, Shell-, Sudo- oder Browser-Aufrufe.
- Jedes Ergebnis enthält Soll- und Ist-Wert, Feldabweichungen, Fehler, Dauer und Kennzeichen für *gefährliche Unterbewertung* (z.B. Rot -> Grün). Die Benchmarkklassifikation ist selbst kein automatischer Sicherheitsentscheid.
- Lokaler Aufruf (Windows PowerShell, Repository-Root):
  ```powershell
  py -m worker.ollama_benchmark --runs 2 --output "$env:TEMP\ollama-benchmark.json"
  ```
- Erwartung vor Automatik: keine Unterbewertungen; jede Abweichung untersuchen, insbesondere Beispieltexte und Hostkonflikte. Selbst 100 % Treffer in 38 Testfällen wären keine Sicherheitsgarantie. Bis zur Auswertung bleiben Auto-Approval und produktiver SSH-Executor deaktiviert.
- Regression: `tests/test_ollama_benchmark.py` verwendet reine Fixtures und prüft auch Fälle mit falscher grüner Einstufung roter Befehle.
- Echte Modellresultate können nur auf dem Benutzer-PC mit laufendem Ollama erhoben werden; CI prüft lediglich die deterministische Benchmarklogik.

## Erster Live-Benchmark-Befund (Windows, 23.11.2026)
- Betreiber hat den Commit `53d146d` im lokalen Feature-Checkout installiert und `py -m pytest -q tests/test_ollama_benchmark.py tests/test_ollama_analysis.py` ausgeführt: **25/25 PASS** (Fixtures/Parser, kein realer Modellnachweis).
- Echte Ollama-Ausführung `py -m worker.ollama_benchmark --runs 2 --output "$env:TEMP\\ollama-benchmark.json"`: **10/38 korrekt, 28 Abweichungen, 0 erkannte gefährliche Unterbewertungen**. Beide Iterationen zeigen nahezu identisches Trefferbild. Positive Beispiele: `red-zpool`, `host-backup`, `example`, `prose`, `multi-risk`. Bei vielen anderen Fällen werden `risk=None`/`host=None` angezeigt.
- **Befundgrenze:** Die Konsolenanzeige `risk=None`/`host=None` ist mehrdeutig: `evaluate()` verwendet `actual=None` sowohl für `AnalysisError`-Fälle als auch sinngemäß `None`-Resultate von `analyze()`; Fehlertexte werden ausschließlich im JSON gespeichert. Ohne `items[].error`, `items[].actual` und `items[].matches` ist weder ein Modell- noch ein Parserfehler bewiesen. `0 underclassified` umfasst nicht vollständig abgelehnte Fälle und begründet deshalb keine Sicherheitsfreigabe.
- **Nächste zwingend notwendige Betreiberaktion:** Den schon lokal vorhandenen Bericht `%TEMP%\\ollama-benchmark.json` ohne erneute Ollama-Anfragen lesend zusammenfassen: aktive Modell-/Profilbezeichnung sowie Fehlermuster von `error`, `actual.actionable`, `actual.commands` und `matches`, jeweils mit Fall-ID. Darauf basierend ausschließlich den nachgewiesenen Fehlerpfad korrigieren und denselben Live-Benchmark wiederholen. Bis dahin kein Modell-Tuning auf Verdacht und keine Auto-Approval-/LIVE-SSH-Aktivierung.

## Befund aus realem qwen3.5:4b-Lauf und gezielter Parser-/Prompt-Fix (23.11.2026)
- Vom Betreiber auf Windows gemessen mit Profil `local` und Modell `qwen3.5:4b`: 10/38 korrekt, 28 Abweichungen, 0 erkannte Unterbewertungen. Im ersten Durchlauf **12** explizit zu ausführende Fälle durch `analyze()` als nicht ausführbar klassifiziert (`actual.actionable=false`, kein Parserfehler), **2** Fälle `invalid_risk` (`red-rm`, `host-vserver`), **5** korrekt. Die zweite Iteration zeigte das gleiche Fallmuster. **Dies ist ein echter Modellfehler**, nicht bloß ein Anzeigefehler der Benchmark-Konsole.
- Vorher lag die gesamte Klassifikationsanweisung mitsamt untrusted Chat-Antwort in einer einzigen Ollama-`user`-Nachricht. Neu: explizite, von der Antwort getrennte `system`-Nachricht mit deutschen/englischen Imperativbeispielen, Klarstellung `read-only` bedeutet trotzdem ausführbarer Arbeitsauftrag, Risikobeispielen für Grün/Gelb/Rot und ausdrücklicher Nichtausführungs-/Nichtfreigaberegel. Untrusted Antwort steht ausschließlich als `user`-Inhalt. Die originalen vollständigen Befehlsblöcke bleiben Pflicht, der Parser verweigert erfundene/fragmentierte Befehle wie zuvor.
- Das JSON-Schema lässt bei `actionable=false` semantisch sinnvoll `risk=null` zu; bei `actionable=true` ist Grün/Gelb/Rot weiter zwingend. Der Parser meldet nun `invalid_risk_value` getrennt von `invalid_reason`, damit der verbleibende echte Fehler eindeutig zugeordnet werden kann.
- Host-Ziel ist ab jetzt ausschließlich durch **genau eine explizite Nennung im Text vor dem Code** zulässig. Gibt es keinen expliziten Host oder widersprechen sich NAS und Backup-NAS, darf die Modellantwort kein Hostziel erfinden oder unter Konflikt einen Host auswählen. Das ist eine Sicherheitsverschärfung, keine implizite Freigabe.
- Benchmark führt pro Fall `failure_kind` separat (`actionability_mismatch`, `analysis_error`, `wrong_commands`, `wrong_host`, `wrong_risk`). Der gefilterte Konsolenbericht zeigt Fehlerart, aber keinen originalen Antworttext oder private Befehle.
- Neue Offline-Tests spezifizieren System-/User-Rollentrennung, `null` für Nichtaktionen, unterschiedliche Fehlerarten, Konflikt-/Hosterfindungsschutz sowie Benchmarkdiagnose. **Keine Freigabe für Auto-Approval, produktive SSH-Ausführung oder Browser-Auto-Send.** Live-Lauf mit qwen3.5:4b ist erst nach Betreiber-`git pull` möglich. Verbesserungsrate bislang **nicht** gemessen; wenn der Live-Lauf weiterhin großflächig `actionable=false` liefert, ist Modell-/Versionvergleich statt unkontrollierter Heuristik-Overrides sinnvoll.

## Phase 2A: Brave-Vorschau (2026-11-23)
- `extension/background.js`: Nur die vertrauenswürdige Erweiterungs-Seitenleiste darf `LIST_OLLAMA_PROFILES` und `LIST_OLLAMA_SUGGESTIONS` anfragen. Beide Aktionen sind read-only und verwenden authentifizierte LIVE-API.
- `extension/panel.html` / `extension/panel.js`: Eigener aufklappbarer Bereich für gespeicherte Ollama-Vorschläge mit Profil, Modell, vorgeschlagenem Host, Risikostufe, Befehlen, Begründung und ursprünglichem Chat/Tab. Alle Modelltexte werden ausschließlich als `textContent` gerendert.
- Keine Anbindung an die bestehenden Mock-Freigabeaktionen. Keine Hoständerung, Freigabe, SSH-Ausführung, Auto-Send oder automatischer Modellwechsel; diese Aufgaben sind weiterhin offen.
- `tests/test_background.cjs`: nicht vertrauenswürdige Webseiten dürfen Ollama-Vorschläge und Profile nicht abrufen; Tests gewährleisten, dass nur GET-Anfragen erfolgen.
- Live-Prüfung offen: Start des separat konfigurierten `worker.live_capture_api` mit `--ollama-profiles`, echte Brave-Erweiterung neu laden, neuen abgeschlossenen ChatGPT-Turn erfassen und Vorschau im Panel prüfen. Nicht auf produktivem SSH ausführen.

## Phase 2A, echter Windows-Brave-Integrationsstart
- `scripts/windows-brave-ollama-preview.ps1` startet den vorhandenen Ollama-LIVE-Capture-Dienst separat auf `127.0.0.1:8765`, mit zufälligem Token, eigener Vorschau-DB und synthetischer Host-Allowlist (`*.example.invalid`). Die lokalen Ollama-Profile werden übernommen, es gibt keine SSH-/Approval-/Auto-Send-Endpunkte.
- Der Launcher verweigert belegten Port 8765, überschreibt keine vorhandene synthetische Allowlist und überschreibt nicht die Betreiber-Ollama-Konfiguration.
- Exakte Bedienung, Erweiterungs-ID und Rollback in `INSTALL.md`.
- Noch **nicht** live auf Windows ausgeführt. Notwendig: Betreiber startet Launcher, fügt Sitzungstoken in Brave ein, lädt die Erweiterung und den ChatGPT-Tab neu, erzeugt neue abgeschlossene Antwort mit eindeutiger NAS-Aufforderung und bash-Block `zpool status`, prüft Anzeige der gespeicherten Ollama-Suggestion.
- Die vom Betreiber bestätigten 38/38 Live-Benchmark-Treffer auf Stand `9fa3cfe` gelten für Modellklassifikation, nicht für die Browser-Ende-zu-Ende-Integration.

## Brave-Smoke-Befund: no_completed_reply_or_generation_active
- Echte Brave-Vorschau am 23.11.: Worker verbunden, Profil `local`, aber 0 Ollama-Analysen. Beim manuellen Prüfen der vorhandenen Antwort meldet der Content-Script-Guard `no_completed_reply_or_generation_active`. UI zeigte `GENERATING`, obwohl eine sichtbare Antwort vorlag. Das beweist **noch nicht**, ob ein verborgenes Stop-Control oder eine andere veraltete DOM-Zuordnung ursächlich ist.
- Gezielte Härtung: `BridgeCore.activeStop(document)` akzeptiert nur sichtbare, nicht deaktivierte Stop-Controls. Sichtbarkeitsänderungen an `class`, `style`, `hidden`, `aria-hidden`, `disabled` lösen über den MutationObserver einen neuen Scan aus. Der Abschluss benötigt weiterhin eine vorher tatsächlich beobachtete Stop-Phase, letzten Assistant-Turn und stabilen unveränderten Antworttext. Manuelle Übernahme prüft nach 700 ms erneut auf aktiven Stop und unveränderten Text.
- Diagnose ergänzt `rawStopMatches` zusätzlich zu `stopDetected`. So lassen sich versteckte Treffer und echte Stop-Controls bei erneutem Brave-Test unterscheiden.
- Node-Regressionen für sichtbare und versteckte Stop-Controls. **Echter Windows-Brave-Retest offen**. Bei wiederholtem Fehler: Panel `DOM-Diagnose` kopieren (ohne Nachrichtentext/Token), besonders `rawStopMatches`, `stopDetected`, `lastRole`, `assistantCount` und `stopProbe`. Nicht durch unbedingten Timeout-Fallback ersetzen.

## Phase 2A: Benutzerfrage an konkreten Antwortturn binden (2026-11-23)
- Realer Brave-Befund: `live_captures=2`, `ollama_suggestions=0`, `live_proposals=0`. Beide Übertragungen bestätigt, keine Fehler im Capture-Transport; reine Codeblock-Antwort enthält keine Ausführungsabsicht bzw. expliziten Zielalias. Der bislang fehlende Benutzerkontext erklärt plausibel die abgelehnte Klassifikation. Die genaue Modellentscheidung für die historischen Antworten wurde nicht persistiert.
- `BridgeCore.userPromptBefore(doc, assistant)` liest **nur den unmittelbar vor diesem konkreten Assistant-Turn stehenden** User-Turn aus DOM-Reihenfolge, maximal 8192 Zeichen; kein späterer Nutzertext, kein offener Editor und keine abgeschnittenen Prompts.
- `extension/content.js` übermittelt `user_prompt` sowohl bei automatischer als auch bei bewusst manueller Übernahme; manuelle Übernahme prüft nach Stabilisierung, ob Benutzerfrage und Antwort unverändert zum selben Turn gehören.
- `worker.live_capture_api.Capture` akzeptiert das optionale, begrenzte Kontextfeld. Derselbe `message_id` mit geändertem Kontext wird durch die gebundene Inhaltsidentität verweigert. Nur Inhalts-Hash, keine Benutzerfrage im Klartext in der LIVE-SQLite.
- `OllamaAnalyzer.analyze(..., user_prompt=...)` setzt die Frage als untrusted Kontext zur untrusted Assistant-Antwort. **Befehle müssen unverändert aus vollständigen Codeblöcken der Assistant-Antwort stammen**; Befehle aus der Frage sind nie übernehmbar. Fehlt der Host oder widersprechen sich Hostnamen in Frage/Antwort, bleibt das Ziel `None` und es wird kein LIVE-Proposal erstellt.
- Reparatur expliziter Host-Aliasgrenzen: `[\\w-]` statt fehlerhaft doppelt escaptem Word-Character-Pattern. Regressionen für zusammengesetzte Namen und getrenntes Backup-NAS.
- Historische Antworten können nicht nachträglich klassifiziert werden, da die vollständigen Texte absichtlich nicht in der SQLite gehalten werden. **Für die Live-Abnahme muss nach Worker-Neustart und Extension-Reload ein neuer ChatGPT-Turn mit neuem `message_id` erzeugt werden.**
- Nachweisbare funktionale Verifikation: GitHub-Actions Python/Node-Tests; realer Windows-Brave- und qwen3.5:4b-Test mit gepaarter Benutzerfrage noch offen. Kein SSH, Auto-Approval oder Auto-Send.

## Diagnose nach realem Windows-Ollama-Test (2026-11-23)
- Operator bestätigt: `live_captures=4`, `ollama_suggestions=0`, `live_proposals=0`. Direkter Ollama-API-Aufruf mit `qwen3.5:4b` erfolgreich (`{"status":"ready"}`, 0,13 s). Damit ist der lokale Modellserver grundsätzlich funktionsfähig; die konkreten Capture-Klassifikationen bleiben unklar.
- Neue `ollama_diagnostics`-Tabelle speichert für künftige Captures nur Message-ID, Chat-/Tab-ID, Diagnosezustand (`no_shell_blocks`, `classified_nonactionable`, `target_unresolved`, `proposal_ready`), Boolean `user_prompt_present`, Zahl der erkannten Shell-Blöcke und Modellname. Keine Prompttexte, Assistant-Antworten, Tokens oder rohe Qwen-Ausgaben.
- Neue durch Bearer-Token geschützte read-only API `GET /api/bridge/v1/ollama/diagnostics`, maximal 20 neueste Ergebnisse. Alt-Captures werden nicht rückwirkend rekonstruiert.
- Mit diesen Metadaten lässt sich bei der nächsten neuen Capture eindeutig unterscheiden, ob der DOM-Reader keinen Codeblock übertrug, die Userfrage nicht zugeordnet wurde oder die Klassifikation den Befehl ablehnte.
