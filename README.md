# NX API — Live-Scripting-Toolkit für Siemens NX

Werkzeuge, um Siemens NX aus einem LLM/Agenten heraus **live in einer sichtbaren
Sitzung** zu steuern: NX lädt beim Start selbst einen Dispatcher, Jobs vom Mac
werden auf dem NX-Main-Thread in der GUI-Sitzung ausgeführt, Ergebnisse kommen
zurück.

Erste Anwendung: [`10_Online_Machining`](../10_Online_Machining) — dort entstand
dieser Code, und dort läuft er verifiziert. Dieses Verzeichnis ist die
herausgelöste, wiederverwendbare Ebene darunter.

Hintergrund, Recherchestand und Bewertung der Alternativen (NX Remoting,
`#nx: threaded`, öffentliche MCP-Projekte):
[`docs/nx-live-scripting-handoff.md`](docs/nx-live-scripting-handoff.md).
Der verifizierte Aufbau im Detail:
[`docs/nx-setup-verified.md`](docs/nx-setup-verified.md).
Der aktuelle validierte Stand in Kurzform:
[`docs/project-state.md`](docs/project-state.md).
Betriebs- und Sicherheitsregeln für Agenten:
[`AGENTS.md`](AGENTS.md).
Das destillierte Betriebswissen als Skill für Claude und GPT:
[`skills/nx-live-scripting/`](skills/nx-live-scripting/SKILL.md).
Die Sequenzen, die tatsächlich gelaufen sind — und die Wege, die belegt nicht
funktionieren:
[`skills/…/references/api-modelling.md`](skills/nx-live-scripting/references/api-modelling.md)
und [`api-drafting.md`](skills/nx-live-scripting/references/api-drafting.md).
Die deklarative High-Level-Oberfläche vor dem eigenen Job-Code:
[`high-level-tools.md`](skills/nx-live-scripting/references/high-level-tools.md).

## Was hier liegt

Die Ordner sind nach dem **Datenfluss** nummeriert: vom Mac (`01`) über den
Dispatcher in NX (`02`) zu dem, was dort ausgeführt wird (`03`); `04` ist das
Nachschlagewerk beim Schreiben von Jobs.

```
01_host/                      Mac-Seite: alles wird von hier aus angestoßen
  nx_bridge_install.py        Dispatcher bauen, sichtbares NX starten
  nx_remote.py                Job archivieren und hochladen (+ Batch-Pfad), lintet vorher
                              (`--toolkit-job` für feste Runner aus diesem Toolkit)
  nx_lint.py                  Statische Vorab-Pruefung eines job.py (Imports, Tolerance, main-Signatur)
  nx_dispatch.py              Jobs einreihen, Status, Stop
  nx_visible.py               NX starten, Ergebnisse einsammeln
  nx_plan.py                  deklarativen High-Level-Plan validieren + einmal ausführen
  nx_mcp_server.py            ein MCP-Tool `nx_run_plan` über denselben Plan-Executor
02_bridge/                    NX-Seite: der Dispatcher, den NX beim Start lädt
  VisibleBridge.cs            Queue-Polling auf dem NX-Main-Thread, über ufsta
  start-visible.cmd           Launcher, setzt DOTNET_ROOT für x64-NX auf ARM64-VM
03_jobs/                      Was in der Sitzung läuft: Python mit main(job_dir)
  probe.py                    Minimaler Smoke-Test (Batch)
  visible_probe.py            Smoke-Test in der sichtbaren Sitzung
  live_demo.py                Schrittweiser Aufbau mit Undo-Marks, zum Zuschauen
  acceptance.py               Fähigkeitstest: Körper → Zeichnung → Toleranz → PDF
  feature_reedit_probe.py     Öffnet jedes Feature erneut — findet Builder-Defaults,
                              die erst beim Doppelklick auffallen
  part_open_probe.py          Liest NX' Ladestatus im Klartext, wenn ein Teil
                              nicht mehr öffnet
  probes/                     Archivierte Belege hinter den Layer-4-Dateien
  nx_high_level_plan.py       zertifizierte High-Level-Operationen in einem atomaren Job
04_reference/                 Nachschlagen beim Schreiben von Jobs
  nx_api_lookup.py            Substring-Suche in NXOpen.xml
  NXOpen.xml                  API-Doku aus der eigenen Installation (gitignored)
  nxopen_python_ref/          Lokaler Spiegel der öffentlichen Python-Doxygen-Referenz (gitignored)
  mirror_nxopen_python_ref.py Aktualisiert diesen lokalen Spiegel
docs/                         Aufbau, Belege, Recherchestand
skills/nx-live-scripting/     Der Skill für Claude Code und Codex/GPT
runs/nx/<run-id>/             Erzeugt: archivierte Source, Manifest, Ergebnisse
examples/                     sichere, validierbare High-Level-Beispielpläne
```

## Der Kern in drei Sätzen

NX lädt managed Assemblies aus dem `startup`-Ordner eines in
`UGII_CUSTOM_DIRECTORY_FILE` gelisteten Verzeichnisses und ruft dort `ufsta`
(Rückgabetyp **muss** `int` oder `string` sein). Der Dispatcher pollt von dort
eine Datei-Queue auf einem `System.Windows.Forms.Timer`, wodurch jeder NX-Call
auf dem Thread landet, auf dem NX ihn gestartet hat — kein Socket, kein
Hintergrund-Thread mit NX-API. Jobs sind Python (`job.py` mit globaler
`main(job_dir)`), ausgeführt über `Session.Execute`, hash-geprüft und auf das
Projektverzeichnis beschränkt.

Warum nicht `USER_STARTUP`, nicht `run_journal.exe`, nicht
`JournalManager.PlayDotNetJournal` und nicht NX Remoting: siehe die beiden
Dokumente unter `docs/`.

## Status: verifizierte Bridge plus deklarative High-Level-Schicht

Die Bridge stammt unverändert aus `10_Online_Machining` und läuft dort
verifiziert (Run `20260905T211411Z-4db4f56d`, sichtbare Desktop-Session 1).
Darüber liegt inzwischen eine eigene deklarative High-Level-Schicht:
`nx_run_plan` bündelt eine kleine zertifizierte Operationsmenge in einem
validierten, einmal eingereihten NX-Job. Eigenen NXOpen-Code schreibt der Skill
erst, wenn diese Schicht und die verifizierten Low-Level-Snippets nicht reichen.
Die VM-seitige Dispatcher-Assembly wurde dafür nicht verändert.
Konkret sind das ein registriertes MCP-Tool und 16 interne Planoperationen;
Contract v2 ergänzt Status, evidence-sicheres Open/Close, planlokales Undo und
den verifizierten STEP-AP214-Translator.

Die projektgebundenen Namen stecken deshalb noch im Code und sind Aufgabe 1:

| Stelle | steckt drin |
| --- | --- |
| `02_bridge/VisibleBridge.cs:27-28` | `ONLINE_MACHINING_ROOT`, Default-Ordner `OnlineMachiningNX` |
| `02_bridge/start-visible.cmd:8` | `ONLINE_MACHINING_ROOT` |
| `01_host/nx_bridge_install.py:33,35` | Task-Name `OnlineMachining-NX-Bridge` |
| `01_host/nx_visible.py:22,23` | Task-Name `OnlineMachining-NX-Interactive` |
| `01_host/nx_remote.py:13` | harter Pfad `C:/Users/hanne/Documents/OnlineMachiningNX` |

Sinnvoll: ein `NX_BRIDGE_ROOT` mit `ONLINE_MACHINING_ROOT` als Fallback, damit
die bestehende Installation weiterläuft, während neue Projekte den generischen
Namen benutzen. Erst umstellen, dann in `10_Online_Machining` gegen einen echten
Lauf prüfen.

## Offene Arbeit

Siehe Abschnitt „Tool-bezogene Optimierungen" im
[Handoff](docs/nx-live-scripting-handoff.md). Größter Hebel bleibt 9.2: der
Rückkanal fürs Auge (Viewport-Bild/PDF mit einsammeln), damit der Agent sieht,
was er gebaut hat.
