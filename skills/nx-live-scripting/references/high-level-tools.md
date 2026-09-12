# High-level NX plans

Use this surface after a short task plan and before writing a custom NXOpen
job.  It packages several dependent actions into one atomic invocation of the
existing visible-session dispatcher.  It never accepts Python source.

The operation vocabulary is inspired by the certified tool surface of the
MIT-licensed [DreamEnding/NX_MCP](https://github.com/dreamending/nx_mcp).
Its socket/batch bridge and unverified legacy calls are deliberately not used.
The implementation here translates the declarative operations to calls already
verified by this toolkit's `SNIPPETS-modelling.md`.

## One MCP tool

The server exposes one tool, `nx_run_plan(operations, wait_seconds=90)`. Start
it over stdio with the project's venv. For Codex, register the durable main
checkout (not a generated Codex worktree):

```sh
codex mcp add nx-live-scripting -- \
  /Users/hanne/Documents/Developer/08_NX_API/.venv/bin/python \
  /Users/hanne/Documents/Developer/08_NX_API/01_host/nx_mcp_server.py
codex mcp list
```

The equivalent configuration is:

```toml
[mcp_servers.nx-live-scripting]
command = "/Users/hanne/Documents/Developer/08_NX_API/.venv/bin/python"
args = ["/Users/hanne/Documents/Developer/08_NX_API/01_host/nx_mcp_server.py"]
cwd = "/Users/hanne/Documents/Developer/08_NX_API"
enabled = true
enabled_tools = ["nx_run_plan"]
startup_timeout_sec = 10
tool_timeout_sec = 660
default_tools_approval_mode = "writes"

[mcp_servers.nx-live-scripting.tools.nx_run_plan]
approval_mode = "writes"
output_token_limit = 30000
```

The 660-second client timeout is deliberately longer than the plan executor's
600-second maximum. An MCP timeout does not cancel an already submitted NX run.
After changing MCP configuration, start a new Codex task/client session so its
tool inventory is rebuilt; registration cannot inject a tool into a task that
is already running.

When the MCP server is not registered in the current agent host, use the same
executor through the CLI rather than dropping straight to custom code:

```sh
.venv/bin/python 01_host/nx_plan.py examples/nx-high-level-box.json --wait 90
```

For an explicit MCP protocol smoke test (stdio client → server → tool call):

```sh
.venv/bin/python examples/call_nx_mcp.py examples/nx-high-level-box.json --wait 90
```

Both paths validate before upload, check the visible bridge, prepare one
immutable run, submit it exactly once, collect it, and return both
`bridge-execution.json` and `result.json` evidence.
The executor selects the static runner from the toolkit via
`nx_remote.py --toolkit-job`, so it also works when `NX_PROJECT_ROOT` points at
a thin project that contains only its own jobs and evidence.

## Certified operations (v2)

DreamEnding's certified server registers **16 separate MCP tools**. This
toolkit registers **one MCP tool** whose plan accepts those same **16 operation
names**. They are locally reimplemented against this toolkit's verified
recipes; DreamEnding's socket bridge and its `DexManager` STEP path are not
used. Thus 16 operations still means one locally registered MCP tool.

| Operation | Required args | Optional args / output id |
| --- | --- | --- |
| `nx_status` | — | may be used alone or around one stateful plan |
| `nx_create_part` | `path` (relative `.prt`) | `units=mm`; optional `id` |
| `nx_open_part` | `path` (relative existing `.prt`) | opens a run-local hashed copy |
| `nx_save_part` | — | terminal; only status may follow |
| `nx_close_part` | — | `save=true`; terminal; only status may follow |
| `nx_export_step` | `path` (relative `.stp`/`.step`) | saves the run copy, exports AP214, terminal |
| `nx_list_sketches` | — | — |
| `nx_list_bodies` | — | — |
| `nx_list_features` | — | — |
| `nx_create_sketch` | operation `id` | `plane=XZ`, `name=<id>` |
| `nx_sketch_line` | `sketch`, `start{x,y}`, `end{x,y}` | — |
| `nx_sketch_rectangle` | `sketch`, `corner1{x,y}`, `corner2{x,y}` | — |
| `nx_finish_sketch` | `sketch` | — |
| `nx_extrude` | `sketch`, positive `distance` | `reverse=false`; optional `id` |
| `nx_undo` | — | undoes the last model mutation in this plan |
| `nx_fit_view` | — | — |

An operation's `id` is a plan-local reference, not a persistent NX object id.
For example, an `nx_create_sketch` with `"id": "profile"` is referenced by
later operations as `"sketch": "profile"`. A stateful plan begins with exactly
one `nx_create_part` or `nx_open_part` as its first non-status operation. Only
XZ is exposed because that is the principal-plane recipe verified locally.
Other planes are a reason to use the fallback ladder, not a reason to guess
another enum.

`nx_open_part` resolves its path below `NX_PROJECT_ROOT` (the toolkit root when
the variable is unset), computes SHA-256 before any remote side effect, archives
the file under the immutable run's `inputs/`, records hash and size in
`request.json`, and uploads it. The NX runner verifies the same hash and opens a
run-id-suffixed copy. Save, export and close therefore never mutate the source
file named by the caller.

NX treats an already loaded part with the same leaf name as a collision even
when its directory differs. The runner therefore inserts the immutable run id
before the requested `.prt` suffix and reports both `requested_path` and the
actual `path`. Do not remove that suffixing step: separate high-level calls
share one long-lived visible NX session.

`nx_save_part`, `nx_export_step`, and `nx_close_part` are terminal operations;
only a read-only `nx_status` may follow. This prevents a later failed model step
from occurring after persistent output. `nx_export_step` saves the run copy and
uses the verified standalone `STEP214UG/step214ug.exe` path; the known silent
`DexManager.CreateStepCreator` dead end is not used.

`nx_undo` uses the mark and Python-side reference snapshot captured before the
last model mutation in the same plan. It can be repeated while mutation history
remains, but intentionally does not reach into earlier MCP calls.

Examples: [`nx-high-level-box.json`](../../../examples/nx-high-level-box.json)
(v1-compatible save) and
[`nx-high-level-undo-export.json`](../../../examples/nx-high-level-undo-export.json)
(v2 undo plus STEP).

## Verified evidence

Visible MCP stdio run `20260912T185302Z-9cb4c6ea` is the production-contract
acceptance run: MCP and the NX runner both reported `contract_version: 1`.
`nx_run_plan` created the uniquely named part, XZ datum/sketch and four profile
lines, committed one Extrude/body, listed one body and four features, fitted the
view and saved. `bridge-execution.json` reports `execution_ok: true`, NX PID
10924, desktop session 1, main thread 1 and the archived source SHA-256;
`result.json` reports all nine operations `ok: true`.

Earlier visible MCP stdio run `20260912T113647Z-60d37433` is the initial v1
acceptance run with the same successful geometry and evidence chain.

The immediately preceding visible MCP run `20260912T113535Z-db64f032` exposed
the long-lived-session leaf-name collision (`NXException 1020004`, “File
already exists”) even though the directory was unique. It is the evidence for
the mandatory run-id suffix described above; that failed run was not
resubmitted. Batch run `20260912T104646Z-82000717` separately verified the same
NXOpen construction sequence, and diagnostic batch run
`20260912T104553Z-5eeb703b` verified `rollback.ok: true` after a later step
failed.

Contract-v2 visible evidence:

- `20260912T194649Z-7524295e`: status-only MCP run after the final v2 change;
  `Session.GetEnvironmentVariableValue("UGII_VERSION")` reported `v2506`, with
  no active part, from NX PID 10924 / desktop session 1 / main thread 1.
- `20260912T193745Z-9989edc7`: rectangle created, undone, rebuilt and extruded;
  one sketch/body and four features listed; STEP214UG exit 0 produced an
  8,230-byte AP214 file with six `ADVANCED_FACE` entries and one `CLOSED_SHELL`.
- `20260912T194302Z-c723423b`: the exported run's 81,850-byte `.prt` was staged
  with SHA-256 `47e21441…65d5`, verified again inside NX, opened as a uniquely
  named copy, listed with one body, closed with `save=false`, then status
  reported no active part. Both bridge execution and job result are green.

## Failure semantics and fallback

- Validation failures occur before upload.  Unsupported intent falls through
  to the verified low-level snippets.
- Creating or opening a display part invalidates marks from the previously
  displayed part. Therefore the atomic undo boundary starts immediately after
  the unique run-local part is created or opened. A failing NX operation rolls
  back every model operation after that point while the boundary remains valid;
  the run-local container/copy remains for diagnosis. File persistence caused
  by a terminal save/export cannot be undone by an NX model mark.
  The result reports the failed layer, exception, NX code (when present),
  traceback, completed steps and rollback outcome in `result.json`.
- Transport failures do **not** justify a low-level retry: both paths use the
  same bridge.  Restore `ready`, a non-zero desktop session and a fresh
  heartbeat first.
- Never resubmit the same run after a timeout.  Collect its state exactly as for
  a low-level job.
- A high-level success is still not visual acceptance.  Use programmatic checks
  and the existing PDF/viewport rules when the task requires them.

Fallback order for unsupported or insufficient behavior:

1. `SNIPPETS-modelling.md` / `SNIPPETS-drafting.md` (working code);
2. the corresponding `api-*.md` recipe and local Python Reference Guide;
3. a narrowly scoped new low-level probe/job, then file verified findings into
   the existing knowledge layer.

## Reviewed candidates beyond the 16 — not implemented

These are already backed by local verified recipes and are plausible next
high-level operations. They require a joint scope decision before code is added:

| Candidate | Readiness | Decision needed |
| --- | --- | --- |
| `nx_revolve` | High: smart associative axis, 360° limits and mandatory tolerance are verified | profile schema and whether only new-body is allowed |
| `nx_threaded_hole` | High for the verified metric workflow | general standard/size validation versus a deliberately narrow first preset |
| `nx_measure_solid` | High and read-only: UF face types/radii plus edge circumference are verified | generic report versus expectation-driven assertions |
| `nx_extrude_cut` / `nx_keyway` | Medium: the stadium keyway and subtractive extrude work | generic cut schema, target-body references and direction/view semantics |
| `nx_create_drawing_sheet` | High mechanically with the company template | mandatory title-block fields and whether this starts a separate drawing plan |
| `nx_add_base_view` | High with explicit canned-view checks and freshness gate | safe placement/scale schema and required semantic view intent |
| `nx_set_title_block` | High for attributes plus two direct-edit cells | fixed KUP schema versus generic labels (typos silently no-op) |
| `nx_export_pdf` | High when paired with regenerate/update/assert gates | whether it is allowed only as terminal drawing validation |

Do **not** promote general dimensions, surface-finish annotations, section
views, arbitrary sheet deletion or a generic journal runner yet. Their local
knowledge files still contain open associativity gaps, a native sheet-delete
crash case, or an intentionally forbidden arbitrary-code path.
