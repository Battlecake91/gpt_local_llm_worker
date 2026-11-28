# Active Chat GUI: Phase 1 (2026-11-28)

## Ziel und Abgrenzung
- Nur explizit aktivierte **offene** ChatGPT-Tabs in Brave/Chrome synchronisieren.
- Browser-Erweiterung liest sichtbare User- und Assistant-Turns mit Codeblöcken und liefert sie an eine lokale Python-Anwendung.
- PySide6-Desktop-GUI zeigt parallele Chats und den übertragenen Nachrichtentext.
- **Kein Ollama, keine SSH-Ausführung, kein Auto-Send, keine GitHub-Aktionen** in Phase 1.
- Isoliert von Legacy-Bridge (`extension/`) und deren Port 8765. Neuer Port: 8766.

## Implementiert
- `extension-active/`: neue MV3-Erweiterung, Popup statt Sidepanel; Token-Eingabe und Aktivierung des aktuell geöffneten Chat-Tabs.
- Aktivierung in `chrome.storage.session`: Bindung an **Tab-ID und Chat-Konversations-ID**. Browser-Neustart soll nicht automatisch aktivieren.
- Content-Script gibt kontinuierliche Snapshots aller aktuell im DOM sichtbaren Messages aus. Regelmäßiger Abgleich auch ohne DOM-Events.
- Weitergabe nur wenn Tab aktiviert und Konversation identisch. Tab-Schließung und Navigation entfernen die Aktivierung. Bei Transferproblemen wird ein Folgesnapshot erneut versucht.
- `src/worker/chat_sync.py`: FastAPI über Loopback, token- und Origin-Prüfung, SQLite-Snapshot-Store, begrenzte Nachrichtenzahl und Textgrößen.
- `src/worker/chat_sync_gui.py`: PySide6-GUI, zeigt Nachrichten je Chat, 1,5-s Aktualisierung, Kopierbutton für zufällig erzeugtes Session-Token.
- Neue `gui`-Extra-Abhängigkeit in `pyproject.toml`, Python-API-Regressionstests.
- Store speichert Texte lokal **im Klartext** in SQLite, keine Übertragung an externe Dienste; dies ist für spätere Ollama-Analyse vorgesehen und muss vor produktivem Einsatz datenschutzseitig geprüft werden.

## Installation und Live-Test unter Windows
Im Repository:

```powershell
git fetch origin
git switch feature/active-chat-gui-20261128
git pull --ff-only
py -m pip install -e ".[gui,test]"
py -m worker.chat_sync_gui --extension-id laogocebnhllcalglgakemfeadmheppo
```

1. Brave: `brave://extensions` → Entwicklermodus → **Entpackte Erweiterung laden** → Ordner `extension-active`. Bestehende alte Bridge besser deaktivieren, aber nicht löschen (sie läuft unabhängig).
2. **Wichtig:** Die neue Erweiterung erhält eine **eigene Erweiterungs-ID**. Wird sie aus einem anderen Ordner geladen, ist die ID nicht zwingend identisch mit der bisherigen. Tatsächliche ID von `brave://extensions` verwenden und die GUI mit **dieser** ID starten.
3. In der GUI auf **Bridge-Token kopieren** klicken, in das Popup der neuen Erweiterung eintragen → **Speichern**.
4. In einem geöffneten ChatGPT-Chat im Popup **Aktivieren**. Erst dann werden dessen sichtbare Nachrichten an die GUI übertragen.
5. Mehrere ChatGPT-Tabs getrennt aktivieren. Die GUI zeigt die Nachrichtentexte je Tab und aktualisiert sich laufend.
6. Deaktivieren oder Tab schließen stoppt die Synchronisierung. Bei ausbleibenden Snapshots zeigt die GUI den Tab nach 18 s als nicht erreichbar.
7. Alte Bridge auf 8765 ist für diese Phase nicht erforderlich. Keine SSH-Freigaben und keine Ollama-Konfiguration.

Abnahme: Nur aktivierte Tabs erscheinen, User- und Assistant-Nachrichten stimmen inklusive Codeblöcken; parallele Tabs bleiben getrennt; Tab-Wechsel, Reload und Schließen stoppen bzw. aktualisieren die Überwachung. Browser-Live-Nachweis ausstehend.

## Grenzen und offene Punkte
- Nur **im DOM vorhandene** Nachrichten werden erfasst. ChatGPT kann lange Unterhaltungen virtualisieren. Das ist keine Zusage über vollständige historische Chats, auch wenn viele alte Turns sichtbar sind.
- Das Feld `complete` ist in Phase 1 lediglich ein UI-Indikator aus Stop-Button und zwei stabilen Abtastungen, **keine Autorisierung für Aktionen**. Ein stärkerer Abschlussnachweis wird vor dem LLM-Task-Trigger nötig.
- Bei UI-Änderungen von ChatGPT sind DOM-Selektoren erneut zu testen.
- SQLite hält die zuletzt empfangenen Snapshots auch nach Ablauf eines Tabs vor; die GUI markiert solche Tabs als nicht erreichbar. Automatische Datenlöschung als Folgefeature entscheiden.
- Die aktuelle GUI ist ein Fenster mit lokalem API-Thread, noch kein separat betriebener Tray-Dienst.
- Bei GUI-Neustart wird ein neues zufälliges Token generiert. Im Browser-Popup erneut speichern.
- Benutzer-Aktionen und Rückmeldungen in ChatGPT bewusst noch nicht implementiert.

## Prüfungen
- GitHub Actions Workflow `tests.yml` für neuen Branch erweitert.
- `py -m pytest -q tests/test_chat_sync.py`
- `py -m pytest -q`
- `node --test tests/*.cjs`
- Live-Abnahme Windows/Brave/PySide6 ausstehend.

## Nächster Schritt
Realen Browser- und GUI-Abgleich durchführen, DOM-Lücken und Snapshot-Grenzen prüfen, dann LLM-Modul auf Chat-Snapshots ansetzen und taskbasierte Benachrichtigungen bauen. SSH bleibt separat.
