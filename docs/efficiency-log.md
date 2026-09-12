# Efficiency log

Token-/Zeit-Kennzahlen einzelner Agent-Läufe mit diesem Toolkit, damit sich
Verbesserungen (Skill-Fixes, Prompt-Änderungen, weniger Round-Trips) über die
Zeit tatsächlich nachweisen statt nur vermuten lassen — **agentenübergreifend**:
jedes Tool (Claude Code, OpenCode, künftige) trägt hier ein, sofern es dieselbe
Methodik anwendet.

**Methodik (agentenunabhängig; immer gleich anwenden, sonst sind Zeilen nicht
vergleichbar):**

1. **Eigene Session-Quelle finden.** Jedes Tool loggt anders — nicht von einem
   Format ausgehen, sondern das eigene tatsächliche Log/DB identifizieren.
   Bekannte Fälle:
   - *Claude Code*: `~/.claude/projects/<project>/<session-id>.jsonl`
     (Zeilen-JSON, ein Eintrag pro Event).
   - *OpenCode*: `~/.local/share/opencode/opencode.db` (SQLite). Tabelle
     `session` führt bereits laufende Aggregate (`tokens_input`,
     `tokens_output`, `tokens_reasoning`, `tokens_cache_read`,
     `tokens_cache_write`) — das ist die autoritative Quelle, nicht selbst
     aus `message` nachrechnen, außer zur Gegenprobe.
2. **Prüfen, ob eine Nachricht mehrfach geloggt wird.** Manche Formate
   speichern einen logischen Antwort-Turn (Denken + Tool-Aufruf, oder
   mehrere parallele Tool-Aufrufe) als **mehrere** Log-Einträge mit
   **identischem** `usage`-Wert. Wird das vor dem Summieren nicht erkannt,
   ist die Summe 1,8-1,9x zu hoch.
   - *Claude Code hat dieses Problem*: JSONL-Assistant-Records nach
     `message.id` gruppieren, `usage` genau einmal pro Gruppe zählen.
   - *OpenCode hat es nicht* (verifiziert 2026-09-08, Session
     `ses_f7d38a565ffec…`): jede `message`-Zeile trägt genau ein atomares
     `tokens`-Objekt (`{total, input, output, reasoning, cache:{read,write}}`),
     keine Duplikate — dort direkt pro Nachricht summieren.
   - Für ein unbekanntes drittes Tool: das erst **empirisch prüfen** (z. B.
     rohe Zeilen-/Eintragszahl gegen eine unabhängige Aggregatzahl des Tools
     selbst vergleichen, falls vorhanden), nicht annehmen.
3. **Nur Turns der eigentlichen Aufgabe zählen.** Eigene Rückfragen zur
   Token-Nutzung selbst (wie diese Analyse) zählen nicht mit — bei Claude
   Code z. B. über `attributionSkill` filtern, bei anderen Tools über den
   Zeitpunkt/Titel der jeweiligen Unterhaltung.
4. **Rechnung:** Reasoning-Tokens zählen als Output (beide werden vom
   Provider wie Output abgerechnet). Gewichtung: Input ×1, Cache-Read ×0,1,
   Cache-Write ×2, (Output+Reasoning) ×5 = **Token effektiv**.
   **Token aktiv** = Input + Cache-Read + Cache-Write **des letzten Turns**
   (Kontextfenster-Endstand, keine Summe über die Session) — gegen die
   eigene UI-Anzeige des Tools querchecken, wenn sichtbar.
5. **Zeitstempel in Lokalzeit**, nicht roh übernehmen. Beide bekannten
   Quellen liefern UTC (Claude-JSONL: `...Z`-Suffix; OpenCode-DB:
   Unix-Millisekunden) — Berlin: UTC+2 im Sommer/Frühherbst, UTC+1 im
   Winter.

| Run | Agent       | Projekt/Aufgabe                                                                                    | Modell                                 |          Zeit | Turns | Token aktiv | Token effektiv | Ausführungstimestamp |
| --- | ----------- | -------------------------------------------------------------------------------------------------- | -------------------------------------- | ------------: | ----: | ----------: | -------------: | -------------------- |
| 4   | Claude Code | `99_4_Muse_Spark_6nd_impl_with_knowledge` — Prüfkörper 3D-Modell + Zeichnung (abstract.md Phase 1) | Sonnet 5, Hoch                         |        43 min |   197 |        434k |      7,08 Mio. | 07.09.2026, 23:55    |
| 5   | Claude Code | `99_5_Muse_Spark_7nd_impl_with_knowledge` — dieselbe Aufgabe, unabhängig wiederholt                | Sonnet 5, Hoch                         | 43 min (42,6) |   163 |        419k |      6,20 Mio. | 08.09.2026, 08:45    |
| 6   | OpenCode    | `99_6_Muse_Spark_8nd_impl_with_knowledge` — dieselbe Aufgabe, Engineering-Turns ohne Token-Meta    | muse-spark-1.3-contributor-free, xhigh | 22 min (21,7) |    84 |        187k |      1,78 Mio. | 08.09.2026, 22:48    |

**Zu Run 4:** "Token effektiv" korrigiert auf 7,08 Mio. (7.078.475 exakt) statt
der im Chat genannten 7,2 Mio. — letztere war eine Verwechslung mit dem
*Gesamt*-Wert von Run 5 (7.204.346, inklusive dessen eigener
Token-Rückfrage), nicht der Wert für Run 4 selbst.

**Run 4 vs. Run 5, was der Unterschied zeigt:** Run 5 lief nach Run 4 und
profitierte von 4 der 5 API-Fixes, die Run 4 in `api-modelling.md`/
`api-drafting.md` nachgetragen hat (0 Wiederholungen dieser Fehler im Run-5-
Transkript bestätigt) — 34 Turns und ~12% Tokens weniger für dieselbe
Aufgabe. Run 5 fand dafür einen eigenen, neuen Fehler (Sketch-Karteileichen
nach Namenskollision), der jetzt ebenfalls dokumentiert ist. Die reine
Zeit blieb nahezu gleich (43 vs. 42,6 min) — ein Hinweis darauf, dass ein
guter Teil der Zeit aus NX-Dispatch-Wartezeit besteht, die sich durch
weniger Fehlschläge kaum verkürzt, während die Tokenkosten (getrieben vom
Cache-Read pro Turn) sehr wohl sinken.

**Zu Run 6 — Vorsicht beim Vergleich mit 4/5:** deutlich weniger Turns und
Tokens, aber das ist nicht automatisch "OpenCode ist effizienter" — andere
Größenordnung an anderen Stellschrauben zugleich: anderes (kostenloses)
Modell, andere Tool-Aufruf-Architektur, und **hier nicht geprüft, ob Run 6
tatsächlich zum selben validierten Endergebnis kam** (Modell + Zeichnung,
gleiche vier Toleranzmerkmale erfüllt) wie Run 4/5. Erst nach dieser Prüfung
ist ein Effizienzvergleich über Agenten hinweg belastbar, vorher nur ein
Rohdatenpunkt.

**Zu Run 6 — Korrektur:** Die Zeile zählte ursprünglich 99 Nachrichten
inklusive Token-Meta-Rückfragen (31 min, 201k, 2,13 Mio. — Verstoß gegen
Schritt 3) und wurde durch die strikte Scope-Rechnung ersetzt: 84
Engineering-Assistant-Turns + 2 User-Messages, 22 min (21,7), 187k aktiv
(letzter Engineering-Turn, 186.540), 1,78 Mio. effektiv (1.781.352 exakt).
Schritt-2-Prüfung sauber (kein doppeltes Token-Objekt); Gegenprobe
Message-Summen vs. `session`-Aggregate stimmt bis auf Live-Drift; kein
UI-Gegencheck möglich (Headless-Agent).

## Wie eine neue Zeile entsteht

1. Session-Log der Methodik entsprechend identifizieren, auf
   Mehrfachzählung prüfen, dedupliziert nach Turns der eigentlichen Aufgabe
   filtern (siehe oben).
2. Turns, Zeitspanne (in Lokalzeit), Token aktiv/effektiv berechnen.
3. Agent + Modell + Reasoning-Effort/Variante notieren — beim jeweiligen
   Tool selbst nachsehen (Claude Code: `message.model`/`effort` je Record;
   OpenCode: `session.model`/`session.agent`).
4. Neue Zeile anhängen, nie eine bestehende überschreiben — der Wert dieser
   Datei ist der Verlauf über mehrere Runs und Agenten. Spaltenbreiten der
   Markdown-Tabelle beim Anhängen neu ausrichten (Pipes untereinander).
