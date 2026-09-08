# API-Referenzen

Dieser Ordner enthält zwei absichtlich lokale, nicht versionierte
NXOpen-Referenzen:

- `NXOpen.xml` ist die mit der installierten NX-Version gelieferte .NET-API-
  Dokumentation. Für exakte Signaturen dieser Installation bleibt sie die
  maßgebliche Quelle.
- `nxopen_python_ref/` ist ein statischer Spiegel der öffentlichen
  [NXOpen-Python-Doxygen-Referenz von Siemens](https://docs.sw.siemens.com/documentation/external/PL20241101461013487/en-US/custom_api/nxopen_python_ref/index.html).
  Lokaler Einstieg: `nxopen_python_ref/index.html`.

Der Spiegel wird mit folgendem, ausschließlich auf diese URL beschränkten
Standardbibliotheks-Skript aktualisiert:

```sh
.venv/bin/python 04_reference/mirror_nxopen_python_ref.py
```

Ein unterbrochener Lauf wird automatisch fortgesetzt. Mit `--refresh` werden
auch bereits vorhandene Dateien noch einmal vom Siemens-Server abgerufen.
Die Vorgabe drosselt Abrufe auf zehn pro Sekunde, damit der öffentliche Server
nicht unnötig belastet wird.

Er bleibt aus Git ausgeschlossen: Die Vendor-Dokumentation ist kein
Projektquellcode und soll nicht weiterverteilt werden. Die Online-Dokumentation
kann gegenüber der installierten NX-Version abweichen; verifizierter Python-Code
und anschließend ein Probe-Job haben weiterhin Vorrang.
