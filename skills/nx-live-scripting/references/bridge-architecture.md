# Why the bridge looks like this

Verified against the toolkit source and a working NX 2506 installation on an
ARM64 Parallels VM. Read this before proposing a different transport: the
obvious alternatives were tried, and each failed for a specific reason.

## The one constraint everything follows from

NXOpen is not thread-safe. Every call must happen on the thread NX started it
on. A socket server, a background worker, or an RPC dispatcher on a thread pool
does not satisfy that on its own — it only moves the marshalling problem.

The dispatcher solves it by not having a thread of its own: it polls a file
queue on a `System.Windows.Forms.Timer`, which ticks on NX's message loop. A
WinForms timer inside NX's Qt loop was doubted and turned out to tick reliably.

## How NX loads the dispatcher

NX loads managed assemblies from the `startup` folder of a directory listed in
the file named by `UGII_CUSTOM_DIRECTORY_FILE`, and calls the entry point
`ufsta`.

- **`ufsta` must return `int` or `string`.** A `void` one is refused with
  *"Found method, but return type is not an integer or string"*, followed by
  *"Cannot find method ufsta in image"* in the NX syslog.
- The launcher passes the project directory explicitly through an environment
  variable. Relying on `MyDocuments` is wrong when NX starts from a scheduled
  task.

## Rejected paths, with the reason

| Path | Why not |
| --- | --- |
| `USER_STARTUP` | Loads a **native** DLL and resolves `ufsta` as an exported C symbol. A .NET assembly fails with *"Library is missing required entry point"*. Would need the NX Open C++ component (`UGOPEN`, not installed) plus a C++ compiler. |
| `ugraf.exe -nx <journal>` | NX starts and ignores the file. The GUI has no journal option; `run_journal.exe -help` lists them all. |
| `run_journal.exe` | Own headless kernel. Works, but is unwatchable — it is the batch fallback, not the live path. |
| NX Open "external" `.exe` | Own headless kernel. Does **not** attach to the running GUI. |
| `JournalManager.PlayDotNetJournal` | Takes only C#/VB **source**, compiles against .NET 8 while the dispatcher runs on .NET Framework (*"Resolve failed: System.Runtime, Version=8.0.0.0"*), and **reports success even when the journal throws**. |
| Compiled job assembly by reflection | Forces every job to be C#, and `Assembly.LoadFrom` silently returns the first job loaded in the session because all jobs share one assembly identity. |
| NX Remoting (.NET Remoting) | Real and documented, but: the server half must still be registered from inside NX (so the startup path is needed anyway), it dispatches on thread-pool threads so the main-thread problem returns, an NX Open Author license is cited as a prerequisite, .NET Remoting is deprecated and absent from .NET 5+, and it needs an extra Windows proxy to reach from the Mac. Decisive argument: it is an **object proxy** — every property access is a wire call, so a run over 500 features is 500+ round trips, while shipping a script moves arbitrary computation in one. |
| `#nx: threaded` journal directive | Keeps a listener alive; does not make NXOpen thread-safe. The marshalling work remains. Weakest-sourced item in the research — reproduce it yourself before relying on it. |

Two independent public NX MCP projects build the same architecture and both stop
at the interactive mode, not at the protocol. This dispatcher is past that point.

## The one real gap

Polling cannot deliver **event push** — NX telling the agent by itself that the
user changed something. If an agent must react to GUI actions, that is the only
place where Remoting or another callback path is actually needed. Nothing else
in the alternatives table buys anything back.

## Why C# dispatcher, Python jobs

Only the dispatcher must be a managed assembly, because NX's start-up hook loads
libraries and there is no equivalent hook for a Python script. It is ~200 lines
that rarely change and is compiled once.

Jobs are Python, executed with
`Session.Execute(path, "", "main", new object[] { runDirectory })`, which runs a
global function in NX's own embedded interpreter and propagates exceptions
correctly.

The run directory arrives as an **argument**, never through the environment: NX
freezes `os.environ` when it starts the interpreter, so a variable set by the
dispatcher never reaches the script.

## Safety properties already in the design

Keep these when extending it:

- SHA-256 verification of the job source against the request;
- path confinement — only a `job.py` inside the project directory runs;
- atomic renames `.ready` → `.running` → `.done`/`.failed`, never auto-retried;
- requests queued before the session started are quarantined as `.stale`;
- abort when `SessionId == 0` (no visible desktop session);
- pause while `JournalManager.IsJournalRunning`;
- main-thread identity re-checked on every tick;
- no additional listening port — transport is the existing SSH/SCP connection.

## Runtime and platform notes

NX 2506 ships both loaders: `NXBIN\managed` (.NET Framework) and
`NXBIN\managed_core` (.NET 8). It tries Core first and falls back to Framework,
which the syslog states literally. The dispatcher is built with the Framework
`csc.exe` and loaded through the Framework path. Leave it there until NX is
upgraded or the dispatcher is touched anyway; a rebuild against
`managed_core\NXOpen.dll` on `net8.0-windows` needs a .NET 8 **SDK** and a
`.csproj` with `UseWindowsForms` (the timer). The failure would be loud, not
silent: no `bridge-loaded.log`, no `bridge-status.json`, and `status` fails at
once.

On an ARM64 host the x64 .NET runtime lives in `C:\Program Files\dotnet\x64`,
which the NX loader does not search — the launcher sets `DOTNET_ROOT` to it.
`winget install` there fetches the **arm64** build by default; force the
architecture and check where it landed.

## Measured cost

An SSH round trip to the VM is ~0.3 s, ~0.5 s with PowerShell — the VM and the
host are the same machine. A full job (upload → execute → collect) takes ~7 s,
of which ~4 s is poll granularity (1 s dispatcher timer plus the host wait loop)
and ~3 s is six to eight individual SSH calls. The **number** of round trips is
the cost, not the latency of one. Optimising further buys little against model
thinking time; bundle reads into one job instead.
