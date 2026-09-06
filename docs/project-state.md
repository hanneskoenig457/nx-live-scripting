# Projektstand 08_NX_API

Kurzfassung des validierten Stands. Details und Herleitung stehen in den
verlinkten Dokumenten; diese Datei nennt nur, was beobachtet/validiert vs.
geplant ist.

## Zweck

Wiederverwendbare Live-Scripting-Ebene unter `10_Online_Machining`: sichtbare
NX-Sitzung per Dispatcher steuern, Jobs als Python-Files shippable, Results
einsammelbar. Ordner nach Datenfluss: `01_host/` → `02_bridge/` → `03_jobs/`,
`04_reference/` zum Nachschlagen.

## Beobachtet / validiert (Stand 2026-09-06)

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
[verified-recipes.md](../skills/nx-live-scripting/references/verified-recipes.md);
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

## Geplant (nicht begonnen)

1. Generalisierung `NX_BRIDGE_ROOT` mit `ONLINE_MACHINING_ROOT`-Fallback, danach echter Lauf gegen `10_Online_Machining` (Handoff 9.1).
2. Rückkanal fürs Auge (Handoff 9.2) — größter Hebel.
3. .NET→Python-Mapping-Regeln + verifizierte Beispiele indexieren, erst dann Embedding-Index (Handoff 9.3).
4. Dispatcher auf `managed_core`/net8 nur bei NX-Upgrade oder wenn ohnehin angefasst (Handoff 9.4, heute nicht anfassen).

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
- Kein Project-Board (erst bei mehreren aktiven/blockierten/übergebenen Issues).

Herleitung und Alternativenbewertung: [nx-live-scripting-handoff.md](nx-live-scripting-handoff.md).
Betriebsregeln: [../AGENTS.md](../AGENTS.md).
