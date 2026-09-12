# API-Referenzen

Dieser Ordner enthält zwei absichtlich lokale, nicht versionierte
NXOpen-Referenzen:

- `NXOpen.xml` ist die mit der installierten NX-Version gelieferte .NET-API-
  Dokumentation. Sie ist die letzte Rückfallebene für Lizenzanforderungen,
  Deprecations und .NET-Details — nicht die kanonische Python-Signaturquelle.
- `nxopen_python_ref/` ist ein statischer Spiegel der öffentlichen
  [NXOpen-Python-Doxygen-Referenz von Siemens](https://docs.sw.siemens.com/documentation/external/PL20241101461013487/en-US/custom_api/nxopen_python_ref/index.html).
  Lokaler Einstieg: `nxopen_python_ref/index.html`.

Beim Schreiben eines neuen Aufrufs gilt: erst verifizierte Projekt-Snippets,
dann der Python Reference Guide; die XML-Referenz erst, wenn diese Quellen die
Frage nicht beantworten. Ein im Guide fehlender Name wird nicht geraten,
sondern höchstens als klar markierter Probe-Kandidat behandelt.

## Python Guide durchsuchen

Die lokale Guide-Suchleiste funktioniert offline. Agenten verwenden denselben
Doxygen-Index direkt, statt mit `rg` durch tausende HTML-Dateien zu laufen:

```sh
.venv/bin/python 04_reference/nxopen_python_search.py CreateCylinderBuilder
.venv/bin/python 04_reference/nxopen_python_search.py FeatureCollection --section classes
```

Die Suche hat bewusst Doxygen-Semantik: Sie findet Namenspräfixe in der
gewählten Indexkategorie und liefert die lokale Referenzseite samt Anker. Ein
fehlender Treffer ist damit aussagekräftig; erst danach ist ein enger,
expliziter Probe-Job angebracht. Die Python-Stubs 2506.3001 dienen lediglich
als schnelle Lesehilfe für die wenigen unstrukturiert gerenderten Enum-Tabellen.
Sie sind keine kanonische Signaturquelle und decken insbesondere `NXOpen.UF`
nicht ab.

## Lokale Enum-Reparatur

Ein Vergleich der 2506.3001-Stubs mit den jeweils gleichnamigen, echten
Doxygen-Enum-Seiten findet derzeit **257** Seiten, deren Tabelle Werte auslässt
oder nicht zuverlässig strukturiert. Nach jedem erfolgreichen Standard-Refresh
ergänzt der Spiegel dafür automatisch eine klar markierte Tabelle mit den
Stub-Werten; die ursprüngliche Siemens-Tabelle bleibt darunter unverändert.
Die Zuordnung prüft ausdrücklich die erzeugte `ValueOf`-Methode und fasst keine
gleichnamige normale Klasse an (etwa den alten Alias `NXOpen.Axis`).

Manuell prüfen oder erneut anwenden:

```sh
.venv/bin/python 04_reference/repair_nxopen_python_enum_tables.py
.venv/bin/python 04_reference/repair_nxopen_python_enum_tables.py --apply
```

Die reparierten Seiten und ihr lokales Manifest bleiben wie der gesamte
Vendor-Spiegel außerhalb von Git. `--no-enum-repair` unterdrückt den Schritt
bei einem Spiegel-Refresh ausnahmsweise.

Der Spiegel wird mit folgendem, ausschließlich auf diese URL beschränkten
Standardbibliotheks-Skript aktualisiert:

```sh
.venv/bin/python 04_reference/mirror_nxopen_python_ref.py
```

Ein unterbrochener Lauf wird automatisch fortgesetzt. Mit `--refresh` werden
auch bereits vorhandene Dateien noch einmal vom Siemens-Server abgerufen.
Die Vorgabe drosselt Abrufe auf zehn pro Sekunde, damit der öffentliche Server
nicht unnötig belastet wird.
Der Aktualisierer erkennt zudem die von Doxygen nur dynamisch aufgebauten
Suchindex-Dateien (`search/*_<hex>.js`), damit die Suchleiste auch offline
funktioniert.

Die lokale Link-Integrität lässt sich ohne Netzwerkzugriff prüfen:

```sh
.venv/bin/python 04_reference/mirror_nxopen_python_ref.py --verify
```

Er bleibt aus Git ausgeschlossen: Die Vendor-Dokumentation ist kein
Projektquellcode und soll nicht weiterverteilt werden. Die Online-Dokumentation
kann gegenüber der installierten NX-Version abweichen; verifizierter Python-Code
und anschließend ein Probe-Job haben weiterhin Vorrang.
