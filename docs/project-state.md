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
- Skill-Kopie `../skills/nx-live-scripting/SKILL.md` synchron mit `~/.claude/skills/nx-live-scripting` (geprüft 2026-09-06, `diff -rq` leer).

## Bekannte Grenzen (validiert, nicht geraten)

- Projektgebundene Namen stecken noch im Code (`ONLINE_MACHINING_ROOT`, Task-Namen, harter Pfad `C:/Users/hanne/Documents/OnlineMachiningNX`) — siehe Tabelle im [README](../README.md).
- Kein visueller Rückkanal: Job liefert nur `result.json`; Viewport-Bild/PDF wird nicht mit eingesammelt (Handoff-Punkt 9.2).
- API-Suche nur Substring auf Member-Namen; .NET-Signaturen ≠ Python. Lizenz-/Deprecation-Treffer müssen manuell geprüft werden (Handoff-Punkt 9.3).
- Timer 1000 ms + mehrere SSH-Runden ≈ 4 s Poll-Anteil an ~7 s pro Auftrag (Handoff-Punkt 9.5).

## Geplant (nicht begonnen)

1. Generalisierung `NX_BRIDGE_ROOT` mit `ONLINE_MACHINING_ROOT`-Fallback, danach echter Lauf gegen `10_Online_Machining` (Handoff 9.1).
2. Rückkanal fürs Auge (Handoff 9.2) — größter Hebel.
3. .NET→Python-Mapping-Regeln + verifizierte Beispiele indexieren, erst dann Embedding-Index (Handoff 9.3).
4. Dispatcher auf `managed_core`/net8 nur bei NX-Upgrade oder wenn ohnehin angefasst (Handoff 9.4, heute nicht anfassen).

## Repo / laufende Arbeit

- Remote (privat): https://github.com/hanneskoenig457/nx-live-scripting
- Issue #1: Generalisierung `NX_BRIDGE_ROOT` (Handoff 9.1).
- Issue #2: Rückkanal fürs Auge (Handoff 9.2).
- Issue #3: API-Retrieval + .NET→Python-Mapping (Handoff 9.3).
- Kein Project-Board (erst bei mehreren aktiven/blockierten/übergebenen Issues).

Herleitung und Alternativenbewertung: [nx-live-scripting-handoff.md](nx-live-scripting-handoff.md).
Betriebsregeln: [../AGENTS.md](../AGENTS.md).
