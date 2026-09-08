# Operating the bridge

All commands run from the project root. Host Python is `.venv/bin/python`.

## Commands

```sh
01_host/nx_dispatch.py status                    # dispatcher state and heartbeat
01_host/nx_bridge_install.py                     # build dispatcher, start visible NX
01_host/nx_visible.py start                      # start visible NX without rebuilding
01_host/nx_visible.py status                     # NX processes and their session ids
01_host/nx_remote.py <job>.py --prepare-only     # archive + upload, prints the run id
01_host/nx_dispatch.py submit --run <id> --wait 90
01_host/nx_visible.py collect --run <id>
01_host/nx_check_result.py --run <id> [--gate-pdf]  # schema/rules/dims/hash gate; --gate-pdf needs pdftoppm+PIL+numpy
01_host/nx_dispatch.py stop                      # end the dispatcher loop
01_host/nx_remote.py <job>.py                    # batch fallback via run_journal.exe
04_reference/nx_api_lookup.py <term> [<term> …]  # search the NXOpen .NET reference
```

`nx_bridge_install.py` compiles `02_bridge/VisibleBridge.cs` in the VM with the
.NET Framework `csc.exe` and starts NX through an **on-demand** scheduled task
running with the logged-in user's interactive token and limited privileges. It
stores no password and has no timed trigger. Windows must have the user logged
in — without an interactive session there is nothing to be visible in.

## Reading `status`

```json
{"state": "ready", "pid": 13032, "session_id": 1, "thread_id": 1,
 "heartbeat": 1757110451.0, "details": "idle"}
```

| Field | What it must say before submitting |
| --- | --- |
| `state` | `ready`. `paused` means a journal is running in the GUI; `stopped` means the loop ended; `error` carries the exception in `details`. |
| `session_id` | Non-zero. `0` is Windows Session 0 — no visible desktop, the whole point is lost. |
| `heartbeat` | Within ~60 s of now. A stale heartbeat means the timer died, not that the network is slow: a round trip here is under a second. |

`nx_dispatch.py submit` refuses to queue anything when these do not hold. Do not
work around that check.

**Do not call `status` standalone immediately before every `submit`.** `submit`
already performs this exact check and refuses cleanly if the bridge isn't
ready — a separate `status` call right before it re-answers a question `submit`
is about to answer anyway. In a full task session this habit alone measured
19 redundant `status` calls out of 25 total (transcript analysis, 2026-09-08,
99_4/99_5 sessions on the same task) — about 9% of that session's total token
cost for zero additional safety, since the exact same guard already lives
inside `submit`. Call `status` standalone only:

- once at the start of a session,
- right after a restart (`nx_bridge_install.py`) to confirm recovery,
- or when actively diagnosing why a request is stuck (see the triage table
  below) — not as a reflex before a routine dispatch.

## Queue semantics

A request file moves by atomic rename: `.upload` → `.ready` → `.running` →
`.done` or `.failed`. Requests found at start-up that were queued before this
session began are quarantined as `.stale` — that session never accepted them.

- **One submission per run.** `nx_dispatch.py` writes `dispatch.json` into the
  run directory and refuses a second attempt. Inspect the state; do not replay.
- **A `--wait` timeout is not a cancellation.** The job may still be running in
  NX. Collect, read what is there, and wait longer if needed.
- **There is no cancel.** While a job runs, the NX window is busy.

## After collecting

Two files, two different claims:

- `bridge-execution.json` — `execution_ok`, pid, session id, thread id, source
  SHA-256, start/finish, and any dispatcher-level error. It proves *what* ran.
- `result.json` — the job's own report. It is the only evidence the job did the
  *right* thing. `nx_visible.py collect` exits non-zero when it is missing or
  when `ok` is not `true`.

`outcome.json` in the local run directory records `visual_validation: pending`.
That is deliberate: API success and visual acceptance are separate. Open the PDF
or the part before calling a drawing good.

## Failure triage

Name the failing layer instead of reporting a generic error.

| Symptom | Layer | Action |
| --- | --- | --- |
| `ssh` refuses / times out | VM or SSH | Is the Parallels VM running and the user logged in? |
| `status` cannot read `bridge-status.json` | Dispatcher never loaded | Check `bridge-loaded.log` in the VM project directory, then the NX syslog for the `ufsta` messages. |
| `bridge-loaded.log` exists, no status file | Startup threw | `bridge-errors.log` has the exception; `SessionId == 0` is the usual cause. |
| `state: paused` | A journal is running in the GUI | Wait, or ask the user to finish it. Do not force. |
| `state: error` | Tick or job failure | `details` plus `bridge-errors.log`. |
| Request stuck at `.ready` | Timer not ticking | Stale heartbeat confirms it; restart NX via `nx_bridge_install.py`. |
| Request at `.failed` | Hash mismatch, path outside the project, or wrong filename | The archived source was modified, or the job is not `job.py` inside the project directory. |
| `execution_ok: false` | Exception escaped into NX | A modal dialog may be waiting in the VM — the queue stalls until it is dismissed. |
| `result.json` missing | Job died before writing | It did not follow the contract; fix the job, do not resubmit blindly. |
| SEHException in `AddToDeleteList([sheet])` (syslog: `jam.cxx ... reallocate var for arg 1`) | NX marshaller, sheet purge | Sheet deletion via the delete list can crash natively (once, after dim-deletes/pref-sets/saves on that sheet; mechanism unknown). Prefer uniquely named sheets (`SetName`) over purge. Run `20260907T152337Z-06bc356a`. |
| NX modal dialog visible | Anything | Nothing proceeds until it is closed. Ask the user. |
| Save dialog `Save CGM` (sheets not displayed) | Harmless preview cache | `Yes` — CGM is only the cached 2D sheet preview (Computer Graphics Metafile), regenerated on open; model + sheet data save normally. Avoid it: `sheet.Open()` before `part.Save()` in jobs. Run `20260907T135712Z-97f0bb7f`. |

## Reading NX's own error text

NXOpen exceptions are short; the syslog carries the real message. The newest
`*.syslog` in `%TEMP%` is the session's:

```python
import os
from pathlib import Path

temp = Path(os.environ.get('TEMP', r'C:\Windows\Temp'))
newest = sorted(temp.glob('*.syslog'), key=lambda p: p.stat().st_mtime)[-1]
tail = newest.read_text(encoding='utf-8', errors='replace').splitlines()[-60:]
```

That is how a bare `Tolerance error` was traced to `+++ Invalid tolerance` from
`revolve_builder_definitions.c`
([api-modelling.md §1](api-modelling.md#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero)).
Put this in the failure path of a **probe** job, not in production jobs.

## Diagnosing a part

Two reusable diagnostics live directly in `03_jobs/` (the rest are archived
probes under `03_jobs/probes/`).

**`part_open_probe.py` — a part that will not open.** `OpenDisplay` returns
`None` for the part instead of raising; the load status carries the reason:

```python
opened = session.Parts.OpenDisplay(path)
part, status = opened[0], opened[1]
for i in range(status.NumberUnloadedParts):
    print(status.GetPartName(i), status.GetStatusDescription(i))
# -> "Corrupt data found when loading an OM file"
```

A part corrupted this way is **not repairable from the API** — rebuild it, which
is the argument for keeping the model job repeatable in the first place. The
usual cause is a template sheet instantiated without
`SetTemplateInstantiationIsComplete(True)`
([api-drafting.md §1](api-drafting.md#1-sheet-from-the-company-template)).

**`feature_reedit_probe.py` — features that commit but cannot be re-opened.**
It re-opens the builder of every feature and reports which ones refuse: the API
equivalent of double-clicking each entry in the part navigator, and the fastest
way to catch the tolerance trap before a part is handed on. Two details it had
to learn:

- **Map on `FeatureType`, not on the journal identifier.** A hole package names
  its children after itself: `THREADED HOLE(7)` is the package,
  `THREADED HOLE(7:1A)` the drilled hole, `THREADED HOLE(7:1A:1A)` the thread —
  three different feature types under one name.
- **A colon in the journal identifier marks a feature internal to another one.**
  Those are edited through their parent and answer *"First parameter is invalid.
  Expecting … found …"* if asked directly. Skip them; a builder that refuses an
  internal child is not a defect. (The same rule applies when deleting features
  — matching `:` children breaks the delete-count assert.)

Verified against the specimen part on 2026-09-06: twelve features, zero re-edit
failures, sketches reported honestly as unmapped.

## Restart rules

NX holds the loaded assembly, so **any change to `VisibleBridge.cs` needs an NX
restart**. `nx_bridge_install.py` requests one. Never restart the user's NX
session unasked, and never when it may hold unsaved work.

Start visible NX only through the `OnlineMachining-NX-Bridge` task
(`nx_bridge_install.py`, or `schtasks /Run /TN OnlineMachining-NX-Bridge`),
which runs `02_bridge/start-visible.cmd` with the project-local
`custom_dirs.dat`.

`nx_visible.py start` uses a different task that launches `ugraf.exe -nx`
directly, **without** `UGII_CUSTOM_DIRECTORY_FILE` / `DOTNET_ROOT`. NX opens
fine and looks healthy, but the dispatcher never loads: no `ufsta` line in the
session syslog, no new `bridge-loaded.log`, a frozen `bridge-status.json`.
Observed 2026-09-06 after a crash — new PID, responsive Discovery Center, zero
dispatcher signs. Kill an env-less instance first if one is running (it holds no
dispatcher state; confirm no unsaved work). Verified: Bridge-task start → new
PID, fresh heartbeat, `ready`.

`nx_dispatch.py stop` writes a `bridge-stop` marker; the dispatcher deletes it,
stops its timer and reports `stopped`. NX itself stays open. Getting the loop
back requires restarting NX.

## The batch trap

`nx_remote.py <job>.py` without `--prepare-only` runs the job as a Python journal
through `run_journal.exe` — headless, unwatchable, and with one documented trap:
a drafting view must be updated **immediately after creation**. Updating it only
after dimensions are attached leaves it out of date in batch, and the PDF then
exports dimension lines over an empty frame with no part contour, silently.
`03_jobs/acceptance.py` asserts `IsOutOfDate == False` and a non-empty
`AskVisibleObjects()` before exporting; keep that guard in any job that exports.
