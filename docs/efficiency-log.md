# Efficiency log

Token-/Zeit-Kennzahlen einzelner Agent-Läufe mit diesem Toolkit, damit sich
Verbesserungen (Skill-Fixes, Prompt-Änderungen, weniger Round-Trips) über die
Zeit tatsächlich nachweisen statt nur vermuten lassen.

**Methodik (immer gleich anwenden, sonst sind Zeilen nicht vergleichbar):**
Transkript-JSONL unter `~/.claude/projects/<project>/<session-id>.jsonl`,
Assistant-Records nach `message.id` deduplizieren (ein gestreamter Turn
erzeugt mehrere Zeilen mit identischem `usage` — sonst wird 1,8-2x zu viel
gezählt), dann nur die Turns zählen, deren `attributionSkill` dem Skill der
eigentlichen Aufgabe entspricht (eigene Rückfragen zur Token-Nutzung selbst
zählen nicht mit). Gewichtung: Input ×1, Cache-Read ×0,1, Cache-Write ×2,
Output ×5 = **Token effektiv**. **Token aktiv** = Cache-Read + Cache-Write +
Input des *letzten* Turns der Aufgabe (Kontextfenster-Endstand, keine Summe).
**Zeitstempel im JSONL sind UTC** (`...Z`-Suffix) — für die Spalte
Ausführungstimestamp in Lokalzeit umrechnen (Berlin: UTC+2 im Sommer/Frühherbst,
UTC+1 im Winter), sonst steht die falsche Uhrzeit in der Tabelle.

| Run | Projekt/Aufgabe                                                                                    | Modell         |          Zeit | Turns | Token aktiv | Token effektiv | Ausführungstimestamp |
| --- | -------------------------------------------------------------------------------------------------- | -------------- | ------------: | ----: | ----------: | -------------: | -------------------- |
| 4   | `99_4_Muse_Spark_6nd_impl_with_knowledge` — Prüfkörper 3D-Modell + Zeichnung (abstract.md Phase 1) | Sonnet 5, Hoch |        43 min |   197 |        434k |      7,08 Mio. | 07.09.2026, 23:55    |
| 5   | `99_5_Muse_Spark_7nd_impl_with_knowledge` — dieselbe Aufgabe, unabhängig wiederholt                | Sonnet 5, Hoch | 43 min (42,6) |   163 |        419k |      6,20 Mio. | 08.09.2026, 08:45    |

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

## Wie eine neue Zeile entsteht

1. Session-Transkript wie oben beschrieben deduplizieren und nach
   `attributionSkill` filtern.
2. Turns, Zeitspanne, Token aktiv/effektiv wie in der Methodik berechnen.
3. Modell + Reasoning-Effort stehen im Transkript selbst
   (`message.model`, `effort` je Assistant-Record).
4. Neue Zeile anhängen, nie eine bestehende überschreiben — der Wert dieser
   Datei ist der Verlauf über mehrere Runs.
