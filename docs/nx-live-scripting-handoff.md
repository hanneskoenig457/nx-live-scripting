# NX live scripten — Recherchestand & Bewertung

Handoff-Notiz aus einer Claude-Code-Session, 2026-09-05.
Thema: Siemens NX aus einem LLM heraus **live in der sichtbaren Sitzung** steuern.
Gegenfrage am Anfang: gibt es bei NX Open einen Einstiegspunkt analog zum
gRPC-Server von Ansys Workbench, den man per Flag startet?

Kennzeichnung durchgehend:
**[V]** = an Quellcode/Doku des eigenen Projekts verifiziert ·
**[V-extern]** = fremde Primärquelle selbst gelesen ·
**[W]** = aus Websuche, nicht selbst getestet ·
**[A]** = Annahme/Einschätzung ·
**[F]** = im Verlauf als falsch erkannt

---

## 1. Ausgangsfrage: Gibt es ein Startflag wie bei Ansys?

**Nein — kein Flag.** [W]
NX kennt keinen eingebauten RPC-Server, der per Kommandozeilenschalter hochkommt.
Es gibt aber mehr eingebaute Substanz als zunächst behauptet:

| Weg | Prozess | Für Live-Session? |
|---|---|---|
| `run_journal.exe` | eigener headless NX-Kernel | nein (Batch) |
| NX Open "external" (.exe mit `Session.GetSession()`) | eigener headless Kernel, **kein** Attach an die GUI | nein |
| `File → Execute → NX Open` (Ctrl+U) | laufende GUI | ja, aber manuell |
| Startup-Assembly im `startup`-Ordner | laufende GUI, beim Start geladen | **ja — das ist der Weg** |
| NX Remoting (.NET Remoting) | laufende Session über HTTP-Kanal | ja, siehe Abschnitt 3 |

**`ugraf.exe -nx <journal>` ist keine Alternative** [V]: NX startet und ignoriert
die Datei. `run_journal.exe -help` listet alle Journal-Optionen; die GUI hat keine.

---

## 2. Der Lade-Mechanismus — hier lag ich zuerst falsch

**[F] Falsch von mir behauptet:** "USER_STARTUP ist kein Legacy-C-Zwang, das darf
auch .NET sein."

**[V] Richtig ist:**
- `USER_STARTUP` lädt eine **native** DLL und löst `ufsta` als exportiertes
  C-Symbol auf. Ein .NET-Assembly scheitert dort mit
  *"Library is missing required entry point"*. Es bräuchte die NX-Open-C++-
  Komponente (`UGOPEN`) plus C++-Compiler.
- Der Weg, der **managed Assemblies frisst**: NX lädt Libraries aus dem
  `startup`-Ordner eines Verzeichnisses, das in der Datei aus
  `UGII_CUSTOM_DIRECTORY_FILE` gelistet ist, und ruft dort `ufsta`.
- **`ufsta` muss `int` oder `string` zurückgeben.** Ein `void` wird abgelehnt mit
  *"Found method, but return type is not an integer or string"*, gefolgt von
  *"Cannot find method ufsta in image"* im NX-Syslog.

Die ursprüngliche Skepsis gegenüber USER_STARTUP war also berechtigt — nur die
Begründung lag woanders (nativ vs. managed, nicht "Legacy").

---

## 3. NX Remoting — der eingebaute Fernzugriff

**[W]** NX bringt .NET Remoting mit. Externer Prozess holt sich eine
Session-Referenz ([Q3], [Q4], [Q5]):

```csharp
Session s   = (Session)Activator.GetObject(typeof(Session),   "http://localhost:4567/NXOpenSession");
UFSession uf = (UFSession)Activator.GetObject(typeof(UFSession), "http://localhost:4567/UFSession");
```

- **[V-extern]** Hilfsklasse `NXRemotingHelper` mit `IsSessionRunningRemotely()` und
  `GetServerObject()` — direkt in einer ausgelieferten `NXOpen.Utilities.xml` gelesen ([Q6]); `NXObjectManager.GetTaggedObject(Tag)` ist ausdrücklich
  für Remoting-Anwendungen gedacht.
- Siemens liefert ein Beispiel mit ([Q3], [Q4]):
  `%UGII_BASE_DIR%\UGOPEN\SampleNXOpenApplications\.NET\RemotingExample\`

**Einschränkungen** [W]:
1. **Kein Flag.** Die Server-Hälfte (`ChannelServices.RegisterChannel`) muss von
   innerhalb NX registriert werden — also wieder über den Startup-Weg aus (2).
2. **Das Sample zielt auf die falsche Session:** dessen Server ist eine
   Console-App mit *eigener* Session. Community-Hinweis: der Server registriert
   den Listener und terminiert dann, womit gar keine Session mehr da ist.
3. **NX-Open-Author-Lizenz** wird durchgängig als Voraussetzung genannt ([Q3]). Ungeklärt.
4. **.NET Framework Remoting** ist von Microsoft deprecated, existiert nicht in
   .NET 5+. Vom Mac aus bräuchte es zusätzlich einen Windows-Proxy-Prozess.
5. **[A] Der Main-Thread-Zwang bleibt.** Remoting dispatcht auf Threadpool-Threads;
   NXOpen ist nicht thread-safe. Remoting löst das Kernproblem also **nicht**,
   es entfernt nur die Arbeit am Protokoll und an der API-Oberfläche.

---

## 4. `#nx: threaded` — der billige Prototyp-Pfad

**[W]** NXOpen-Python-Journals kennen eine Direktive, die das Journal in einem
eigenen Thread laufen lässt ([Q7] — **nur über Suchtreffer, Seite nicht lesbar**):

```python
#nx: threaded
import NXOpen
from bottle import route, run
run(host='localhost', port=8080)
```

Es gibt dokumentierte Berichte, dass ein Bottle-Webserver so aus einem
interaktiven NX-Journal heraus läuft. **[A] Aber:** die Direktive hält nur den
Listener am Leben, sie löst das Thread-Safety-Problem nicht. Das Marshalling auf
den Main-Thread bleibt eigene Arbeit.

---

## 5. Prior Art auf GitHub — und warum sie hinter dem eigenen Stand liegt

| Repo | Lizenz / NX | Stand |
|---|---|---|
| [`DreamEnding/NX_MCP`][Q1] | MIT, NX 2506 | `MCP-Client ↔ Python-Sidecar ↔ JSON-RPC über Loopback ↔ NX-Bridge ↔ NXOpen`. Journal-basierte Request-Pump auf dem Main-Thread, Token-Auth, Workspace-Confinement. **Batch-only; interaktive GUI ausdrücklich "conditional".** Früherer Direct-Attach-Entwurf als unverifiziert verworfen. |
| [`TQJ2007-git/nx-mcp`][Q2] | MIT, NX 2206 | `queue + threading.Event` zum Marshallen auf den Main-Thread. Batch läuft, **Realtime-Modus unfertig** — ausdrücklich wegen "journal execution limitations in interactive NX sessions". |
| [`nxopen-mcp`][Q9] | — | Kein Steuerungs-Server. RAG über die NXOpen-.NET-Doku aus der eigenen lizenzierten Installation (BGE-M3 + sqlite-vec). Siehe Abschnitt 8. |
| [`Foadsf/NXOpen_Python_tutorials`][Q10], `nxopen-python-cookbook`, [`nxopentse`][Q11] | — | Rezepte und Fallstricke, kein Server. |

**Kernaussage:** Zwei unabhängige Projekte bauen dieselbe Architektur und
**beide scheitern am interaktiven Modus**, nicht am Protokoll.

---

## 6. Der eigene Stand (`10_Online_Machining`) — löst genau das

**[V] aus `nx/bridge/VisibleBridge.cs` und `docs/nx-setup.md`:**

- Dispatcher ist ein **C#-Assembly**, von NX beim Start über
  `UGII_CUSTOM_DIRECTORY_FILE` → `startup` → `ufsta` geladen.
- Er pollt eine Queue auf einem **`System.Windows.Forms.Timer`, Intervall 1000 ms**.
  Damit läuft jeder NX-API-Call auf dem Thread, auf dem NX ihn gestartet hat.
  **Kein Socket, kein Hintergrund-Thread mit NX-API.**
  → **[F] Ich hatte gezweifelt, ob ein WinForms-Timer im Qt-Message-Loop von NX
  zuverlässig tickt. Der Code beweist, dass er es tut.**
- **Jobs sind Python**, nicht C#: eine `job.py` mit globaler `main(job_dir)`,
  ausgeführt via `Session.Execute(path, "", "main", new object[]{ dir })`.
  Exceptions propagieren korrekt.
  → **[F] Ich hatte in der Bewertung noch einen Compile-Schritt pro Job
  unterstellt. Den gibt es nicht mehr; kompiliert wird nur der Dispatcher, einmal.**
- Warum nicht `JournalManager.PlayDotNetJournal` [V]: nimmt nur C#/VB-**Source**,
  kompiliert gegen .NET 8 während der Dispatcher auf .NET Framework läuft
  (*"Resolve failed: System.Runtime, Version=8.0.0.0"*), und **meldet Erfolg
  auch wenn das Journal wirft**.
- Sicherheit/Robustheit [V]: SHA-256-Prüfung der Source, Pfad-Confinement auf das
  Projektverzeichnis, atomare Renames `.ready` → `.running` → `.done`/`.failed`,
  vor Sessionstart eingereihte Requests werden als `.stale` quarantiert,
  **kein zusätzlicher offener Port** (Transport ist die bestehende SSH/SCP-Verbindung).
- Guards [V]: bricht ab bei `SessionId == 0` (keine sichtbare Desktop-Session),
  pausiert bei `JournalManager.IsJournalRunning`, prüft die Main-Thread-Identität
  bei jedem Tick.
- VM-Spezifika [V]: ARM64-Parallels, NX ist x64; x64-.NET liegt in
  `C:\Program Files\dotnet\x64`, was der NX-Loader nicht durchsucht →
  `start-visible.cmd` setzt `DOTNET_ROOT`.
- Verifiziert [V]: Run `20260905T211411Z-4db4f56d`, Python-Job aus der sichtbaren
  Sitzung; früher `20260905T210107Z-3916f657`, Feature `CYLINDER(0)`,
  NX-PID 7852, **Desktop-Session 1**.

---

## 7. Bewertung: Remoting vs. der eigene Dispatcher

**Empfehlung: nicht wechseln.** [A]

| | eigener Dispatcher | NX Remoting |
|---|---|---|
| Main-Thread | **gelöst, verifiziert** | wieder offen (Threadpool) |
| Lizenz | keine zusätzliche | NX Open Author, ungeklärt |
| Angriffsfläche | kein offener Port, SSH + SHA-256 | zusätzlicher Listener auf 4567 |
| Tech-Basis | .NET Framework, lebendig | deprecated, kein .NET 5+ |
| Mac-Anbindung | direkt über SSH | zusätzlicher Windows-Proxy nötig |
| Granularität | grob: ein Skript pro Runde | fein: ein Wire-Call pro Property |

**Das entscheidende Argument gegen Remoting ist die Granularität, nicht die
Latenz** [A]: Remoting ist ein Objekt-Proxy — jeder Property-Zugriff ist ein
Wire-Call. Ein Lauf über 500 Features sind 500+ Round-Trips. Das Skript-Shipping-
Modell überträgt beliebige Berechnung in **einem** Round-Trip und ist für
Bulk-Inspektion strukturell überlegen. Remoting gewinnt nur beim Fall
"eine winzige Frage, sofort" — und genau den stellt ein LLM selten; es fragt
"wie sieht das Modell aus", also den Bulk-Fall.

**Ebenfalls, inzwischen gemessen [V]:** Eine SSH-Runde zur VM kostet **0,3 s**,
mit PowerShell **0,5 s**. Die Behauptung aus einer früheren Sitzung, eine
Auftragsrunde koste „15–20 s, fast alles SSH-Latenz", war **falsch** — VM und Host
liegen auf derselben Maschine. Ein kompletter Auftrag (hochladen → ausführen →
einsammeln) dauert **7 s**, davon rund **4 s reine Poll-Granularität**: 1 s Timer
im Dispatcher plus die Warteschleife im Host. Der Transport selbst liegt bei ~3 s
und besteht aus sechs bis acht einzelnen SSH-Aufrufen à 0,3–0,5 s — teuer ist die
**Anzahl** der Runden, nicht die einzelne. Weiter zu optimieren bringt einem
Agenten-Loop trotzdem wenig, weil die Denkzeit des Modells (Sekunden) dominiert.

**Die eine echte Lücke, die Remoting hätte und das Polling-Modell nicht:**
**Event-Push** — NX meldet von sich aus "Nutzer hat etwas geändert". Das kann die
Queue nicht. Falls der Agent auf Nutzeraktionen reagieren soll, ist das der
einzige Punkt, an dem Remoting (oder ein anderer Callback-Weg) wirklich gebraucht
wird.

### Billigere Verbesserungen im bestehenden Design [A]

1. **Timer-Intervall 1000 ms → 100–200 ms.** Ein Wort im Quellcode, senkt den
   dominierenden Latenzterm. Kosten: mehr Leerlauf-Ticks, vernachlässigbar.
2. **Resident-Query-Job:** eine feste `query.py` mit stabilem Hash, die die
   eigentliche Frage aus dem Run-Verzeichnis liest. Spart das Hochladen neuer
   Source pro Frage.
3. **Reads bündeln:** ein Job liefert einen reichen Zustands-Snapshot statt N
   kleiner Abfragen.
4. **Undo-Marks pro Agenten-Schritt** (`session.SetUndoMark`) — bei
   LLM-gesteuerter Konstruktion kein Nice-to-have.

---

## 8. nxopen-mcp / RAG über die API-Doku

**Was es ist** [W] ([Q9]): kein Live-Zugriff auf NX. Ein Index über die
NXOpen-.NET-API-Dokumentation aus der **eigenen lizenzierten** Installation,
als MCP-Tools ausgeliefert, mit hybridem Retrieval (BGE-M3-Embeddings +
sqlite-vec). Der Agent fragt "wie erzeuge ich eine Extrusion" und bekommt die
passenden Signaturen statt der ganzen Doku.

**Spart das Tokens/Zeit?** Ja [A] — aber die Fähigkeit ist teilweise schon da [V]:
- `04_reference/NXOpen.xml`, 59 MB, versionsgleich aus der eigenen Installation
- `04_reference/nx_api_lookup.py` sucht darin

**Was fehlt** [A]:
- Die vorhandene Suche ist **Substring-Match auf Member-Namen**. Sie setzt voraus,
  dass man den Klassennamen schon errät. Embeddings erlauben "wie mache ich eine
  Senkbohrung" ohne Vorwissen. Das ist die echte Lücke.
- MCP-Exposition, damit der Agent selbst nachschlägt, statt dass jemand von Hand
  ein Skript aufruft.
- **Bekannte Reibung** [V], laut Docstring des eigenen Tools: das XML enthält
  **.NET**-Signaturen, die Jobs sind **Python** — die Signaturen unterscheiden
  sich. Das ist ein realer Grund, warum Halluzinationen bleiben, und kein
  Retrieval-Verfahren behebt es allein.

---

## 9. Tool-bezogene Optimierungen (Toolkit `08_NX_API`)

Die wiederverwendbare Ebene wurde nach `08_NX_API` herausgelöst; siehe dort
`README.md`. `10_Online_Machining` ist die erste Anwendung davon.
Reihenfolge unten nach Wirkung.

**Nachtrag 2026-09-06:** Die Ordner im Toolkit heißen inzwischen `01_host/`,
`02_bridge/`, `03_jobs/`, `04_reference/` (Datenflussreihenfolge). Pfadangaben
unten sind darauf aktualisiert, wo sie das Toolkit meinen; Pfade mit dem Präfix
`10_Online_Machining/` beschreiben weiter jenes Projekt und sind unverändert.
Aus diesem Stand ist der Skill `skills/nx-live-scripting/` entstanden.

### 9.1 Generalisierung der Namen — Voraussetzung für alles Weitere [V]

Der Code ist wörtlich kopiert, die projektgebundenen Namen stecken noch drin:
`ONLINE_MACHINING_ROOT` und der Default-Ordner `OnlineMachiningNX`
(`02_bridge/VisibleBridge.cs:27-28`, `02_bridge/start-visible.cmd:8`), die
Task-Namen `OnlineMachining-NX-Bridge` (`01_host/nx_bridge_install.py:33,35`)
und `OnlineMachining-NX-Interactive` (`01_host/nx_visible.py:22,23`), sowie der
harte Pfad `C:/Users/hanne/Documents/OnlineMachiningNX`
(`01_host/nx_remote.py:13`).

Vorschlag: `NX_BRIDGE_ROOT` einführen, `ONLINE_MACHINING_ROOT` als Fallback
behalten, damit die verifizierte Installation nicht bricht. Danach gegen einen
echten Lauf in `10_Online_Machining` prüfen — nicht nur gegen den Smoke-Test.

### 9.2 Rückkanal fürs Auge — der größte Hebel am Toolkit [A]

Ein Job liefert heute nur `result.json`. **Das Modell sieht nicht, was es gebaut
hat.** Ein Viewport-Bild und/oder das erzeugte PDF mit ins Run-Verzeichnis, von
`nx_visible.py collect` mit eingesammelt und dem Agenten vorgelegt, macht aus
einem blinden Loop einen sehenden.

Doppelter Nutzen: Es ist zugleich die billigste Absicherung gegen den bereits
einmal aufgetretenen Fehlermodus „Zeichnung exportiert still ein leeres Blatt".
Ein API-Erfolg ohne Bild beweist nichts — die Trennung von *API success* und
*visual acceptance* steht in der eigenen Doku bereits richtig drin, sie ist nur
noch nicht im Werkzeug abgebildet.

### 9.3 Semantisches API-Retrieval und .NET→Python-Mapping [A]

Vorhanden [V]: `04_reference/NXOpen.xml` (56 MB, versionsgleich aus der eigenen
Installation) und `04_reference/nx_api_lookup.py`.

Zwei Lücken, und die zweite ist die wichtigere:

**(a) Retrieval.** Die Suche ist ein **Substring-Match auf Member-Namen**. Sie
setzt voraus, dass der Klassenname schon erraten ist — „Extrude" findet man nur,
wenn man „Extrude" eingibt. Ein Embedding-Index (das öffentliche `nxopen-mcp`
nutzt BGE-M3 + sqlite-vec) erlaubt „wie mache ich eine Senkbohrung" ohne
Vorwissen. Einmal bauen, danach billig.

**(b) Mapping — der eigentliche Punkt.** Das XML enthält **.NET**-Signaturen,
die Jobs sind **Python**. Der Docstring von `nx_api_lookup.py` sagt das selbst:
*„signatures may differ in Python"*. Ein Agent, der eine .NET-Signatur liest und
Python schreibt, produziert genau dann plausiblen, nicht lauffähigen Code — und
**kein Retrieval-Verfahren behebt das**, egal wie gut die Suche ist. Besseres
Suchen liefert nur schneller die falsch geformte Antwort.

Was hier wirklich hilft, in aufsteigendem Aufwand:
1. Die bekannten systematischen Unterschiede als Regelwerk neben den Suchtreffer
   legen (Properties vs. `Get`/`Set`, `out`-Parameter werden zu Rückgabetupeln,
   Enum-Pfade, `Destroy()`-Pflicht bei Buildern, Expression-Strings statt Zahlen).
2. Signaturen aus den **funktionierenden** Jobs als verifizierte Beispiele
   indexieren — echter, in dieser NX-Version gelaufener Python-Code schlägt jede
   übersetzte .NET-Signatur.
3. Erst dann der Embedding-Index über das XML.

**Fund beim Verifizieren der Ablage [V]:** Das XML führt pro Member die
**License requirements** und **Deprecations** mit, z. B. bei
`FeatureCollection.CreateCylinderBuilder` *„solid_modeling OR cam_base OR
insp_programming"*, und bei `Implicit.…CreateCylinderBuilder` *„Deprecated in
NX2406.0.0, use …CreateCylinderBuilder1 instead"*. Beides gehört in den Index:
der Agent kann dann vor dem Schreiben sehen, ob ein Aufruf überhaupt lizenziert
ist und ob er auf einer veralteten Signatur sitzt. Das ist billiger Gewinn und
adressiert zwei Fehlerklassen, die sonst erst zur Laufzeit auffallen.

Als MCP-Server exponieren, damit der Agent selbst nachschlägt, statt dass jemand
von Hand ein Skript aufruft.

### 9.4 .NET-Runtime: Framework heute, `managed_core` später

**Befund [V]:** NX 2506 liefert **beide** Loader mit — `NXBIN\managed`
(.NET Framework) und `NXBIN\managed_core` (.NET 8). NX versucht zuerst .NET Core 8
und fällt auf Framework zurück; im Syslog steht das wörtlich: *„ERROR: No versions
of .NET Core 8 were found … Compiler set to .NET Framework"*. Der Dispatcher wird
heute mit `csc.exe` aus dem .NET Framework gebaut und über den Framework-Loader
geladen. Das läuft verifiziert.

**Was das für die Zukunft heißt [A]:** Die Richtung ist eindeutig — Core ist der
bevorzugte, Framework der Fallback-Pfad. Ein Termin, zu dem Siemens den
Framework-Loader entfernt, ist nicht bekannt; dass er irgendwann fällt, ist
plausibel. Dann muss der Dispatcher einmal gegen `managed_core\NXOpen.dll` auf
`net8.0-windows` neu gebaut werden. Das braucht ein .NET-8-**SDK** (das Runtime
allein genügt zum Bauen nicht) und eine `.csproj` mit `UseWindowsForms`, weil der
Timer aus `System.Windows.Forms` kommt.

**Empfehlung: jetzt nicht anfassen.** [A] Der Wechsel bringt heute keinen
messbaren Vorteil — 200 Zeilen Dateipolling profitieren weder von Performance noch
von Sprachfeatures. Dem steht das Risiko gegenüber, ein verifiziert laufendes
System auf Verdacht umzubauen. Sinnvoller Auslöser: das nächste NX-Upgrade, oder
wenn der Dispatcher ohnehin angefasst wird.

**Der Ausfall wäre laut, nicht still [V]:** Ohne Framework-Loader würde
`VisibleBridge.dll` gar nicht geladen — es entstünde kein `bridge-loaded.log`,
keine `bridge-status.json`, und `nx_dispatch.py status` scheitert sofort. Billige
Vorwarnung, falls gewünscht: `nx_bridge_install.py` liest nach dem Start das
NX-Syslog und meldet, über welchen der beiden Loader die DLL geladen wurde.

**Nebenbefund zur Plattform [V]:** Auf der ARM64-VM installiert
`winget install Microsoft.DotNet.DesktopRuntime.8` die **arm64**-Variante. NX ist
x64 und braucht das x64-Runtime unter `C:\Program Files\dotnet\x64` — das der
NX-Loader nicht durchsucht, weshalb `start-visible.cmd` `DOTNET_ROOT` setzt. Beim
Nachrüsten also die Architektur erzwingen und prüfen, wohin installiert wurde.

### 9.5 Kleinere Hebel [A]

- **Timer-Intervall 1000 ms → 100–200 ms** (`VisibleBridge.cs`) **und weniger
  SSH-Runden im Host.** Zusammen sind das die ~4 s Poll-Granularität aus den
  gemessenen 7 s (Abschnitt 7). Beides ist wenige Zeilen. Nutzen bleibt begrenzt,
  weil die Denkzeit des Modells ohnehin in Sekunden liegt — deshalb hier unten und
  nicht oben.
- **Resident-Query-Job:** feste `query.py` mit stabilem Hash, Frage kommt aus dem
  Run-Verzeichnis. Spart das Hochladen neuer Source pro Abfrage.
- **Reads bündeln:** ein Zustands-Snapshot statt N Einzelabfragen. Passt zum
  Skript-Shipping-Modell und ist der Grund, warum Remoting hier nichts bringt
  (siehe Abschnitt 7).
- **Undo-Marks pro Agenten-Schritt.** In `live_demo.py` bereits vorbildlich
  umgesetzt (`SetUndoMark` je Schritt) — gehört als Konvention in den
  Job-Contract, nicht nur in einen Demo-Job.
- **Event-Push bleibt die einzige echte Lücke des Polling-Modells.** Nur
  angehen, wenn der Agent auf Nutzeraktionen in der GUI reagieren soll.

---

## 10. Projekt-Hebel (`10_Online_Machining`) — nicht Toolkit

Zur Abgrenzung, damit es nicht vermischt wird. Gemessen an `abstract.md`
Phase 1 ist der CAD-Teil bei ungefähr null [V]:

1. **STEP-AP214-Export fehlt vollständig.** `grep` über alle Jobs und Tools
   findet keinen STEP-/Export-Code außer PDF. Blockiert Test A bei allen vier
   Anbietern. **Per Reimport verifizieren, nicht per Dateigröße.**
2. **Das Bauteil existiert nicht.** `live_demo.py` baut drei gestapelte Zylinder
   ohne Boolean (also drei Bodies), ausdrücklich „not production CAD".
   Von ø20 h6 / Ra 0,8, Passfedernut 6 P9 (DIN 6885 A), Sicherungsringnut
   DIN 471 (1,1 +0,14; Nutgrund ø19,0 h11) und M6 mit Zentrierung DIN 332 ist
   **keines** modelliert.

   **Konstruktionsweg [A]:** Die Zylinder in `live_demo.py` sind NX-Grundkörper
   (`CreateCylinderBuilder`) — parametrische Features ohne Skizze. Richtig für eine
   Taktungs-Demo, falsch für ein Drehteil. Für den Prüfkörper: **eine Skizze des
   Halbprofils → Rotation** trägt ø25, den Sitz ø20 h6, die Sicherungsringnut und
   die Fasen in *einem* Feature, mit allen Maßen als Ausdrücken an einer Stelle;
   **Bohrung**-Feature für M6 mit Zentrierung; **Skizze + Extrusion (Abzug)** für
   die Passfedernut. Grundkörper bräuchten je Absatz eine Boolesche Operation,
   ergäben einen unübersichtlichen Baum und keine saubere, assoziativ bemaßbare
   Kontur — genau das, worauf die Zeichnungsableitung angewiesen ist.
3. **Toleranzen, die das Portal liest.** Bewiesen ist bisher nur, dass *ein*
   Toleranzzeichen rendert. Gebraucht: Passungskurzzeichen, Rauheitssymbol,
   ISO-2768-m-Sammelvermerk — in einer Form, die ein DFM-Review annimmt.
4. **Reopen-Validierung und Parameter-Propagation**, weil das ganze Abstract auf
   Reproduzierbarkeit zielt und dieselbe Revision an vier Portale geht.

**Priorisierungshinweis:** Die Transportfrage ist beantwortet, dort liegt nichts
mehr. Punkt 9.2 (Augen) und Projekt-Punkt 1 (STEP) sind zusammen vermutlich ein
Nachmittag und schalten den Rest frei.

---

## Quellen

Belastbarkeit unterschiedlich — deshalb mit Zuordnung und Einschränkung.
**Gelesen** = Seite selbst abgerufen. **Nur Suchtreffer** = die Seite lieferte 403
bzw. rendert per JavaScript; die Aussage stammt aus der Zusammenfassung einer
Suchmaschine und wurde **nicht am Original geprüft**.

### Primärquellen (gelesen)

- **[Q6]** [`NXOpen.Utilities.xml` — NXRemotingHelper](https://github.com/cgrooves/ME578_Lab8/blob/master/NXRemotingProject/NXRemotingProject/bin/Debug/NXOpen.Utilities.xml)
  · gelesen · belegt `NXRemotingHelper`, `IsSessionRunningRemotely()`,
  `GetServerObject()`, `NXObjectManager.GetTaggedObject` als Remoting-API.
  **Stärkster Beleg dafür, dass NX Remoting real existiert.**
- **[Q1]** [DreamEnding/NX_MCP](https://github.com/DreamEnding/NX_MCP) · gelesen ·
  Architektur, Journal-Pump, „Batch-only, interactive GUI conditional".
- **[Q2]** [TQJ2007-git/nx-mcp](https://github.com/TQJ2007-git/nx-mcp) · gelesen ·
  `queue + threading.Event`, Realtime-Modus unfertig.
- **[Q8]** [GitHub-Topic `siemens-nx`](https://github.com/topics/siemens-nx) ·
  gelesen · Übersicht der Repos.
- **[Q9]** `nxopen-mcp` (über [Q8]) · Beschreibung gelesen, Code nicht ·
  RAG über NXOpen-.NET-Doku, BGE-M3 + sqlite-vec.
- **[Q3]** [nxjournaling — Bi-directional data flow](https://nxjournaling.com/content/bi-directional-data-flow-using-nx-open-external-program)
  · gelesen · Remoting existiert, **Author-Lizenz nötig**, Sample-Pfad.
  Nennt keine Portnummer und keinen Code.

### Nur Suchtreffer — nicht am Original geprüft

- **[Q4]** [eng-tips — NXOpenRemotingService example](https://www.eng-tips.com/threads/nx-remoting-need-help-with-nxopenremotingservice-example.511227/)
  · **403** · Quelle für: Sample kompilierbar als Console-App, Server registriert
  Listener und terminiert dann.
- **[Q5]** [eng-tips — NXOpen VB.Net Remoting](https://www.eng-tips.com/threads/nxopen-vb-net-remoting.394790/)
  · **403** · Quelle für **Port 4567**, `http://localhost:4567/NXOpenSession`
  und die `Activator.GetObject`-Zeilen in Abschnitt 3.
  → Der konkrete Code-Schnipsel ist damit **unbestätigt**. Vor Verwendung gegen
  das lokale Sample unter
  `%UGII_BASE_DIR%\UGOPEN\SampleNXOpenApplications\.NET\RemotingExample`
  prüfen — das ist ohnehin die bessere Quelle.
- **[Q7]** [eng-tips — NXOpen python journal, how to stop](https://www.eng-tips.com/threads/nxopen-python-journal-how-to-stop.436880/)
  · **403** · einzige Quelle für `#nx: threaded` **und** für den Bericht, dass ein
  Bottle-Webserver aus einem interaktiven Journal läuft. **Schwächster Punkt der
  ganzen Recherche** — falls dieser Weg verfolgt wird, zuerst selbst reproduzieren.
- **[Q12]** [Siemens Community — Threading](https://community.plm.automation.siemens.com/t5/NX-Programming-Customization-Forum/Threading/td-p/296586)
  · **403** · NXOpen ist nicht thread-safe, Calls müssen vom Main-Thread kommen.
  Inhaltlich durch den eigenen `VisibleBridge.cs` ohnehin bestätigt.
- **[Q10]** [Foadsf/NXOpen_Python_tutorials](https://github.com/Foadsf/NXOpen_Python_tutorials) ·
  **[Q11]** [theScriptingEngineer/nxopentse](https://github.com/theScriptingEngineer/nxopentse)
  · nur aus Trefferlisten, Inhalte nicht gesichtet.

### Nicht erreichbar

Mehrere Threads auf `community.sw.siemens.com` rendern per JavaScript und lieferten
nur eine CSS-Fehlerseite. Dort liegt vermutlich die belastbarste Diskussion zu
Remoting gegen eine **laufende GUI-Sitzung** — offener Rechercheweg, am besten
direkt im Browser.

### Eigene Primärquellen (im eigenen Projekt verifiziert)

- `10_Online_Machining/nx/bridge/VisibleBridge.cs` — Startup über `ufsta`,
  WinForms-Timer auf dem Main-Thread, `Session.Execute` für Python-Jobs,
  SHA-256, Queue-Semantik, Guards.
- `10_Online_Machining/docs/nx-setup.md` — `UGII_CUSTOM_DIRECTORY_FILE`,
  `ufsta`-Rückgabetyp, warum nicht `USER_STARTUP`, warum nicht
  `PlayDotNetJournal`, verifizierte Run-IDs.
- `10_Online_Machining/abstract.md` — Bauteilspezifikation, Phasen, Anbieter.
- `04_reference/NXOpen.xml` — versionsgleiche API-Doku inkl. License-Requirements
  und Deprecations pro Member.

[Q1]: https://github.com/DreamEnding/NX_MCP
[Q2]: https://github.com/TQJ2007-git/nx-mcp
[Q8]: https://github.com/topics/siemens-nx
[Q9]: https://github.com/topics/siemens-nx
[Q10]: https://github.com/Foadsf/NXOpen_Python_tutorials
[Q11]: https://github.com/theScriptingEngineer/nxopentse
