# Projektstand 08_NX_API

Kurzfassung des validierten Stands. Details und Herleitung stehen in den
verlinkten Dokumenten; diese Datei nennt nur, was beobachtet/validiert vs.
geplant ist.

## Zweck

Wiederverwendbare Live-Scripting-Ebene unter `10_Online_Machining`: sichtbare
NX-Sitzung per Dispatcher steuern, Jobs als Python-Files shippable, Results
einsammelbar. Ordner nach Datenfluss: `01_host/` → `02_bridge/` → `03_jobs/`,
`04_reference/` zum Nachschlagen.

## Beobachtet / validiert (Stand 2026-09-12)

- Deklarative High-Level-Schicht für neue einfache Extrusionsmodelle:
  `01_host/nx_plan.py` (Schema, Sicherheit, Orchestrierung), ein MCP-Tool
  `nx_run_plan` und `03_jobs/nx_high_level_plan.py` auf lokal verifizierten
  NXOpen-Rezepten. Entscheidung und Fallback stehen in
  [`high-level-tools.md`](../skills/nx-live-scripting/references/high-level-tools.md).
- Vollständige sichtbare MCP-stdio-Abnahme: Run
  `20260912T113647Z-60d37433`, `nx_run_plan` → MCP-Server → Host-Executor →
  Queue → sichtbares NX. `bridge-execution.json`: `execution_ok: true`, PID
  10924, Desktop-Session 1, Main-Thread 1, passender Source-SHA-256;
  `result.json`: neun erfolgreiche Schritte, XZ-Skizze mit vier Linien,
  Extrude mit einem Körper, vier Features, Fit und Save.
- Historischer v1-Produktionsvertrag im echten sichtbaren NX verifiziert: Run
  `20260912T185302Z-9cb4c6ea`; Host und statischer NX-Runner melden beide
  `contract_version: 1`, alle neun Planoperationen sowie Bridge-Hashprüfung
  erfolgreich. Bereits dort bezog das MCP-Schema seine damaligen elf
  Operationsnamen aus derselben Registry wie der Host-Validator und markierte
  den Aufruf als verändernd und nicht idempotent.
- Contract v2 deckt alle 16 zertifizierten DreamEnding-Namen innerhalb des
  weiterhin einzigen MCP-Tools ab. Sichtbare Abnahme: Status-only mit
  `nx_version: v2506` `20260912T194649Z-7524295e`; planlokales Undo plus STEP AP214
  `20260912T193745Z-9989edc7` (8.230 Byte, sechs Flächen, ein Closed Shell);
  gehashte Input-Kopie öffnen, einen Body listen, ohne Save schließen und
  Status prüfen `20260912T194302Z-c723423b`. Alle Bridge- und Job-Ergebnisse
  sind grün.
- Der vorherige sichtbare MCP-Run `20260912T113535Z-db64f032` fand die
  Live-Session-Kollision gleicher Part-Blattnamen trotz verschiedener
  Run-Verzeichnisse (`NXException 1020004`). Der Runner versieht den echten
  Dateinamen deshalb zwingend mit der Run-ID; der fehlgeschlagene Run wurde
  nicht resubmitted.
- Ergänzende reale NX-API-Abnahme im Batch-Fallback: Run
  `20260912T104646Z-82000717`, `ok: true`, eingesammeltes `.prt` 71.682 Byte.
  Diagnose-Run `20260912T104553Z-5eeb703b` belegte den Modell-Rollback nach
  Teileerzeugung (`rollback.ok: true`).
- Vierzehn lokale Tests prüfen Schema/Defaults, Pfad-Confinement,
  Tool-Allowlist mit exakt 16 Namen, Undo-Zustand, terminale Operationen,
  Input-Hash/Archivierung, Bridge-Gate, Exactly-once-Submit und die
  Ein-Tool-MCP-Oberfläche. Der NXOpen-Linter meldet 0 Fehler/0 Warnungen.

- Sichtbarer Pfad Ende-zu-Ende lauffähig (Details: [nx-setup-verified.md](nx-setup-verified.md)):
  Run `20260905T211411Z-4db4f56d`, drei Features mit Undo-Marks, NX-PID 13032, Desktop-Session 1.
- Batch-Pfad verifiziert: Run `20260905T201118Z-44b7601a`, Kontur + Toleranzzeichen, 14081-Byte-PDF.
- Code identisch aus `10_Online_Machining` übernommen, nur Ordnernamen (`01_host/` …) und Pfadverweise umbenannt. VM-Seite unberührt.
- `~/.claude/skills/nx-live-scripting` ist ein **Symlink** auf
  `skills/nx-live-scripting` in diesem Repo — es gibt keine zweite Kopie und
  keinen Deploy-Schritt. Folge: **der ausgecheckte Branch ist der aktive
  Skill.** Auf einem Feature-Branch gearbeitete Skill-Änderungen sind sofort
  live; ein Wechsel zurück auf `main` vor dem Merge nimmt sie wieder weg.

### Aus dem Prüfkörper-Lauf am 2026-09-06 (Quelle: `10_Online_Machining/cad/README.md`)

Erste vollständige Nutzung über eine reine API-Aufgabe hinaus: Modell aus
Skizzen, Gewindebohrung mit Normdaten, Zeichnung aus Firmenvorlage, STEP AP214.
Was dabei belegt wurde, steht in
[api-modelling.md](../skills/nx-live-scripting/references/api-modelling.md) /
[api-drafting.md](../skills/nx-live-scripting/references/api-drafting.md);
jede Aussage dort nennt den Probe-Job, der sie stützt.

- **Ursache für „Tolerance error" beim Wiederöffnen eines Revolve gefunden:**
  `RevolveBuilder.Tolerance` ist per Vorgabe 0,0. Belegt in
  `revolve_tolerance_probe.py`; Profilform und vier Achskonstruktionen vorher
  als Ursache ausgeschlossen. Gleiches Muster bei
  `HolePackageBuilder.Tolerance` mit irreführender Meldung.
- **Skizze auf einer Datum-Ebene:** `PlaneReference` wird ignoriert, wirksam ist
  `PlaneOption = Inferred` + `PlaneOrFace.Value` (`sketch_plane_probe.py`).
- **Gewinde:** `ThreadBuilder` nimmt kein Gewinde auf einer gedrehten Bohrung an
  (24 Kombinationen geprüft, `thread_probe.py`); der Weg ist
  `HolePackageBuilder` mit `Types.ThreadedHole` (`hole_probe.py`). Normdaten
  sind installiert, der Schlüssel lautet `M6 x 1.0`, nicht `M6 x 1` — der
  frühere Befund „fehlende Normdaten" war falsch.
- **Blattvorlage ohne Adminrechte:** `SheetOption.UseTemplate` mit vollem Pfad;
  danach zwingend `Drafting.SetTemplateInstantiationIsComplete(True)`, sonst
  wird das gespeicherte Teil korrupt (einmal reproduziert).
- **Bemaßung:** Durchmesser in der Längsansicht brauchen zweimal die
  Mantelfläche mit `OnCurve`; ISO-Passungen über `ToleranceType.LimitsAndFits`;
  Probemaße aus einer Suche müssen wieder gelöscht werden.
- **Zwei generische Diagnose-Jobs neu in `03_jobs/`**, beide am Prüfkörper
  gelaufen: `feature_reedit_probe.py` (zwölf Features, null Fehlschläge) und
  `part_open_probe.py` (liest den Ladestatus im Klartext, hat
  „Corrupt data found when loading an OM file" identifiziert).
- **Host-Tools:** `nx_remote.py` und `nx_visible.py` lesen `result.json` jetzt
  auch in cp1252 — NX' eingebettetes Python schreibt ohne explizites
  `encoding='utf-8'` in der Windows-Codepage.

## Bekannte Grenzen (validiert, nicht geraten)

- Zeichnungsableitung, zwei belegte Lücken aus dem Prüfkörper-Lauf:
  `SectionViewBuilder` schneidet aus der API heraus längs statt quer
  (Schnittlinienpunkte und Ablagerichtung ändern daran nichts,
  `ViewPlacementBuilder.Method` ist nur lesbar), und es gibt keine assoziative
  Bemaßung auf den Scheitel eines Zylinders — alle fünf Punktoptionen liefern
  Achsabstände. Folge im Prüfkörper: kein Querschnitt, Nuttiefe als Angabe
  statt als Maßlinie.
- Projektgebundene Namen stecken noch im Code (`ONLINE_MACHINING_ROOT`, Task-Namen, harter Pfad `C:/Users/hanne/Documents/OnlineMachiningNX`) — siehe Tabelle im [README](../README.md).
- Kein visueller Rückkanal: Job liefert nur `result.json`; Viewport-Bild/PDF wird nicht mit eingesammelt (Handoff-Punkt 9.2).
- API-Suche nur Substring auf Member-Namen; .NET-Signaturen ≠ Python. Lizenz-/Deprecation-Treffer müssen manuell geprüft werden (Handoff-Punkt 9.3).
- Timer 1000 ms + mehrere SSH-Runden ≈ 4 s Poll-Anteil an ~7 s pro Auftrag (Handoff-Punkt 9.5).
- High-Level-v2 deckt zwar alle 16 DreamEnding-Namen ab, bleibt geometrisch
  absichtlich schmal: XZ-Skizze, Linien/Rechteck und neue Extrusion. Neue und
  geöffnete Teile sind Run-Kopien mit Run-ID; `nx_open_part` archiviert und
  prüft zusätzlich den Input-Hash. Undo reicht nur innerhalb desselben Plans.
  Save, Close und STEP sind terminal, weil persistierte Dateien nicht über eine
  NX-Modellmarke zurückgerollt werden können.

## Geplant (nicht begonnen)

1. Generalisierung `NX_BRIDGE_ROOT` mit `ONLINE_MACHINING_ROOT`-Fallback, danach echter Lauf gegen `10_Online_Machining` (Handoff 9.1).
2. Rückkanal fürs Auge (Handoff 9.2) — größter Hebel.
3. .NET→Python-Mapping-Regeln + verifizierte Beispiele indexieren, erst dann Embedding-Index (Handoff 9.3).
4. Dispatcher auf `managed_core`/net8 nur bei NX-Upgrade oder wenn ohnehin angefasst (Handoff 9.4, heute nicht anfassen).
5. Nächste eigene High-Level-Kandidaten gemeinsam priorisieren: Revolve,
   Gewindebohrung und Solid-Messung sind am reifsten; Drawing-Sheet/Base-View/
   PDF mechanisch ebenfalls, aber mit strengem Regel-/Validation-Gate. Noch
   nicht implementiert; nach gemeinsamer Entscheidung als eigener Scope.

## Geschlossen

- **Erste echte Konstruktionsaufgabe über den Skill gefahren** (Prüfkörper:
  Modell, Zeichnung, STEP), inklusive Nachmessen am Volumenmodell und
  Soll-/Ist-Prüfung jedes Maßes im Job. Ergebnis und offene Entscheidungen des
  Bauteils selbst: `10_Online_Machining/cad/README.md`.
- **Erste Hälfte von Issue #3** (verifizierter Python-Code vor .NET-Signatur):
  als handgeschriebene Rezeptsammlung geliefert, nicht als Index. Der Index
  bleibt offen.

## Repo / laufende Arbeit

- Remote (privat): https://github.com/hanneskoenig457/nx-live-scripting
- Issue #1: Generalisierung `NX_BRIDGE_ROOT` (Handoff 9.1).
- Issue #2: Rückkanal fürs Auge (Handoff 9.2).
- Issue #3: API-Retrieval + .NET→Python-Mapping (Handoff 9.3) — erste Hälfte
  geliefert, Index offen.
- Issue #4: Zeichnungsableitung, die beiden belegten Lücken oben.
- Issue #6: High-Level-NX-Toolplan vor Low-Level-Jobs — geschlossen.
- Issue #7: Erweiterung auf alle 16 DreamEnding-Namen — implementiert, mit
  14 lokalen Tests und drei sichtbaren v2-Abnahmen verifiziert.
- Kein Project-Board (erst bei mehreren aktiven/blockierten/übergebenen Issues).

Herleitung und Alternativenbewertung: [nx-live-scripting-handoff.md](nx-live-scripting-handoff.md).
Betriebsregeln: [../AGENTS.md](../AGENTS.md).
