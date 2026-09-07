# Job contract

A job is a Python file in `03_jobs/` with a global `main(job_dir)`. The
dispatcher archives it as `job.py` in a run directory in the VM, verifies its
SHA-256, and calls `main` with that directory as the only argument.

## Hard requirements

1. **`main(job_dir)` is global and takes exactly one argument.** The dispatcher
   calls `Session.Execute(path, "", "main", [runDirectory])`. A `main()` without
   the parameter fails; an `if __name__ == '__main__'` block is never reached.
2. **Write `result.json` into `job_dir`, as UTF-8.** It is the only proof the
   job ran and the only channel back to the host. `bridge-execution.json`,
   written by the dispatcher, records identity, source hash and timings — not
   correctness. NX's embedded Python writes text in the Windows ANSI code page
   unless told otherwise, so a job reporting German text produces cp1252 and the
   host's `json.loads` fails on a byte it cannot decode:
   `(out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')`.
   (`nx_remote.py` and `nx_visible.py` try `utf-8-sig` then `cp1252`, so older
   jobs still collect — new jobs write UTF-8 explicitly.)
   **Never put an NXOpen object into it.** Keeping a dimension in the report for
   later cleanup and forgetting to strip it fails the whole job at the last line
   with `Object of type HorizontalDimension is not JSON serializable` — after all
   the work is done and before anything is saved.
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
6. **One result-dict name, checked before dispatch.** `nx_remote.py` compiles
   the job (syntax) but cannot catch a `NameError`: a checkpoint writing
   `result` while the dict is named `r` crashes AFTER all work is done, the
   exception escapes `main`, and NX stalls on a modal dialog until a human
   clicks OK (2026-09-07, two modals, one root cause). Grep before
   `--prepare-only` that the dumped name matches the defined one.

## Conventions that make a run usable

- **One `SetUndoMark` per logical step**, not one per job. With an agent driving
  the construction this is what makes a wrong step recoverable by hand.
  `session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, label)`.
- **Record every mark ID.** `Session.UndoToMark(mark_id, name)` needs the ID
  (no license required) — an unrecorded mark cannot be undone to later:
  `mid = session.SetUndoMark(...); result['marks'][key] = str(mid)`.
  Learned 2026-09-07: drawing iterations without recorded IDs were only
  recoverable by rebuilding, never by selective undo.
- **Repaint deliberately.** The job runs as one uninterrupted block on the main
  thread, so NX only repaints when told: `view.UpdateDisplay()` after each
  feature. Without it a short job finishes faster than the eye follows.
- **Every drawing goes on the company sheet template.** `KUP_Zeichenvorlage.prt`
  (A3, frame + title block) via `SheetOption.UseTemplate` with the full VM path —
  standing rule until said otherwise. A `CustomSize` sheet is a probe or scratch
  only, never a deliverable draft: it carries no frame, no title block and no
  general-tolerance note, so it cannot satisfy layer-3 rule §1. Call shape and
  the two instantiation traps:
  [api-drafting.md §1](api-drafting.md#1-sheet-from-the-company-template).
- **`Regenerate()` before export and save, in every job that touches
  annotations.** `UpdateViews(All)` refreshes geometry only; the interactive
  session keeps showing stale annotation layout and missing tolerances while the
  PDF already renders correctly. `part.Views.UpdateDisplay()` alone heals
  nothing — `part.Views.Regenerate()` is the load-bearing call (it is the
  gallery action *View → Layout → Regenerate All Views*). Learned 2026-09-07
  from the user's hand journal; call shape in
  [api-drafting.md §8](api-drafting.md#8-regenerate-the-call-that-refreshes-annotations).
- **`Fit()` the final sheet so the watcher sees it whole.** After the last
  `sheet.Open()`, `part.Views.WorkView.Fit()` + `UpdateDisplay()`. Without it the
  drafting window shows a zoomed section and the user cannot judge the drawing
  (user screenshot 2026-09-07). Also open the sheet before `part.Save()` — it
  avoids the `Save CGM` dialog ([operations.md](operations.md), triage table).
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
- **Check annotation CONTENT against the norm checklist, not just its
  mechanics.** A sweep that optimizes associativity/placement silently drops
  content details (remain markings, short-form wordings, limit deviations).
  Every annotation needs its rulebook line verified, not just its
  `ComputedSize`. Learned 2026-09-07 (F-5 remain marking, limit deviations).
- **Check PLACEMENT against the rule, not just the number.** A verified
  `ComputedSize` says nothing about the view: record `view` + `rule` per
  dimension (e.g. width → end view per F-2) and let overall `ok` require
  the rule fields. Learned 2026-09-07/08: keyway width verified 6.0 in
  Front was expedience (first green number won; end view never even
  tried — no trial entries exist), length skipped for lack of value
  instead of flagged open.
- **Validate across features, not just within.** Per-feature asserts
  (floor/flanks/radii green) miss collision layouts (groove crossing the
  keyway span) and missing locators. Assert stations/spans between features
  wherever the rulebook fixes them. Learned 2026-09-07.
- **Abstract silence is not freedom.** Undimensioned stations/sizes the
  abstract leaves open are unvalidated choices — flag them as assumptions
  for decision instead of inventing quietly. Learned 2026-09-07.
- **Read rules before API.** Normative sections (rules, checklists, figures)
  first, recipes/mapping second — API-first reading optimizes mechanism
  over conformity. The pre-flight rule list (§template) plus the feature
  index (mapping) make this the cheap path. Learned 2026-09-08.

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
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
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
calls behave unpredictably. And check whether the builder has a `Tolerance`: a
default `0.0` commits happily and breaks later
([api-modelling.md §1](api-modelling.md#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero)).

The verified call sequences themselves are layer 4:
[api-modelling.md](api-modelling.md) for geometry,
[api-drafting.md](api-drafting.md) for sheets, views, dimensions and
annotations.
