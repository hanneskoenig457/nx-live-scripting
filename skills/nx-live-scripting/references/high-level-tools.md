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

## Certified operations (v1)

DreamEnding's certified server registers **16 separate MCP tools**. This
toolkit registers **one MCP tool** whose plan currently accepts **11 operation
names**. Those 11 names are a locally reimplemented subset of DreamEnding's 16:

- included: `nx_create_part`, `nx_save_part`, `nx_list_sketches`,
  `nx_list_bodies`, `nx_list_features`, `nx_create_sketch`, `nx_sketch_line`,
  `nx_sketch_rectangle`, `nx_finish_sketch`, `nx_extrude`, `nx_fit_view`;
- not yet certified here: `nx_status`, `nx_open_part`, `nx_close_part`,
  `nx_export_step`, `nx_undo`.

The box acceptance plan uses 9 of the 11 included operations: create part,
create sketch, rectangle, finish sketch, extrude, list bodies, list features,
fit view and save. Thus “nine steps” means nine entries inside one
`nx_run_plan` call, not nine locally registered MCP tools.

| Operation | Required args | Optional args / output id |
| --- | --- | --- |
| `nx_create_part` | `path` (relative `.prt`) | `units=mm`; optional `id` |
| `nx_create_sketch` | operation `id` | `plane=XZ`, `name=<id>` |
| `nx_sketch_line` | `sketch`, `start{x,y}`, `end{x,y}` | — |
| `nx_sketch_rectangle` | `sketch`, `corner1{x,y}`, `corner2{x,y}` | — |
| `nx_finish_sketch` | `sketch` | — |
| `nx_extrude` | `sketch`, positive `distance` | `reverse=false`; optional `id` |
| `nx_list_sketches` | — | — |
| `nx_list_bodies` | — | — |
| `nx_list_features` | — | — |
| `nx_fit_view` | — | — |
| `nx_save_part` | — | — |

An operation's `id` is a plan-local reference, not a persistent NX object id.
For example, an `nx_create_sketch` with `"id": "profile"` is referenced by
later operations as `"sketch": "profile"`.  A plan must begin with exactly
one `nx_create_part`; this keeps v1 away from accidental edits to an already
open user part.  Only XZ is exposed because that is the principal-plane recipe
verified locally.  Other planes are a reason to use the fallback ladder, not a
reason to guess another enum.

NX treats an already loaded part with the same leaf name as a collision even
when its directory differs. The runner therefore inserts the immutable run id
before the requested `.prt` suffix and reports both `requested_path` and the
actual `path`. Do not remove that suffixing step: separate high-level calls
share one long-lived visible NX session.

`nx_save_part` must be the final operation. This prevents a later failed step
from persisting a partial model before rollback can run.

The complete box example is
[`examples/nx-high-level-box.json`](../../../examples/nx-high-level-box.json).

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

## Failure semantics and fallback

- Validation failures occur before upload.  Unsupported intent falls through
  to the verified low-level snippets.
- `NewDisplay` invalidates marks from the previously displayed part. Therefore
  the atomic undo boundary starts immediately after the unique run-local part
  is created. A failing NX operation rolls back every model operation after
  that point; the new unsaved container part remains visible for diagnosis.
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
