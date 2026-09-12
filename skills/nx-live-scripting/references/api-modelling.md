# Layer 4 — model: verified NXOpen calls

**Everything about building geometry is in this file.** For drawings, sheets,
views, dimensions and annotations use [api-drafting.md](api-drafting.md).

**Need working code fast, not the story behind it?** [SNIPPETS-modelling.md](SNIPPETS-modelling.md)
has the same verified calls as plain copy-paste blocks with no rationale/
run-id archaeology. Come back to this file when a snippet fails or you need
the *why* behind a trap.

Every call sequence here was executed against **NX 2506.3001** on this VM.
Where a finding cost more than one attempt, the probe job or run id that
settles it is named, so the claim can be re-checked rather than believed.
Probes are archived under [`03_jobs/probes/`](../../../03_jobs/probes/README.md)
— they are the evidence, not a library.

**Nothing here is recalled. Unlisted paths are unverified, not impossible.**
Before writing a call, confirm the member still exists in your build:
`.venv/bin/python 04_reference/nx_api_lookup.py <term>`.

Status per entry: **verified** (ran, with `result.json`) · **provisional**
(one data point) · **dead end** (see the last section).

---

## Index: what you want → where to look

| I need to… | Entry point | Section |
| --- | --- | --- |
| Anything that commits strangely or will not re-open | Check `builder.Tolerance` for `0.0` → set `0.01` | [§1](#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero) |
| Work on the right part | `session.Parts.Display` / `SetDisplay(part, True, True)` | [§2](#2-getting-onto-the-right-part) |
| A sketch that actually accepts curves | `CreateSketchInPlaceBuilder2` + `PlaneOrFace` (never `PlaneReference`) | [§3](#3-sketches-datums-and-why-loose-curves-are-a-defect) |
| Keep sketches/datums out of the drawing | `MoveDisplayableObjects` to layer 21/61 + `SetState(Hidden)` | [§3](#3-sketches-datums-and-why-loose-curves-are-a-defect) |
| A threaded hole with real standard data | `HolePackageBuilder`, `Type ThreadedHole` | [§4](#4-a-threaded-hole-with-real-standard-data) |
| A keyway / any sketched pocket | Sketched stadium + subtractive `ExtrudeBuilder` | [§5](#5-keyway-form-a-as-a-sketch-defined-extrusion) |
| A primitive block cut (legacy) | `BlockFeatureBuilder`, `Length→X / Width→Y / Height→Z` | [§6](#6-block-primitive-axis-mapping-legacy-path) |
| Measure the solid instead of trusting the picture | `UF.Modeling.AskFaceData`; edge Ø via `GetLength()/π` | [§7](#7-measuring-the-solid-instead-of-trusting-the-picture) |
| Export the solid to STEP AP214 | Standalone `step214ug.exe`, **not** `DexManager` | [§8](#8-step-ap214-export) |
| Know what has been tried and does not work | — | [§9](#9-dead-ends-do-not-re-investigate) |

Job-side rules (result.json, undo marks, asserts, pacing) are **not** here —
they are in [job-contract.md](job-contract.md). Model-vs-primitive strategy
(sketch + revolve over stacked primitives) is in that file's *Modelling
guidance*.

---

## 1. The trap that costs the most time: `Tolerance` defaults to zero

`RevolveBuilder.Tolerance` and `HolePackageBuilder.Tolerance` are **0.0** when
the builder is created with `None`. NX commits the feature without complaint.
The damage appears later:

- **Revolve:** re-opening the feature — a double-click in the part navigator, or
  `CreateRevolveBuilder(feature)` — fails with `Tolerance error`. The NX syslog
  says `+++ Invalid tolerance` from `revolve_builder_definitions.c`. The solid
  is correct, the drawing derives fine; only editing is dead.
- **Hole package:** `CommitFeature()` fails with
  `The Tolerance Specification requires three numbers` — a message that has
  nothing to do with the actual cause.

```python
builder.Tolerance = 0.01          # any sane modelling tolerance
```

`ExtrudeBuilder` has no `Tolerance` property, which is why extrudes never
showed the symptom and made the cause look like it was in the revolve's
profile.

**`RevolveBuilder.Limits` is an `AngularLimits`, with `StartExtend`/`EndExtend`
— not `StartAngle`/`EndAngle`.** Same member names as `ExtrudeBuilder.Limits`
(`GeometricUtilities.Limits`), different type. Confirmed live (probe
`03_jobs/pk6_probe_revolve_limits.py`, run `20260907T220820Z-85e13bc5`):
members `Distance, EndExtend, Null, StartExtend, SymmetricOption, Tag, Validate`.

```python
rev_builder.Limits.StartExtend.SetValue('0')
rev_builder.Limits.EndExtend.SetValue('360')     # full revolve
```

**Correction, 2026-09-08** (run `20260908T210034Z-dde048e7`): the
`Value.RightHandSide` shape also commits cleanly on this build
(`builder.Limits.StartExtend.Value.RightHandSide = '0'`,
`EndExtend… = '360'`, `REVOLVED(2)`, all radii green) — both shapes exist, so
when in doubt sweep Value-first with a `SetValue` except-fallback and record
which one ran.

**When any builder behaves strangely on commit or re-open, check whether it has
a `Tolerance` and whether it is 0.** `03_jobs/feature_reedit_probe.py` catches
this across a whole part before it is handed on ([operations.md](operations.md),
*Diagnosing a part*).

Ruled out by experiment before the cause was found — do not re-investigate:
open vs. closed profile, profile touching the revolve axis, and four axis
constructions. All fail identically with tolerance 0, all work with tolerance
set. Probes: `revolve_variants_probe.py`, `revolve_axis_probe.py`,
`revolve_tolerance_probe.py`.

**Provisional, 2026-09-07** (one data point, narrows the "all four axis
constructions work" line above): with tolerance set, a **non-associative** axis
(`Axes.CreateAxis(Point3d, Vector3d, …)`) still SIGSEGV'd at commit on every
variant (runs `…4877773b` … `…98f585ef`), while an **associative smart axis**
(`Points.CreatePoint` + `Directions.CreateDirection` +
`Axes.CreateAxis(point, direction, …)`, tolerance set) committed first try
(run `…ba34dbe5`, `REVOLVED(2)`). Prefer the smart axis; do not assume the
`Point3d` overload is equivalent.

**Verified, 2026-09-07/08** (run `20260907T221229Z-58765390` onward, `REVOLVED(2)`
committed and re-verified clean on a second part): `DirectionCollection.CreateDirection`
has **no** `(Point, Vector3d, UpdateOption)` overload — passing a smart `Point`
alongside a raw `Vector3d` fails `TypeError: No overload matches these
arguments`. The associative smart-axis direction needs **two** smart `Point`s:

```python
axis_point = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
axis_point2 = part.Points.CreatePoint(NXOpen.Point3d(1.0, 0.0, 0.0))
axis_dir = part.Directions.CreateDirection(axis_point, axis_point2,
                                            NXOpen.SmartObject.UpdateOption.WithinModeling)
axis = part.Axes.CreateAxis(axis_point, axis_dir, NXOpen.SmartObject.UpdateOption.WithinModeling)
```

The `(Point3d, Vector3d, UpdateOption)` overload does exist (raw geometry, used
for the *non-associative* axis above) — the point is that mixing a smart
`Point` with a raw `Vector3d` is not a valid overload at all.

---

## 2. Getting onto the right part

`session.Parts.Display` is the displayed part; `SetDisplay(part, True, True)`
makes one displayed. `DisplayPart` and `SetDisplayPart` do **not** exist
(`AttributeError`), and `SetDisplay` is not callable with one argument
(SyntaxError) nor with a `DisplayPartOption` (it expects a bool). Three
dispatches were burned on this.

Background parts refuse `ModelingViews` (`only be performed on a displayed
part`) and boolean commits on them fail with `not of a valid type for reference
set membership`.

Repeatable pattern: find the part by `FullPath` match, ensure display (set,
then re-read), and **fail loudly on mismatch before any commit**.
Runs `20260906T152832Z-986a935f` (probe), `20260906T191220Z-e0a77a70` (member
dump: `Display`, `SetDisplay`, `GetDisplayedParts` exist),
`…cfa2ce58` … `…bf811165` (the three burned dispatches).

---

## 3. Sketches, datums, and why loose curves are a defect

Curves created with `part.Curves.CreateLine` stay in the part and are **drawn
into every drafting view**. A profile left behind after a revolve appears as a
stray line across the finished drawing.

```python
# Datum plane: fixed ZX, or a point-and-direction plane for an offset.
builder = part.Features.CreateDatumPlaneBuilder(None)
builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
feature = builder.CommitFeature(); builder.Destroy()
datum_plane = [e for e in feature.GetEntities()
               if isinstance(e, NXOpen.DatumPlane)][0]

# Sketch on it. PlaneReference is silently ignored — the sketch stays on the
# default plane and then rejects every curve with
# "Object not in the plane of the sketch". Only PlaneOrFace sets the plane.
builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
builder.PlaneOrFace.Value = datum_plane
sketch = builder.Commit(); builder.Destroy()

sketch.SetName('SKIZZE_DREHKONTUR')
sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)   # not `.False` — reserved word
for curve in curves:                                     # curves already created in place
    sketch.AddGeometry(curve,
                       NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
sketch.Update()
sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue,
                  NXOpen.Sketch.UpdateLevel.Model)
```

Probe: `sketch_plane_probe.py` — four recipes, only this one accepts geometry.

`AddGeometry` keeps the objects, so the same curve list still works as the
section of the feature (`ScRuleFactory.CreateRuleCurveDumb(curves)`).

Afterwards, put sketches and datums where they cannot reach a drawing:

```python
part.Layers.MoveDisplayableObjects(21, sketches + loose_curves)   # NX convention
part.Layers.MoveDisplayableObjects(61, datum_objects)
part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
part.Layers.WorkLayer = 1
```

**`datum_objects` must be the actual `DatumPlane`/`Sketch` entities, not the
owning `Feature`, and never an `Axis`.** Passing the `DatumPlaneFeature` itself
(rather than the `NXOpen.DatumPlane` pulled from `feature.GetEntities()`, per
the pattern above) fails `TypeError: ... found NXOpen.Features.DatumPlaneFeature`.
An `Axis` object (from `Axes.CreateAxis`) is not a `DisplayableObject` at all —
including it in the list fails `NXException: Cannot move a non-displayable
entity to a layer`; just leave axes off any `MoveDisplayableObjects` call, they
need no hiding. Runs `20260907T221229Z-58765390` (feature vs. entity),
`20260907T221301Z-f8c1feb1` (axis).

**Scope that sweep.** Template instantiation spawns `SKETCH_<Blatt>_000`; if the
layer-21 sweep catches it, the drawing frame vanishes (observed, then scoped to
`SKIZZE_*` + datums only). See [api-drafting.md §1](api-drafting.md#1-sheet-from-the-company-template).

**Deleting a `SketchFeature` via `AddToDeleteList` DOES cascade to the curves
that were `AddGeometry`'d into it — narrower than it first looks.** A failed
job that had committed a keyway sketch (4 curves added successfully) plus a
second sketch attempt that crashed on `sketch.SetName` *before* its own
`AddGeometry` loop ran left two different kinds of leftover: deleting the
first sketch feature's datum-plane+sketch pair also removed its 4 curves
(count dropped 21→17 for a 2-feature delete); the second attempt's 4 curves,
never added to any sketch, survived the same delete pass as ordinary loose
curves (17, not 13) and needed a separate identification-and-delete step.
**A curve genuinely owned by a kept feature and one merely left over from an
aborted attempt are not distinguishable by geometry alone when both are
plausible** (e.g. two candidate lines of the same length) — `curve.GetLength()`
plus `int(curve.Tag)` (creation-order-adjacent tags cluster by dispatch) is
enough to tell them apart with certainty; a live loose-curve `GetBoundingBox()`
call was not attempted (not established as existing on `Curve` in this
binding) and would in any case risk deleting a curve the kept revolve profile
still needs if the identification were wrong — prefer the exact `Tag` match
once curves are enumerated, never a heuristic delete. `body.GetEdges()` and
`part.Curves` both give `edge.GetVertices()` (a `Point3d` list; NX2506
apparently returns two identical vertices at the seam for a full circle,
narrower than the earlier "no vertices at all" finding two paragraphs up —
that finding was about **solid body** edges from `body.GetEdges()`; loose
sketch/profile `Curve` objects from `part.Curves` behaved differently in this
case) and `.GetLength()` for exactly this kind of identification. Runs
`20260908T070418Z-bf8d866a` (probe: type+length+tag dump, 13 known-good vs.
4 stray by signature), `20260908T070456Z-4bb4e936` (delete by exact `Tag`,
verified clean: `curve_count == 13`, shaft geometry unchanged).

---

## 4. A threaded hole with real standard data

Do **not** cut the bore and then add a thread — see [§9](#9-dead-ends-do-not-re-investigate).
Let NX drill instead:

```python
builder = part.Features.CreateHolePackageBuilder(None)
builder.Type = NXOpen.Features.HolePackageBuilderTypes.ThreadedHole
builder.ThreadStandard = 'Metric Coarse'
builder.ThreadSize = 'M6 x 1.0'          # not 'M6 x 1' — see below
builder.RadialEngageOption = '0.75'
builder.HolePosition.AddSmartPoint(                       # HolePosition is a Section
    part.Points.CreatePoint(NXOpen.Point3d(70.0, 0.0, 0.0)), 0.01)
builder.ThreadLengthOption = \
    NXOpen.Features.HolePackageBuilderThreadLengthOptions.Custom
builder.ThreadDepth.RightHandSide = '12'
builder.HoleDepthLimitOption = \
    NXOpen.Features.HolePackageBuilderHoleDepthLimitOptions.Value
builder.ThreadedHoleDepth.RightHandSide = '14'
builder.ThreadedTipAngle.RightHandSide = '118'
builder.ThreadedStartChamferEnabled = True
builder.ThreadedStartChamferDiameter.RightHandSide = '6.4'
builder.ThreadedStartChamferAngle.RightHandSide = '30'    # half angle from the face
builder.BooleanOperation.Type = \
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
builder.BooleanOperation.SetTargetBodies([body])
builder.Tolerance = 0.01                                  # §1
feature = builder.CommitFeature(); builder.Destroy()
```

Probe: `hole_probe.py`.

**Thread standard data is installed; the key is strict.**
`%UGII_BASE_DIR%\UGII\modeling_standards\NX_Thread_Standard.xml` lists
`Standard="Metric Coarse"` with `Size="M6 x 1.0"`. `'M6 x 1'` produces
`Standard data not found. Specify different standard or edit standards data.` —
a message that reads like a missing installation and is not one. Grep the file
for the exact `Size=` string before writing it.

**Chamfer angles are measured from the face, not the axis.** A 120° included
countersink is `90 − 120/2 = 30`. `Start chamfer angle must be greater than
zero and less than 90 degrees` is the symptom of getting this wrong. Verify by
measuring the resulting cone ([§7](#7-measuring-the-solid-instead-of-trusting-the-picture)):
its half angle from the axis should be 60°.

**Projection.** The default (`FaceNormal`) suffices when the smart point lies
**on** the surface; a point 1 mm above fails with `No closest face found within
tolerance for Normal to Face` (the hint in that message is correct).
`ProjectionOptions.DirectionType` is **read-only** — delete the assignment
instead of working around it. Runs `20260906T152954Z-804f4371`,
`20260906T153434Z-75e55daa`.

For the norm side of threads and centre holes see
[norm-knowledge.md](norm-knowledge.md).

---

## 5. Keyway Form A as a sketch-defined extrusion

One sketched stadium + one subtractive extrude. This is the **only** first
source for slots; the former Block + 2 holes route was struck (it ran, but
against first principles — primitives instead of a sketch). Verified on scratch
(run `…2c6a4f3f`: `EXTRUDE(3)`, floor measured) and live on the specimen
(run `…97f0bb7f`: `EXTRUDE(6)`, old features deleted, floor Y6.5 measured,
1 body kept).

```python
# Stadium in a ZX datum sketch (Y=0 plane), e.g. straight X49..61, R3 ends:
l1 = part.Curves.CreateLine(Point3d(49,0,-3), Point3d(61,0,-3))
l2 = part.Curves.CreateLine(Point3d(49,0,+3), Point3d(61,0,+3))
# 3-point CreateArc does NOT exist in Python (ref-bool overload unmappable) —
# use center/frame/radius/angles in RADIANS: left end pi/2..3pi/2, right mirrored
aL = part.Curves.CreateArc(Point3d(49,0,0), Vector3d(1,0,0), Vector3d(0,0,1),
                           3.0, 1.5708, 4.7124)   # len pi*3: assert!
aR = part.Curves.CreateArc(Point3d(61,0,0), Vector3d(1,0,0), Vector3d(0,0,1),
                           3.0, 4.7124, 7.8539)
# sketch.AddGeometry each + Update + Deactivate (§3), then:
sec = part.Sections.CreateSection(0.01, 0.01, 0.01)
sec.AddToSection([part.ScRuleFactory.CreateRuleCurveDumb([l1,l2,aL,aR])],
                 l1, None, None, Point3d(0,0,0), NXOpen.Section.Mode.Create)
eb = part.Features.CreateExtrudeBuilder(None)
eb.Section = sec
eb.Direction = part.Directions.CreateDirection(   # NOT a Vector3d (TypeError)
    Point3d(0,0,0), Vector3d(0,1,0), NXOpen.SmartObject.UpdateOption.WithinModeling)
eb.Limits.StartExtend.SetValue('6.5')             # blind limits as strings
eb.Limits.EndExtend.SetValue('11')
eb.BooleanOperation.SetBooleanOperationAndBody(    # NOT SetBooleanOperationAndTarget (Block's)
    NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, body)
feat = eb.CommitFeature(); eb.Destroy()
```

Two traps that cost a probe each: `Direction` wants a `Direction` object, not a
`Vector3d`; the boolean setter is named differently than `Block`'s.

**Provisional, 2026-09-08** (run `20260908T210158Z-4519bbca`, asserted
`20260908T210225Z-85a98bd5`): with `Direction (0, −1, 0)`, `StartExtend '6.5'`
puts the pocket floor at *y = −6.5* — the sign follows the cut direction, so
assert the floor with `abs()`, never a signed value.

**Edge-type lesson:** an extruded floor boundary may report a non-`Linear` edge
type — match floor edges by vertices (both Y≈floor, mid-Z≈±half-width, length),
never by `SolidEdgeType`.

**Replacing live features:** skip journal identifiers containing `:` — internal
children die with their parent, and matching them breaks the delete-count
assert ([operations.md](operations.md), *Diagnosing a part*).

---

## 6. Block primitive axis mapping (legacy path)

Kept because existing parts carry these features, not as a recommended route
for new slots — use [§5](#5-keyway-form-a-as-a-sketch-defined-extrusion).

`BlockFeatureBuilder` maps `Length→X`, `Width→Y`, `Height→Z` — **measured, not
documented.** For a keyway on +Z: `Length 14` (x 50..64), `Width 4.5`
(y 6.5..11), `Height 6` (z −3..+3), corner `(50, 6.5, −3)`, subtract via
`Feature.BooleanType`. Swapping Width/Height cuts z −3..+1.5 instead of ±3 —
found via face extents, not by trust.
Runs `20260906T152954Z-804f4371` (scratch trial),
`20260906T153137Z-8c04fc81` (extents proof), `20260906T153508Z-a28c46ac`
(8/8 green).

---

## 7. Measuring the solid instead of trusting the picture

`Face.GetDiameter` does not exist in NX 2506. Face data comes from the UF layer
and answers type, axis, radius and cone angle in one call:

```python
uf = NXOpen.UF.UFSession.GetUFSession()
kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
# kind: 16 cylinder, 17 cone, 18 sphere, 19 torus, 22 plane
# rad_data on a cone: half angle from the axis, in radians
```

`rad_data` is a float, not a sequence. Circular **edges** give their diameter
through their own circumference (`edge.GetLength() / math.pi`), which needs no
UF call at all and is the cheapest way to find a specific edge for a dimension.

`UF.Modeling.AskEdgeData` does **not** exist (`AttributeError`) — check the name
before concluding edge positions are unreadable. Edge stations come from
`edge.GetVertices()[0].X`: full circles are stored as semicircle pairs with
vertices (the `acceptance.py` pattern).

**Truly closed rim edges have no vertices at all.** A keyway length check built
on rim vertices measured the block pocket instead (52/64, not 49/67); the Ø6
wall faces with axis ±Z at the end centres were the working reference.

**End-face rims are smaller than nominal.** 1×45 chamfers move the end rims to
Ø23/Ø18, so a diameter search by station fails. Take lengths from
station-known rim arcs (`arcs_at`: all vertices share one X) and diameters
station-free — any true circle of that Ø measures right, and an end-on view
asserts orientation at once. Run `20260906T192021Z-dd5937e4` and the drawing
runs `20260906T191626Z-84a85e84` … `20260906T193646Z-070e502a`.

**NX is Z-up.** `Top` looks along −Z, so X-parallel floor edges overlap and a
vertical dimension across them correctly reports 0.0 — rejected by the assert,
not a failure of the API.

A verification job that reports faces, edges and feature parameters and lets the
host compare against nominal values keeps the tolerances in one place; see
`specimen_verify.py` in the consuming project.

---

## 8. STEP AP214 export

Working path, no NX session needed — the standalone translator:

```cmd
STEP214UG\step214ug.exe <in.prt> o=<out.stp> d=STEP214UG\ugstep214.def l=<out.log>
```

Paths are rooted at the install dir, **not** `NXBIN`: `C:\Program Files\Siemens\NX2506\STEP214UG\step214ug.exe`
and `…\STEP214UG\ugstep214.def` (a `Test-Path` under `NXBIN\STEP214UG` answers
`False`). Verified 2026-09-08: CWD = target dir, exe + absolute `d=` → EXIT 0,
23 KB, `AUTOMOTIVE_DESIGN … 214`, 19 `ADVANCED_FACE`, 1 `CLOSED_SHELL`.

Verified 2026-09-06 on the SPARK2 part: 25 KB, schema
`AUTOMOTIVE_DESIGN {1 0 10303 214…}`, 21 `ADVANCED_FACE`, 1 `CLOSED_SHELL`,
read back by counting. Cosmetic threads are not BREP (`THREAD` count 0) — the
callout lives on the drawing.

**Output path trap.** `o=<abs path>` with forward slashes is **ignored** — the
`.stp` lands in the translator's process CWD under the `o=` basename. Move it
into the run directory, then verify schema (`AUTOMOTIVE_DESIGN … 214`), counts
(`ADVANCED_FACE`, `CLOSED_SHELL`) and `THREAD 0`. Observed 2026-09-06
(SPARK3 STEP: 27 658 B, 21/1/0).

`UF_PART_export` (`uf.Part.Export`) exists but takes `(str, int, …)`: the first
parameter is a string, the second an int type code — the codes were not swept
once the CLI above worked.

---

## 9. Dead ends: do not re-investigate

Recorded so the next agent does not spend the same hours. **An attempt outcome
is not an impossibility** — where the mechanism is unknown, that is said.

- **Thread on an already-turned cylinder.** `ThreadBuilder` refuses a symbolic
  thread with major/minor diameter, pitch, length and a start face all set,
  answering `Thread depth must be greater than zero` in **all 24** combinations
  of call order, start object (planar end face, countersink cone, circular edge,
  none) and limit option. Probe: `thread_probe.py`. Use `HolePackageBuilder`
  ([§4](#4-a-threaded-hole-with-real-standard-data)).
- **`DexManager.CreateStepCreator` writes no file.** `Validate()` returns True
  and the commit is silent, with `ExportAs = Ap214`,
  `ExportFrom = ExistingPart`/`DisplayPart`,
  `ExportDestination = NativeFileSystem`, the body in
  `ExportSelectionBlock.SelectionComp` (via `Add(body)`),
  `ObjectTypes.Solids/Surfaces = True`, `FileSaveFlag = True`, and a
  `SettingsFile` from `STEP214UG`. `GetCommittedObjects()` returns `[]`.
  Five combinations, no output (runs `20260906T105844Z-a7c94fe9` …
  `20260906T110709Z-37056c1d`). Recorded as tried, not as impossible — use the
  CLI in [§8](#8-step-ap214-export).
- **`Sketch.PlaneReference`** is silently ignored; only `PlaneOrFace` sets the
  plane ([§3](#3-sketches-datums-and-why-loose-curves-are-a-defect)).
- **3-point `CreateArc`** does not exist in Python — the ref-bool overload is
  unmappable ([§5](#5-keyway-form-a-as-a-sketch-defined-extrusion)).
- **`Face.GetDiameter`, `UF.Modeling.AskEdgeData`, `DisplayPart`,
  `SetDisplayPart`** — none of these exist. Look up before concluding a
  capability is missing.
- **`ProjectionOptions.DirectionType`** is read-only; assigning it fails
  ([§4](#4-a-threaded-hole-with-real-standard-data)).
- **A non-associative axis (`Axes.CreateAxis(Point3d, Vector3d, …)`)** SIGSEGV'd
  at revolve commit on every variant even with tolerance set — provisional, one
  session ([§1](#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero)).

Drafting dead ends (section views, `t1`, detail views) live in
[api-drafting.md](api-drafting.md#9-dead-ends-do-not-re-investigate).
