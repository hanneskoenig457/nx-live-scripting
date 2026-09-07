# AGENTS.md — 08_NX_API

Betriebs- und Sicherheitsregeln für Agenten in diesem Toolkit-Repo.
Ausführliche Verfahren stehen im Skill unter `skills/nx-live-scripting/`;
hier nur die verbindlichen Leitplanken für dieses Verzeichnis.

## Run order (immer vom Projektroot, Host-Python `.venv/bin/python`)

```sh
.venv/bin/python 01_host/nx_dispatch.py status                 # immer zuerst
.venv/bin/python 01_host/nx_bridge_install.py                  # nur wenn nicht ready
.venv/bin/python 01_host/nx_remote.py <job>.py --prepare-only  # archiviert + lädt hoch, druckt run-id
.venv/bin/python 01_host/nx_dispatch.py submit --run <run-id> --wait 90
.venv/bin/python 01_host/nx_visible.py collect --run <run-id>
```

- `status` muss `ready`, `session_id != 0` und frischen Heartbeat zeigen, sonst nicht fortfahren.
- Ein Run wird exakt einmal submitted. Ein `--wait`-Timeout bricht nichts ab und erlaubt keine Resubmission — State einsammeln und lesen.
- Nach `collect` beide Dateien prüfen: `bridge-execution.json` (Dispatcher hat die gehashte Source ausgeführt) und `result.json` (einzige Aussage über inhaltliche Richtigkeit).
- Sichtbare Sitzung ist Default (Zuschauen ist der Zweck). Batch-Pfad ohne `--prepare-only` nur für unbeaufsichtigte Reruns oder wenn sichtbar nachweislich fehlt — Wechsel explizit benennen (Drafting-View-Trap, siehe `skills/nx-live-scripting/references/operations.md`).

## Job-Regeln (`03_jobs/`, Vorlage `skills/nx-live-scripting/assets/job-template.py`)

- Globales `main(job_dir)`, schreibt `result.json` nach `job_dir` — sonst kein Nachweis.
- Keine Exception entkommen lassen (NX antwortet mit modalem Dialog, Dispatcher stallt). Alles fangen, in `result.json` berichten.
- Part-Namen pro Run eindeutig wählen (Session überlebt Jobs, `NewDisplay` scheitert bei Namensgleichheit).

## API nachschlagen, nicht erinnern

- `04_reference/nx_api_lookup.py` vor jedem Call befragen; Treffer auf Lizenz-Requirements und Deprecation-Hinweise prüfen (schlagen sonst erst zur Laufzeit fehl).
- `.NET`-Signaturen aus `NXOpen.xml` ≠ Python: `skills/nx-live-scripting/references/nxopen-python-notes.md` beachten. Verifizierter Python-Code aus gelaufenen Jobs schlägt übersetzte .NET-Signatur.
- Für ganze Aufgaben zuerst die passende Layer-4-Datei lesen: `skills/nx-live-scripting/references/api-modelling.md` (Geometrie) bzw. `api-drafting.md` (Blatt, Ansichten, Maße, Annotationen). Beide beginnen mit einer Index-Tabelle und enden mit den Wegen, die nachweislich nicht funktionieren. Bei Zeichnungsarbeit gilt: erst Regeln (`dimensioning-rules.md`, Layer 3), dann API. Teuerste Falle: mehrere Builder haben `Tolerance = 0.0` als Vorgabe, committen klaglos und scheitern erst später (Feature lässt sich nicht wieder öffnen, oder eine Fehlermeldung, die etwas anderes benennt).
- Funde während der Arbeit nach `skills/nx-live-scripting/FINDINGS-INBOX.md` schreiben und **vor Aufgabenende** in die passende Ebene einsortieren — die Datei ist zwischen Aufgaben leer.
- API-Erfolg ≠ visuelle Abnahme: PDF auf Kontur, Bemaßungs-Assoziation, Toleranzzeichen, Layout prüfen bzw. vom Job asserten lassen (`IsOutOfDate is False`, `AskVisibleObjects()` nicht leer).
- Maße im Job gegen ihren Sollwert prüfen (`dim.ComputedSize`) und beides berichten — eine falsch assoziierte Bemaßung liefert sonst eine plausible falsche Zahl.
- Bei zu knapper Ausnahme das NX-Syslog lesen (neueste `*.syslog` in `%TEMP%`); dort steht der eigentliche Fehlertext.

## Safety / Scope (verbindlich)

- Keine NX-Dialoge bedienen und kein Journal von Hand abspielen, während ein Job läuft (`IsJournalRunning` stallt die Queue).
- Laufende Jobs können nicht pausiert/abgebrochen werden — lange Aufbauten in kleine Jobs splitten.
- NX nicht ohne Rückfrage neu starten (lädt Dispatcher-Assembly fest), nie bei möglicher ungespeicherter Arbeit.
- Keinen Listening-Port öffnen; Transport ist die bestehende SSH/SCP-Verbindung. SHA-256-Check und Projektverzeichnis-Confinement nicht aufweichen.
- `04_reference/NXOpen.xml` (lizenzierte Vendor-Doku, ~56 MB) bleibt gitignored und geht an keinen externen Service.
- Keine Scheduled Tasks, Env-Variablen oder NX-Installation im Rahmen einer Engineering-Aufgabe ohne Autorisierung anfassen.
- `runs/nx/<run-id>/` ist generierte Evidence (archivierte Source + Manifest + Results) und wird nicht committet.

## Doku- und Arbeitsdisziplin (CAE Project Ops, minimal)

- `README.md` ist das Dashboard; `docs/project-state.md` der aktuelle validierte Stand. Stabile Docs (`docs/nx-setup-verified.md`, `docs/nx-live-scripting-handoff.md`) nicht stilistisch umschreiben, nur bei Wahrheits-/Navigationsänderung anfassen.
- Substanzielle Arbeit (sessions-übergreifend, Modell-/Workflow-Änderung, Validation-Gate, mehrere Akzeptanzkriterien) bekommt ein GitHub-Issue mit Kontext/Ziel, Scope/Non-Goals, Inputs, Akzeptanzkriterien, Dependencies, Doku-/Evidence-Pflicht. Kleines Housekeeping direkt per Commit.
- Skill-Quelle ist `skills/nx-live-scripting/` hier. `~/.claude/skills/nx-live-scripting` ist ein Symlink darauf — keine zweite Kopie, kein Deploy-Schritt, aber: **der ausgecheckte Branch ist der aktive Skill.** Skill-Änderungen auf einem Feature-Branch wirken sofort und verschwinden beim Wechsel zurück auf `main` vor dem Merge.
