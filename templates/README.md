# TU-Berlin-Vorlagen (CMTS)

Lokale Spiegelung der Kursdateien aus
`11_CMTS/…/Datei_Templates_und_Einstellu…/CMTS - Templates und Einstellungen.zip`.
Die Dateien selbst sind aus Git ausgenommen (siehe `.gitignore`) — es sind
Kursmaterialien, keine eigenen Erzeugnisse.

| Datei | wofür |
| --- | --- |
| `KUP_Zeichenvorlage.prt` | A3-Blatt mit Rahmen und Schriftfeld — **wird benutzt** |
| `KUP-NewFileTemplate.prt` | Vorlage für neue Modelldateien |
| `Konstruktionslehre TU Berlin.pax` | Palette, damit beide im „Neu"-Dialog erscheinen |
| `nx_TU Berlin_Drafting_Standard_User.dpv` | Drafting Standard für die Customer Defaults |
| `CMTS Customer Defaults v4.dpv` / `.xsl` | Customer Defaults des Kurses |
| `Passungstabelle_metric.prt`, `Stueckliste…prt` | Tabellenvorlagen |

## Was davon eingebunden ist

**Stehende Regel:** Jede Zeichnung entsteht auf `KUP_Zeichenvorlage.prt`.
Referenzjob ist `03_jobs/spark3_zeichnungT.py`; `spark3_zeichnung.py` (CustomSize,
ohne Vorlage) ist überholt und nur noch Beleg. Festgehalten im Job-Contract des
Skills und in `api-drafting.md` §1.

**Die Zeichenvorlage.** Der Zeichnungsjob legt das Blatt mit
`DrawingSheetBuilder.SheetOption.UseTemplate` an und setzt
`MetricSheetTemplateLocation` auf den **vollen Pfad** der Vorlagendatei in der
VM. Damit sind keine Administratorrechte nötig: die Datei muss *nicht* nach
`C:\Program Files\Siemens\NX2506\UGII\templates` kopiert werden, anders als es
die Kursanleitung (`CMTS_Templates_v2.pdf`, Folie 10) beschreibt.

Das Blatt bringt Rahmen und Schriftfeld auf Schicht 256 mit. Die Schicht kommt
im Zustand „nur sichtbar" (2) und wird vom Job auf sichtbar gesetzt, sonst
fehlen beide im PDF.

Nach dem Einsetzen ruft der Job `part.Drafting.SetTemplateInstantiationIsComplete(True)`.
Ohne diesen Abschluss bleibt das Teil halb instanziiert; ein so gespeichertes
Teil ließ sich anschließend mit *„Corrupt data found when loading an OM file"*
nicht mehr öffnen.

**Die Schriftfeldfelder.** Das Schriftfeld füllt sich aus Teile-Attributen, die
der Job setzt. Die Titel liest `03_jobs/spark3_template.py` zur Laufzeit aus der Vorlage aus;
die Vorlage bringt sie als Vorgabewerte mit:

`Bezeichnung/Titel`, `Dokumentenart`, `Allgemeintoleranz`, `Oberfläche`,
`Kanten`, `Werkstoff`, `Material_manuell`, `Name`, `Matrikelnummer`, `Tutor`,
`Tutoriumstermin`, `Gruppe`, `Semester`, `Kurs`, `Datum`, `SHEET_NUM`,
`NO_OF_SHEET`.

`Datum` ist ein Zeitattribut und braucht das Format `TT-Mon-JJJJ hh:mm:ss`;
ISO-8601 lehnt NX ab. Die Zellen für **Maßstab** und **Gewicht** füllt NX
selbst und sie stehen nicht in der Liste editierbarer Zellen
(`TitleBlocks.CreateEditTitleBlockBuilder(...).Cells` liefert 13 Zellen, keine
davon der Maßstab). Der Maßstab bleibt deshalb 1:1 — die Zeichnung steht
entsprechend auf 1:1.

## Was bewusst nicht eingebunden ist

* **Drafting Standard und Customer Defaults (.dpv).** Beide sind
  Sitzungseinstellungen des Rechners, die über den Customer-Defaults-Dialog
  importiert werden. Für einen wiederholbaren Job wäre das eine unsichtbare
  Abhängigkeit vom Zustand der VM: derselbe Job ergäbe auf einem anderen
  Rechner eine andere Zeichnung. Was die Zeichnung braucht, setzt der Job
  stattdessen selbst. Wer die Kursvorgaben interaktiv nutzen will, importiert
  sie nach `CMTS_Templates_v2.pdf` Folie 6 und 7.
* **Passungstabelle und Stückliste.** Für ein Einzelteil ohne Baugruppe ohne
  Nutzen; die vier tolerierten Merkmale stehen direkt am Maß.
* **`KUP-NewFileTemplate.prt`.** Das Modell entsteht aus dem Job heraus, nicht
  aus dem „Neu"-Dialog.

## Einspielen in die VM

```sh
scp templates/* ansys-mechanical-vm:'C:/Users/hanne/Documents/OnlineMachiningNX/templates/'
```

Diesen Pfad erwarten die Jobs in ihrer Konstante `TEMPLATE`
(`03_jobs/spark3_zeichnungT.py`, `03_jobs/spark3_template.py`,
`03_jobs/probes/template_probe.py`).
