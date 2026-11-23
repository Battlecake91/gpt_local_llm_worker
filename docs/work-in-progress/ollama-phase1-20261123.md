# Ollama-Analyse normaler ChatGPT-Antworten (2026-11-23)

## Scope und Branch
- Branch: `feature/brave-chat-bridge`
- Ziel: Klassifikation normaler ChatGPT-Antworten in überprüfbare interne SSH-Vorschläge, weiterhin ohne SSH-Ausführung und ohne Browser-Auto-Send.
- Ursprung: Entwicklungsauftrag für Ollama/Brave/SSH, Phase 1.
- Ausgangs-HEAD: `b27606887f91af887f27f6813aa83f5fbb1ef742`.

## Umgesetzt
- `worker/ollama_analysis.py`: Profile für Windows-Ollama, NAS und zusätzliche konfigurierte Hosts, validierte Konfiguration, HTTPX-Anbindung mit JSON-Modus, optionaler Bearer-Token ausschließlich aus Worker-Umgebung, Risiko-/Hostbewertung.
- Extraktion ausschließlich kompletter vorhandener `bash`, `sh`, `shell` oder `console`-Codeblöcke. Kein Hinzufügen, Kürzen oder Ersetzen durch das LLM. Kein Codeblock bedeutet keinen LLM-Aufruf. Nicht erkannter Host erzeugt keinen LIVE-Proposal.
- `worker/live_capture_api.py`: Opt-in mit `--ollama-profiles`, deduplizierte Erfassung und transaktionale Ablage von unveränderlichem LIVE-Vorschlag und separat gespeicherter LLM-Risikoeinschätzung. Ohne Opt-in bleibt alter JSON-Parser unverändert verfügbar.
- Authentifiziert: `GET /api/bridge/v1/ollama/profiles`, `POST /api/bridge/v1/ollama/select`, `GET /api/bridge/v1/ollama/suggestions`. Profilwechsel ohne Prozessneustart.
- Bewusst **nicht** gekoppelt: freie LLM-Einstufung zu automatischer Freigabe, SSH-Executor, Sudo oder Rückkanal.
- Neue Offline-Fälle in `tests/test_ollama_analysis.py`, zusätzlich CI-Workflow für Python/Node-Regressionssuiten.

## Integration
Eine Vorlage liegt in `config/ollama-profiles.example.json`. Für die Verwendung eine lokale Kopie außerhalb des Git-Repositories anlegen und mit `--ollama-profiles ABSOLUTER_PFAD` starten. `auth_env` ist der Name einer lokal gesetzten Umgebungsvariablen für das Profil-Token, niemals das Token selbst.

Die vorhandene LIVE-API bleibt explizit separat und standardmäßig ohne Ollama. Konfigurationsfehler verhindern den Start; LLM-Fehler verhindern die Annahme eines daraus abzuleitenden Auftrags (HTTP 503). Nur vollständig validierte interne Batches können in `live_proposals` gelangen. Resultate aus `ollama_suggestions` werden noch nicht im Brave-Seitenpanel angezeigt.

## Einschränkungen
- Fenced Shell-Codeblöcke werden blockweise, nicht zeilenweise extrahiert. Nicht gefencete Befehle sind noch nicht unterstützt; das vermeidet unsichere Kommandorekonstruktion.
- Modellbewertung ist keine verlässliche Sicherheitsentscheidung, insbesondere bei Beispieltext. Keine automatische Freigabe in Phase 1.
- Profilkonfiguration ist vom lokalen Betreiber zu schützen; Profilauswahl über bestehende Token-API beschränkt sich auf bereits konfigurierte Endpunkte.
- Keine live Ollama-/Windows-/Brave-Tests und keine echten SSH-Verbindungen. Die CI-Ausführung muss nach Repo-Push separat bestätigt werden; Testdateien sind angelegt, aber keine bestandenen Tests behauptet.
- WIP in den nächsten Phasen: Profil-/Modellwahl im Panel, Modellabfrage und Verbindungstest, nicht gefencete eindeutige Befehle, robustere Beispiel-/Zitatklassifikation, Ampel-UI und Zielkorrektur, separate Freigabe- und Sudo-Logik.

## Testbefehle
```powershell
py -m pip install -e ".[test]"
py -m pytest -q tests/test_ollama_analysis.py tests/test_live_capture_api.py
py -m pytest -q
node --test tests/*.cjs
```
