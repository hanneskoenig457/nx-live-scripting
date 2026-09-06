# NX Open setup

Goal: drive Siemens NX from the Mac command line while the work happens in a
**visible** NX session on the Windows VM, so construction and drawing derivation
can be watched as they happen. The first application was the test specimen of
the sibling project `10_Online_Machining`; this directory holds the reusable
layer underneath it.

## Status 2026-09-05

The visible path works end to end. A single command starts NX; NX loads the
dispatcher by itself; jobs submitted from the Mac execute in that session on the
NX main thread and their results are collected back.

Verified in run `20260905T211411Z-4db4f56d`: a Python job dispatched from the
host built three features step by step in NX process 13032, **desktop session 1**,
each with its own undo mark, and the result was collected on the Mac.

## How the automatic load works

NX loads libraries from the `startup` folder of a directory listed in the file
named by `UGII_CUSTOM_DIRECTORY_FILE`, and calls the entry point `ufsta`. This
accepts managed NX Open assemblies, so no native shim and no compiler install
are needed. Two details decide whether it works:

- **`ufsta` must return `int` or `string`.** A `void` one is refused with
  *"Found method, but return type is not an integer or string"*, followed by
  *"Cannot find method ufsta in image"* in the NX syslog.
- **`USER_STARTUP` is the wrong mechanism here.** It loads a *native* DLL and
  resolves `ufsta` as an exported C symbol, so a .NET assembly fails with
  *"Library is missing required entry point"*. It would need the NX Open C++
  component (`UGOPEN`, not installed) plus a C++ compiler (none on the VM).

`ugraf.exe -nx <journal>` is not an alternative: NX starts and ignores the file.
`run_journal.exe -help` lists every journal option; the GUI has none.

## Commands

Run from the project root; host Python is always `.venv/bin/python`.

```sh
.venv/bin/python 01_host/nx_bridge_install.py                 # build dispatcher, start visible NX
.venv/bin/python 01_host/nx_dispatch.py status                # dispatcher state and heartbeat
.venv/bin/python 01_host/nx_remote.py <job>.py --prepare-only # archive and upload a job
.venv/bin/python 01_host/nx_dispatch.py submit --run <run-id> --wait 90
.venv/bin/python 01_host/nx_visible.py collect --run <run-id>
.venv/bin/python 01_host/nx_dispatch.py stop                  # end the dispatcher loop
```

`nx_bridge_install.py` compiles `02_bridge/VisibleBridge.cs` in the VM and starts
NX through an on-demand scheduled task with the logged-in user's interactive
token and limited privileges. It stores no password and has no timed trigger.
Windows must have the user logged in. Restarting NX is required after changing
the dispatcher, because NX holds the loaded assembly.

## Why the dispatcher is C# and the jobs are Python

Only the dispatcher has to be a managed assembly: NX's start-up hook loads
libraries, and there is no equivalent hook for a Python script. It is about two
hundred lines that rarely change.

The jobs are Python. The dispatcher runs them with
`Session.Execute(path, "", "main", new object[] { runDirectory })`, which accepts
`.py` files and invokes a global function in NX's own embedded interpreter. Two
alternatives were tried and rejected:

- `JournalManager.PlayDotNetJournal` takes only a C#/VB **source**, compiles it
  against **.NET 8** while the dispatcher runs on .NET Framework — failing as
  *"Resolve failed: System.Runtime, Version=8.0.0.0"* — and **reports success
  even when the journal throws**.
- Loading a compiled job assembly by reflection works, but forces every job to
  be C#, and `Assembly.LoadFrom` silently returns the first job loaded in the
  session because all jobs share one assembly identity.

The run directory is passed as an **argument**, not through the environment: NX
freezes `os.environ` when it starts the interpreter, so a variable set by the
dispatcher never reaches the script.

## Job contract

A job is a Python file in `03_jobs/` with a global `main(job_dir)`. It **must
write `result.json` into `job_dir`**: that file is the only proof it ran.
`bridge-execution.json`, written by the dispatcher, records identity and source
hash but not correctness.

A job **must not let an exception escape**. NX answers one with a modal dialog
that blocks its message loop, and with it the dispatcher, until someone clicks
OK. Catch it and report it in `result.json` instead; see `visible_probe.py`.

Give any new part a name unique to the run. The NX session outlives a single
job, and `NewDisplay` fails with *"File already exists"* when a part of that
name is already loaded.

Jobs run with the logged-in user's privileges. The transport is the existing
SSH/SCP connection; no additional listening port is opened. The dispatcher
accepts only a `job.py` inside the project directory in the VM and verifies its
SHA-256 against the request. Requests are uploaded before an atomic rename to
`.ready`, claimed by renaming to `.running`, and never retried automatically.
Requests queued before the session started are quarantined as `.stale`. A
host-side wait timeout neither cancels the job nor authorises resubmission.
Do not operate NX dialogs while a dispatched job is running.

## Batch path (secondary)

`01_host/nx_remote.py <job>.py` without `--prepare-only` runs a Python journal
through `run_journal.exe`, headless and unwatchable. It is kept for unattended
reruns. One trap is documented in `03_jobs/acceptance.py`: a drafting view must
be updated **immediately after creation**. Updating it only after dimensions are
attached leaves it out of date in batch, and the PDF then exports dimension
lines over an empty frame with no part contour — silently. The journal asserts
`IsOutOfDate == False` and a non-empty `AskVisibleObjects()` before exporting.

Verified batch run `20260905T201118Z-44b7601a`: contour, both tolerance signs and
a 14081-byte PDF identical in size to the interactive result.

## Source and evidence

- `02_bridge/VisibleBridge.cs`: the dispatcher; loaded by NX at start-up.
- `03_jobs/visible_probe.py`: smoke test for the dispatcher.
- `03_jobs/live_demo.py`: paced step-by-step construction in the visible session.
- `03_jobs/acceptance.py`: batch capability test; test geometry, not production CAD.
- `01_host/nx_bridge_install.py`, `01_host/nx_dispatch.py`, `01_host/nx_remote.py`,
  `01_host/nx_visible.py`: host side.
- `runs/nx/<run>/`: immutable prepared source and manifest; fetched output in `remote/`.
- `04_reference/NXOpen.xml`: private installed Siemens API reference, ignored by Git.

API success and visual acceptance are separate. Inspect the PDF for actual
contours, dimension association, tolerance signs and layout before accepting a
drawing. STEP export, native GD&T, parameter-change propagation and reopen
validation remain outstanding.

## Watching a job run

A job executes on the NX main thread as one uninterrupted block, so NX repaints
only when the job tells it to. Without pacing a short job finishes faster than
the eye follows. `live_demo.py` shows the pattern for a watchable run: one undo
mark per step, `view.UpdateDisplay()` after each feature, and a short pause.
Remove the pauses for unattended runs.

The session stays open between jobs, so a construction can also be dispatched as
several small jobs and inspected in NX between them. There is no way to pause a
running job for confirmation, and no way to cancel one: while it runs, the NX
window is busy.

## VM specifics

The VM is ARM64 (Parallels on Apple Silicon) and NX is an x64 process. The x64
.NET runtimes live in `C:\Program Files\dotnet\x64`, which the NX loader does not
search, so `02_bridge/start-visible.cmd` sets `DOTNET_ROOT` accordingly.
