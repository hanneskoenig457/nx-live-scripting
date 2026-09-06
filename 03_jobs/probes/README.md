# Probe-Jobs: die Belege hinter `verified-recipes.md`

Diese Jobs haben das NXOpen-Verhalten festgestellt, das in
[`../../skills/nx-live-scripting/references/verified-recipes.md`](../../skills/nx-live-scripting/references/verified-recipes.md)
als Regel steht. Sie liegen hier, damit jede Aussage dort nachprüfbar bleibt
statt geglaubt werden zu müssen.

Sie sind **kein allgemeines Werkzeug**. Entstanden sind sie am Prüfkörper aus
`10_Online_Machining` und erwarten teils dessen Teil unter
`<remote>/specimen/pruefkoerper.prt` oder legen ein Wegwerfteil an. Wer eine
dieser Fragen neu stellt, kopiert den Job und passt ihn an — er ist als
Nachweis archiviert, nicht als API gedacht.

Für Diagnose im laufenden Betrieb sind stattdessen die beiden Jobs eine Ebene
höher gedacht: `feature_reedit_probe.py` und `part_open_probe.py`. Beide nehmen
den Teilepfad über `--parameters` und sind nicht an ein Projekt gebunden.

| Job | beantwortet |
| --- | --- |
| `revolve_variants_probe.py` | Liegt der „Tolerance error" am Profil? (nein — offen/geschlossen, an der Achse/abgerückt scheitern gleich) |
| `revolve_axis_probe.py` | Liegt er an der Achskonstruktion? (nein — vier Varianten, gleiches Ergebnis) |
| `revolve_sketch_probe.py` | Liegt er an losen Kurven statt Skizze? (nein; liefert zusätzlich den Syslog-Auszug mit `+++ Invalid tolerance`) |
| `revolve_tolerance_probe.py` | **Die Ursache:** `Tolerance` = 0,0 gegen 0,01 gegen 0,0254 |
| `sketch_plane_probe.py` | Welches Rezept legt eine Skizze wirklich auf die gewünschte Ebene? (vier Varianten, eine funktioniert) |
| `thread_probe.py` | Nimmt `ThreadBuilder` ein Gewinde auf einer gedrehten Bohrung an? (24 Kombinationen, keine) |
| `hole_probe.py` | Geht es über `HolePackageBuilder`? (ja — und `Tolerance` ist auch dort der Stolperstein) |
| `template_probe.py` | Was steckt in einer Blattvorlage, und nimmt `UseTemplate` einen vollen Pfad? |
| `drawing_api_probe.py` | Welche Mitglieder haben Bemaßung, Schnitt, Einzelheit, Oberflächensymbol, Schriftfeld in diesem NX-Stand? |
| `model_api_probe.py` | Welche Feature-Builder gibt es, und welche Aufzählungswerte kennen sie? |

Alle sind lesend bzw. arbeiten auf Wegwerfteilen und speichern nichts am
Prüfkörper.
