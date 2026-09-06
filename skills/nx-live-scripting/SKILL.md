---
name: nx-live-scripting
description: Drive Siemens NX from an agent by shipping NXOpen Python jobs into a visible NX session through the file-queue dispatcher of the 08_NX_API toolkit. Use for NX, NX Open, NXOpen Python journals, ugraf/run_journal, .prt parts, modelling features, drawing derivation, dimensions and tolerances, PDF or STEP export, or when a job must be watched in the NX GUI on the Windows VM. Also use to install, start, diagnose or extend the bridge itself, and to look up NXOpen API signatures before writing job code. Do not use for Ansys Mechanical, Workbench, Fusion, or CAD work that never touches NX.
---

# NX live scripting

Siemens NX has no start flag that opens an RPC server. The working mechanism is
a **dispatcher assembly that NX loads at start-up**, which polls a file queue on
NX's own message loop. Every NX API call therefore runs on the thread NX started
it on, which is the one hard requirement NXOpen imposes. Jobs are Python files
shipped from the Mac over the existing SSH/SCP connection.

The toolkit that implements this lives at
`/Users/hanne/Documents/Developer/08_NX_API`, numbered along the data flow:
`01_host/` (Mac CLI) → `02_bridge/` (dispatcher NX loads) → `03_jobs/` (what
runs inside NX) → `04_reference/` (API lookup). A project that uses it holds a
copy of the same layout.

## Prefer the visible session; batch is the fallback

The point of this setup is that the user can **watch** construction and drawing
derivation happen. Dispatch into the running GUI session by default. Use the
batch path (`run_journal.exe` via `nx_remote.py` without `--prepare-only`) only
for unattended reruns, or when the visible session is genuinely unavailable —
and say so explicitly rather than switching silently. Batch has its own failure
mode that the visible path does not: see the drafting-view trap in
[references/operations.md](references/operations.md).

## Run order

Work from the project root; host Python is `.venv/bin/python`.

```sh
.venv/bin/python 01_host/nx_dispatch.py status                 # always first
.venv/bin/python 01_host/nx_bridge_install.py                  # only if not ready
.venv/bin/python 01_host/nx_remote.py <job>.py --prepare-only  # archive + upload
.venv/bin/python 01_host/nx_dispatch.py submit --run <run-id> --wait 90
.venv/bin/python 01_host/nx_visible.py collect --run <run-id>
```

1. **Check `status` before anything else**, and again later in a long session —
   NX may have been closed or restarted meanwhile. Proceed only when `state` is
   `ready`, `session_id` is non-zero, and the heartbeat is fresh. `session_id 0`
   means no visible desktop session; the job would run invisibly or not at all.
2. `--prepare-only` prints a run id. That run directory is immutable evidence:
   never edit the archived `job.py`, the SHA-256 check will reject it.
3. **A run is submitted exactly once.** A `--wait` timeout does not cancel the
   job and does not authorise resubmission. If the wait expires, collect and
   read the state; a job may still be running in NX.
4. `collect` fetches results. Check both files: `bridge-execution.json` proves
   the dispatcher ran the source it was given; `result.json` is the job's own
   report and the only evidence it did the right thing.

Read [references/operations.md](references/operations.md) for the queue states,
the stop/restart rules, and a failure-triage table.

## Writing a job

A job is a Python file in `03_jobs/` with a global `main(job_dir)`. Three rules
decide whether it works at all:

- **Write `result.json` into `job_dir`.** Nothing else counts as proof it ran.
- **Never let an exception escape.** NX answers one with a modal dialog that
  blocks its message loop and stalls the dispatcher until a human clicks OK.
  Catch everything and report it inside `result.json`.
- **Give every part a name unique to the run.** The session outlives one job,
  and `NewDisplay` fails once a part of that name is loaded.

Start from [assets/job-template.py](assets/job-template.py); it already has the
correct shape. The full contract, including pacing for a watchable run and undo
marks per agent step, is in [references/job-contract.md](references/job-contract.md).

## Look the API up; do not recall it

`04_reference/NXOpen.xml` is the version-matched reference from the licensed
installation. Search it before writing calls:

```sh
.venv/bin/python 04_reference/nx_api_lookup.py CreateCylinderBuilder
```

It is a substring match on member names, so it only answers when the class name
is already roughly known. It also carries two things worth reading in the hit:
the **license requirements** and any **deprecation** note for that member —
both fail at runtime otherwise.

The XML documents **.NET** signatures while jobs are **Python**. That gap is the
main source of plausible, non-running code. The systematic differences —
properties instead of `Get`/`Set`, getters and setters under different names,
flattened enum paths, `out` parameters returned as tuples, mandatory `Destroy()`
on builders, expression strings instead of numbers — are listed in
[references/nxopen-python-notes.md](references/nxopen-python-notes.md). When in
doubt, a signature copied from a job that has actually run in this NX version
beats a translated .NET signature.

For whole tasks rather than single calls, read
[references/verified-recipes.md](references/verified-recipes.md) **first**. It
carries the working sequences for sketch-based modelling, threaded holes,
drawings from a company sheet template, dimensions with ISO fits, surface finish
symbols and PDF export — and, just as usefully, the routes that do not work, so
they are not tried again. Its opening section is the trap that has cost the most
time so far: several builders default `Tolerance` to `0.0`, commit happily, and
fail only later — on re-opening the feature, or with an error message that names
something else entirely.

## Evidence, not assumption

- **API success is not visual acceptance.** A drawing can export as an empty
  frame with dimension lines and no contour, and every call still returns
  cleanly. Before accepting a drawing, inspect the PDF for contours, dimension
  association, tolerance signs and layout, or make the job assert what it
  produced (`IsOutOfDate is False`, non-empty `AskVisibleObjects()`).
- **Let the job check its own numbers.** A dimension can attach to the wrong
  geometry and still return a value that looks reasonable — a diameter
  associated to circular edges instead of the cylindrical face reports the axial
  distance. Compare `dim.ComputedSize` against the nominal in the job and report
  both, so a wrong association is a failed run rather than a wrong drawing.
- **Read NX's syslog when an exception is too terse to act on.** The newest
  `*.syslog` in `%TEMP%` carries the real message; that is how a bare
  `Tolerance error` was traced to its cause.
- Report the layer that failed — SSH, VM, dispatcher, queue, hash check, NX API,
  job logic — instead of a generic failure.
- Do not claim a run succeeded from the absence of an error. Read `result.json`.

## Safety and scope

- Do not operate NX dialogs, or play a journal by hand, while a dispatched job
  is running. The dispatcher pauses on `IsJournalRunning`, and the queue stalls.
- A running job cannot be paused or cancelled. Split a long construction into
  several small jobs and inspect NX between them instead.
- Restarting NX is required after changing the dispatcher — NX holds the loaded
  assembly. Do not restart the user's NX session without asking, and never when
  it may hold unsaved work.
- Do not open a listening port. The transport is the existing SSH/SCP
  connection; keep the SHA-256 check and the project-directory confinement.
- `NXOpen.xml` is licensed vendor documentation. It stays out of Git and off
  any external service.
- Do not change scheduled tasks, environment variables, or the NX installation
  during an engineering task without the user's authorization.

Why this architecture and not NX Remoting, `USER_STARTUP`, `PlayDotNetJournal`,
`#nx: threaded`, or the public NX MCP projects:
[references/bridge-architecture.md](references/bridge-architecture.md). Read it
before proposing a redesign — every one of those was tried or evaluated.
