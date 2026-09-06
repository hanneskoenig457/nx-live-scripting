# Recipes that have actually run

Every call sequence here was executed against **NX 2506.3001** on this VM. Where
a finding cost more than one attempt, the probe job that settles it is named, so
the claim can be re-checked rather than believed. Source of all of it: the
`10_Online_Machining` specimen (`cad/README.md` there).

Use this file the way you would use a colleague's notebook: copy the shape, then
verify with `nx_api_lookup.py` that the members still exist in your NX build.

Every probe named below is archived under
[`03_jobs/probes/`](../../../03_jobs/probes/README.md) — they are the evidence,
not a library. The two diagnostics meant for reuse sit one level up:
`feature_reedit_probe.py` and `part_open_probe.py`.

---

## 0. The trap that costs the most time: builders whose tolerance defaults to zero

`RevolveBuilder.Tolerance` and `HolePackageBuilder.Tolerance` are **0.0** when the
builder is created with `None`. NX commits the feature without complaint. The
damage appears later:

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

`ExtrudeBuilder` has no `Tolerance` property, which is why extrudes never showed
the symptom and made the cause look like it was in the revolve's profile.

Ruled out by experiment before the cause was found — do not re-investigate:
open vs. closed profile, profile touching the revolve axis, and four axis
constructions (smart axis, the `Point3d`/`Vector3d` overload, datum axis by
point-and-direction, datum axis XC). All fail identically with tolerance 0, all
work with tolerance set. Probes: `revolve_variants_probe.py`,
`revolve_axis_probe.py`, `revolve_tolerance_probe.py`.

**When any builder behaves strangely on commit or re-open, check whether it has a
`Tolerance` and whether it is 0.**

---

## 1. Reading NX's own error text

NXOpen exceptions are short. The syslog carries the real message.

```python
import os
from pathlib import Path

temp = Path(os.environ.get('TEMP', r'C:\Windows\Temp'))
newest = sorted(temp.glob('*.syslog'), key=lambda p: p.stat().st_mtime)[-1]
tail = newest.read_text(encoding='utf-8', errors='replace').splitlines()[-60:]
```

That is how `Tolerance error` was traced to `+++ Invalid tolerance`. Put it in
the failure path of a probe job, not in production jobs.

---

## 2. Sketches, datums, and why loose curves are a defect

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

---

## 3. A threaded hole with real standard data

Do **not** cut the bore and then add a thread. `ThreadBuilder` refuses a
symbolic thread on an already-turned cylinder: with major/minor diameter, pitch,
length and a start face all set, it still answers `Thread depth must be greater
than zero`, in all 24 combinations of call order, start object (planar end face,
countersink cone, circular edge, none) and limit option. Probe:
`thread_probe.py`.

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
builder.Tolerance = 0.01                                  # section 0
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
countersink is `90 − 120/2 = 30`. `Start chamfer angle must be greater than zero
and less than 90 degrees` is the symptom of getting this wrong. Verify by
measuring the resulting cone (section 4): its half angle from the axis should be
60°.

---

## 4. Measuring the solid instead of trusting the picture

`Face.GetDiameter` does not exist in NX 2506. Face data comes from the UF layer
and answers type, axis, radius and cone angle in one call:

```python
uf = NXOpen.UF.UFSession.GetUFSession()
kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
# kind: 16 cylinder, 17 cone, 18 sphere, 19 torus, 22 plane
# rad_data on a cone: half angle from the axis, in radians
```

`rad_data` is a float, not a sequence. Circular **edges** give their diameter
through their own circumference (`edge.GetLength() / math.pi`), which needs no UF
call at all and is the cheapest way to find a specific edge for a dimension.

A verification job that reports faces, edges and feature parameters and lets the
host compare against nominal values keeps the tolerances in one place; see
`specimen_verify.py` in the consuming project.

---

## 5. Drawings

### 5.1 Sheet from a company template, without administrator rights

The documented route is to copy the template into
`C:\Program Files\Siemens\NX...\UGII\templates`. That needs elevation. A full
path works just as well:

```python
builder = part.DrawingSheets.DrawingSheetBuilder(None)
builder.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
builder.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
builder.MetricSheetTemplateLocation = r'C:\...\KUP_Zeichenvorlage.prt'
sheet = builder.Commit(); builder.Destroy()
sheet.Open()

# Without this the part stays half-instantiated. A part saved in that state
# later refuses to open with "Corrupt data found when loading an OM file".
part.Drafting.SetTemplateInstantiationIsComplete(True)

# Frame and title block arrive on layer 256 in state "visible only" (2).
# Set it visible or both are missing from the PDF.
part.Layers.SetState(256, NXOpen.Layer.State.Visible)
```

Probe: `template_probe.py` inspects a template part before use — sheets, sizes,
tables, title blocks, and the attribute titles its cells read.

The sheet name and scale come from the template, not from the builder. Change
them afterwards:

```python
sheet.SetParameters(height, length, numerator, denominator, units, projection_angle)
```

**Title block cells are filled from part attributes**, set before or after the
sheet exists:

```python
part.SetUserAttribute('Bezeichnung/Titel', -1, 'Prüfkörper', NXOpen.Update.Option.Now)
part.SetTimeUserAttribute('Datum', -1, '06-Sep-2026 00:00:00', NXOpen.Update.Option.Now)
```

A time attribute wants `DD-Mon-YYYY hh:mm:ss`; ISO-8601 is refused with
`The date value is invalid.` Cells NX fills itself — scale, mass — are **not** in
`DraftingManager.TitleBlocks.CreateEditTitleBlockBuilder(blocks).Cells` and
cannot be set from the API. If the template's scale cell is fixed at 1:1, the
drawing has to be 1:1, or the title block lies.

### 5.2 View placement

`sheet.SheetDraftingViews.CreateBaseView(model_view, Point3d(x, y, 0), scale, False)`
puts the **model origin** at `(x, y)`, not the part's centre. At 2:1 a 70 mm
part therefore occupies `x … x + 140`. Getting this backwards puts detail-view
boundaries and section lines on the wrong feature.

`view.Origin` is read-only and returns model-space, not sheet coordinates;
`view.SetOrigin(...)` answers `View may not be scaled nor translated`.
`CalculateMinMaxBox()` also returns model space. Place views through the builder
(`ViewPlacement.Placement.SetValue(None, None, Point3d)`) and get it right the
first time.

### 5.3 Dimensions

The general shape, used for every dimension type:

```python
data = part.Annotations.NewDimensionData()
for index, (obj, view, option) in enumerate(objects, 1):
    assoc = part.Annotations.NewAssociativity()
    assoc.FirstObject, assoc.ObjectView, assoc.PointOption = obj, view, option
    data.SetAssociativity(index, [assoc])
dim = part.Dimensions.CreateHorizontalDimension(data, NXOpen.Point3d(x, y, 0.0))
dim.IsOriginCentered = True          # text centred on the dimension line
```

- **`IsOriginCentered` overrides the placement point.** Right for lengths, wrong
  for a diameter in a longitudinal view, where centred means "inside the part".
- **Diameters on a longitudinal view need the cylindrical *face*, twice**, with
  `AssociativityPointOption.OnCurve`. With the circular edges,
  `CreateCylindricalDimension` measures the axial distance between them and
  reports a plausible wrong number (29 instead of 25).
- **ISO fits instead of typed deviations:**

```python
dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
dim.LimitFitDeviation = 'h'          # 'P' for an internal feature
dim.LimitFitGrade = 6
```

- **Trial dimensions are real objects.** Searching for the right associativity
  leaves them on the sheet. Remove each rejected one:

```python
mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Probemaß')
session.UpdateManager.AddToDeleteList([dim])
session.UpdateManager.DoUpdate(mark)
```

- **Assert every dimension.** `dim.ComputedSize` against the nominal value turns
  a wrong association into a failed run instead of a wrong drawing.

### 5.4 Surface finish, notes, leaders

```python
builder = part.Annotations.DraftingSurfaceFinishSymbols \
    .CreateDraftingSurfaceFinishBuilder(None)
# `FinishType` is read-only; the setter is `Finish`. Only the *Modifier*
# variants carry the extension line that the value sits on — without it NX draws
# the tick and silently drops the roughness value, in every spelling.
builder.Finish = NXOpen.Annotations.DraftingSurfaceFinishBuilderFinishType \
    .ModifierMaterialRemovalRequired
builder.SingleRoughnessValue = True
builder.A1 = 'Ra 0,8'
```

A leader onto a real object survives model changes; a leader onto a free point
does not:

```python
data = part.Annotations.CreateLeaderData()
data.Arrowhead = NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
data.StubSide = NXOpen.Annotations.LeaderSide.Inferred
data.Leader.SetValue(edge, view, NXOpen.Point3d(0.0, 0.0, 0.0))
builder.Leader.Leaders.Append(data)
```

The same `Leader` block works on `CreateDraftingNoteBuilder`.

### 5.5 What did not work from the API

Recorded so the next agent does not spend the same hours:

- **`SectionViewBuilder` cuts along the shaft, not across it.** Parent view,
  `SectionViewType = SimpleStepped`, a `Cut` segment point at the wanted station,
  additional `Arrow` points above and below it, and a horizontal placement
  request all produce the same longitudinal cut. `ViewPlacementBuilder.Method` is
  read-only, so the placement direction cannot be forced either.
- **No associative dimension to a cylinder's crest.** All five point options on a
  circular edge (`Tangent`, `OnCurve`, `Control`, `Defining`, `Anchor`), in an
  end view and in a section, and with vertical, perpendicular and parallel
  dimension types, return axis-related distances (3.0 / 6.5 / 9.54 / 10.0 / 20.0)
  — never surface-to-feature. A keyway depth `t1` therefore cannot be dimensioned
  this way; state it as a note, or find a different reference geometry.
- **`DetailViewBuilder.Scale` and `LabelOnParent` are read-only accessors**;
  write through `Scale.Numerator`/`Scale.Denominator` and the flattened enum
  `DetailViewBuilderLabelOnParentType`. Boundary points must be `NXOpen.Point`
  objects, not `Point3d`.

---

## 6. Diagnosing a part that will not open

`OpenDisplay` returns `None` for the part instead of raising. The load status
carries the reason:

```python
opened = session.Parts.OpenDisplay(path)
part, status = opened[0], opened[1]
for i in range(status.NumberUnloadedParts):
    print(status.GetPartName(i), status.GetStatusDescription(i))
# -> "Corrupt data found when loading an OM file"
```

`03_jobs/part_open_probe.py` does exactly this. A part corrupted this way is not
repairable from the API — rebuild it, which is the argument for keeping the
model job repeatable in the first place.

`03_jobs/feature_reedit_probe.py` re-opens the builder of every feature in a
part and reports which ones refuse — the API equivalent of double-clicking each
entry in the part navigator, and the fastest way to catch section 0 before a part
is handed on. Two details it had to learn:

- **Map on `FeatureType`, not on the journal identifier.** A hole package names
  its children after itself: `THREADED HOLE(7)` is the package,
  `THREADED HOLE(7:1A)` the drilled hole, `THREADED HOLE(7:1A:1A)` the thread —
  three different feature types under one name.
- **A colon in the journal identifier marks a feature internal to another one.**
  Those are edited through their parent and answer
  *"First parameter is invalid. Expecting … found …"* if asked directly. Skip
  them; a builder that refuses an internal child is not a defect.

Verified against the specimen part on 2026-09-06: twelve features, zero
re-edit failures, sketches reported honestly as unmapped.

---

## 7. Result files and encoding

NX's embedded Python writes text in the Windows ANSI code page unless told
otherwise. A job that reports German text produces cp1252 and the host's
`json.loads` fails on a byte it cannot decode.

```python
(out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
```

`01_host/nx_remote.py` and `nx_visible.py` now try `utf-8-sig` then `cp1252`, so
older jobs still collect. New jobs should write UTF-8 explicitly.

**Never put an NXOpen object into `result.json`.** Keeping a dimension in the
report for later cleanup and forgetting to strip it fails the whole job at the
last line with `Object of type HorizontalDimension is not JSON serializable`,
after all the work is done and before anything is saved.
