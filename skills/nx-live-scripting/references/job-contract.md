# Job contract

A job is a Python file in `03_jobs/` with a global `main(job_dir)`. The
dispatcher archives it as `job.py` in a run directory in the VM, verifies its
SHA-256, and calls `main` with that directory as the only argument.

## Hard requirements

1. **`main(job_dir)` is global and takes exactly one argument.** The dispatcher
   calls `Session.Execute(path, "", "main", [runDirectory])`. A `main()` without
   the parameter fails; an `if __name__ == '__main__'` block is never reached.
2. **Write `result.json` into `job_dir`.** It is the only proof the job ran and
   the only channel back to the host. `bridge-execution.json`, written by the
   dispatcher, records identity, source hash and timings — not correctness.
3. **Catch every exception.** An exception escaping into NX opens a modal dialog
   that blocks the message loop, and with it the dispatcher, until a human
   clicks OK in the VM. Catch, record `traceback.format_exc()` in `result.json`,
   return normally.
4. **Unique part names per run.** The NX session outlives one job.
   `Parts.NewDisplay` fails with *"File already exists"* when a part of that name
   is already loaded. Deriving the name from the run directory (`out.name`) is
   the pattern that works.
5. **Do not read configuration from `os.environ`.** NX freezes the environment
   when it starts its embedded interpreter. Everything the job needs comes from
   `job_dir` — write a `parameters.json` beside the job and read it there.

## Conventions that make a run usable

- **One `SetUndoMark` per logical step**, not one per job. With an agent driving
  the construction this is what makes a wrong step recoverable by hand.
  `session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, label)`.
- **Repaint deliberately.** The job runs as one uninterrupted block on the main
  thread, so NX only repaints when told: `view.UpdateDisplay()` after each
  feature. Without it a short job finishes faster than the eye follows.
- **Pace a job meant to be watched** (`time.sleep(1.5)` per step) and remove the
  pauses for unattended runs. `03_jobs/live_demo.py` is the reference.
- **Checkpoint into `result.json` as you go**, not only at the end. If NX blocks
  or the job is interrupted, the last written stage says how far it got.
- **Assert what you produced.** A drafting view that is still out of date exports
  an empty frame with dimension lines and no contour — silently. Assert
  `view.IsOutOfDate is False` and `len(view.AskVisibleObjects()) > 0` before
  exporting; `03_jobs/acceptance.py` shows the full pattern.
- **Prefer few large jobs over many small round trips** for reads. One job that
  returns a rich state snapshot costs one dispatch cycle; N small queries cost N.
- **Split a long construction into several dispatched jobs** when the user should
  inspect NX in between. There is no way to pause or cancel a running job.

## Skeleton

See [../assets/job-template.py](../assets/job-template.py). Its shape:

```python
def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'steps': []}
    try:
        build(out, result)          # all NX work here
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2))
```

`result['ok'] is True` is what the host tools check. Set it only when the job
verified its own output, not merely when no exception occurred.

## Modelling guidance

For anything beyond a demo, prefer **sketch + revolve/extrude** over stacked
primitives. Primitives (`CreateCylinderBuilder`) are parametric features with no
sketch, which is right for a timing demo and wrong for a real part: each step
needs a Boolean, the feature tree becomes unreadable, and the contour is not
cleanly associative — exactly what drawing derivation depends on. A revolved
half profile carries diameters, seats, grooves and chamfers in **one** feature
with every dimension as an expression in one place.

Use expression strings (`builder.Diameter.RightHandSide = '20'`), not floats, so
the parameters stay editable and drive the model afterwards.

Always `Destroy()` a builder — in a `finally`, or the builder leaks and later
calls behave unpredictably.
