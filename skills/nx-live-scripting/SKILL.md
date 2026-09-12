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
runs inside NX) → `04_reference/` (API lookup). **Correction, 2026-09-09:**
a project no longer holds a copy of that layout — it keeps only `03_jobs/`
(jobs), `runs/` (evidence) and its deliverables, and points the toolkit at
itself via `NX_PROJECT_ROOT` (unset = work directly in the toolkit). Verified
with `20260909T061426Z-913deadf`, dispatched end to end from a thin project.

## Decision ladder: high level first

After a short plan, classify the required NX actions before writing code:

1. If the task fits the certified declarative surface, call the single
   `nx_run_plan` MCP tool. If that MCP server is not registered in the current
   host, use its equivalent CLI, `01_host/nx_plan.py`; missing MCP registration
   is not a reason to skip the high-level layer.
2. If the high-level surface cannot express the task or its result is
   insufficient, compose a normal job from the **verified**
   `SNIPPETS-modelling.md` / `SNIPPETS-drafting.md` examples.
3. Only when those verified low-level examples are also insufficient, look up
   and develop new narrowly scoped NXOpen code according to the source order
   below. Probe it before treating it as reusable.

The high-level v1 surface creates a new part and supports an XZ sketch,
lines/rectangles, finishing the sketch, a new-body extrusion, object lists,
view fit and save. It intentionally does not yet edit an existing part, create
drawings, revolve, cut, add holes/threads, export STEP, or accept arbitrary
Python. Read [references/high-level-tools.md](references/high-level-tools.md)
for the exact schema, invocation, atomic rollback and failure/fallback rules.

Do not split one dependent construction into several high-level runs: object
references are plan-local, and one atomic plan is both faster and safely
rollbackable. A transport failure is not a reason to switch to low-level code,
because both layers use the same visible dispatcher.

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
.venv/bin/python 01_host/nx_remote.py <job>.py --prepare-only  # lints, archives, uploads
.venv/bin/python 01_host/nx_dispatch.py submit --run <run-id> --wait 90
.venv/bin/python 01_host/nx_visible.py collect --run <run-id>
```

0. `--prepare-only` runs `01_host/nx_lint.py` on the job first and refuses to
   upload on a lint ERROR (warnings print but don't block) — it catches the
   import-namespace-vs-class mistake, a missing `Tolerance` on a new builder,
   and a missing `main(job_dir)` **before** a dispatch cycle is spent on them.
   `--no-lint` forces an upload past a false positive.
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

## Look the API up; do not recall it — verified Python first, XML last

Five sources exist, in **strict cost order**. Do not start at the bottom:

1. **[SNIPPETS-modelling.md](references/SNIPPETS-modelling.md) /
   [SNIPPETS-drafting.md](references/SNIPPETS-drafting.md)** — verified,
   copy-paste Python for calls that have actually run against this NX version.
   Check here **first**, always, before any lookup tool.
2. **Local NXOpen Python Reference Guide** — the canonical public Python API
   reference at `04_reference/nxopen_python_ref/index.html`. A human uses its
   Doxygen search field; an agent queries that exact local Doxygen index, never
   `rg` over the mirrored HTML tree:

```sh
.venv/bin/python 04_reference/nxopen_python_search.py CreateCylinderBuilder
```

   A missing Guide hit is evidence against the proposed Python name, not a
   reason to guess a plausible factory call. Use the 2506.3001 Python stubs
   only as a secondary reading aid for malformed Doxygen enum tables; after a
   value-for-value comparison, the local mirror displays a labelled repair
   table for affected pages. The stubs do not replace the Guide and omit its
   `NXOpen.UF` coverage.
3. **[api-modelling.md](references/api-modelling.md) /
   [api-drafting.md](references/api-drafting.md)** — the narrative layer-4
   files, when a snippet doesn't cover your exact case or you need the *why*
   behind a trap.
4. **Community sources** (NXJournaling, GitHub, Stack Overflow) for genuinely
   new territory neither of the above covers. Still needs translating to
   Python and a cheap probe-verified dispatch before being trusted — never
   copy it in as-is, and it carries the same version-drift risk as the XML
   below (code for a different NX release can look right and still not run).
5. **`04_reference/NXOpen.xml`** — the version-matched .NET reference. **Last
   resort only**, for a member that appears in none of the above:

```sh
.venv/bin/python 04_reference/nx_api_lookup.py CreateCylinderBuilder
```

It is a substring match on member names, so it only answers when the class name
is already roughly known, and it matches across the **entire** NXOpen API, not
just your area — a broad term like `Limits` alone matches ~150 members
(~32,000 characters, ~8,000 tokens) in one call, nearly all unrelated to what
you're building. The tool now caps output at 20 likely matches by default
(`--all` for the rest) and prints a note when your term already appears in a
SNIPPETS/api-\*.md file — read that note; it is pointing at a cheaper, already-
verified answer. **Pass several narrowing terms together in one call** (they
combine as OR) rather than making several separate broad single-term calls
hunting for the same answer — that exact pattern burned 40,000+ tokens
re-deriving a revolve's axis/Limits signature that was already sitting solved,
verified, in SNIPPETS-modelling.md (2026-09-07, a fresh session that skipped
straight to the XML without checking the snippet first).

Two things are worth reading in every hit regardless of source: the **license
requirements** and any **deprecation** note for that member — both fail at
runtime otherwise.

The XML documents **.NET** signatures while jobs are **Python**. That gap is the
main source of plausible, non-running code. The systematic differences —
properties instead of `Get`/`Set`, getters and setters under different names,
flattened enum paths, `out` parameters returned as tuples, mandatory `Destroy()`
on builders, expression strings instead of numbers — are listed in
[references/nxopen-python-notes.md](references/nxopen-python-notes.md). When in
doubt, a signature copied from a job that has actually run in this NX version
beats a translated .NET signature.

For whole tasks rather than single calls, go to the layer-4 file for what you
are building — [references/api-modelling.md](references/api-modelling.md) for
geometry, [references/api-drafting.md](references/api-drafting.md) for sheets,
views, dimensions and annotations. Each opens with an index table (what you
want → entry point → trap) and closes with the routes that are known **not** to
work, so they are not tried again. For a task already covered there, read
[references/SNIPPETS-modelling.md](references/SNIPPETS-modelling.md) /
[references/SNIPPETS-drafting.md](references/SNIPPETS-drafting.md) first —
the same verified calls with the run-id narrative stripped out; drop back to
the full layer-4 file only when a snippet fails or you need the *why*.

The single most expensive trap, before anything else: several builders default
`Tolerance` to `0.0`, commit happily, and fail only later — on re-opening the
feature, or with an error message that names something else entirely.

## Knowledge layers: one transport layer, three knowledge layers

Layer 1 is how jobs reach NX and applies to every job. Layers 2–4 are the
engineering knowledge behind drawing work, from the norm down to the call.
Read top-down, extend bottom-up.

| Layer | Files | Holds |
| --- | --- | --- |
| **1 Transport** | this file, [high-level-tools.md](references/high-level-tools.md), [operations.md](references/operations.md), [job-contract.md](references/job-contract.md), [bridge-architecture.md](references/bridge-architecture.md) | How high-level plans and low-level jobs reach NX, what they must satisfy, how to diagnose the bridge |
| **2 Norm knowledge** | [norm-knowledge.md](references/norm-knowledge.md) | What a standard element *is* and which numbers its norm fixes. Placeholder + entry schema; fill one element per session from the norm original |
| **3 Rules** | [dimensioning-rules.md](references/dimensioning-rules.md) | How to dimension norm-correctly, independent of NX: placement, order, symbols, fits, surface, edges, checklists. Part-specific values stay with the project |
| **4 API** | [api-modelling.md](references/api-modelling.md) (geometry), [api-drafting.md](references/api-drafting.md) (drawing), [nxopen-python-notes.md](references/nxopen-python-notes.md) (the .NET↔Python gap), [SNIPPETS-modelling.md](references/SNIPPETS-modelling.md) / [SNIPPETS-drafting.md](references/SNIPPETS-drafting.md) (same calls, code-only) | Calls that have **actually run**, each with its run id or probe, plus the dead ends. Unlisted paths are unverified, not impossible |

**Read rules before API.** Layer 3 first, layer 4 second — API-first reading
optimises mechanism over conformity.

### Where a new finding goes

Write findings into [FINDINGS-INBOX.md](FINDINGS-INBOX.md) while you work, and
**empty that file before the task is finished**: each entry moves into the
matching layer (new element → 2, new rule → 3, new working sequence → 4 with a
run id and `result.json`) or is deleted as noise. Findings true only for this
part belong to the project, not to this skill.

Two filing rules keep the layers usable:

- **Edit the existing section; never append a new one.** Appending is what
  turned the former `verified-recipes.md` into a chronological pile no layer
  could absorb.
- **A contradiction corrects the old text**, with a dated footnote carrying the
  evidence. Two versions standing side by side misinform whoever reads only the
  first.

A mapping without a run behind it does not go in.

## Evidence, not assumption

- **API success is not visual acceptance.** A drawing can export as an empty
  frame with dimension lines and no contour, and every call still returns
  cleanly. Before accepting a drawing, inspect the PDF for contours, dimension
  association, tolerance signs and layout, or make the job assert what it
  produced (`IsOutOfDate is False`, non-empty `AskVisibleObjects()`).
  **A rendered view that looks right is not the same claim as "shows the
  right thing"** — `IsOutOfDate is False` + visible objects only proves a
  view rendered *something*; a base view can be fresh, populated, and still
  be the wrong end of the part (2026-09-07: 'Right' showed a plain chamfered
  end while the feature being checked sat at the other end, and the render
  alone didn't catch it — a one-line table check would have, see
  [api-drafting.md §3](references/api-drafting.md#3-view-placement)). When a
  fact is checkable from data the job already has (a feature's known
  position, a fixed view-direction table), assert it in the job instead of
  reading a screenshot — reserve images for what genuinely has no cheap
  programmatic check.
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
