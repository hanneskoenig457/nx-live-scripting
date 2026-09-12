# Snippets — modelling (code only)

Copy-paste-ready calls, no rationale/run-id storytelling. Read a section here
first; go to [api-modelling.md](api-modelling.md) (linked per snippet) only
when something fails or you need the *why*. Every block below either ran in
a dispatched job (`ok: true` in its `result.json`) or is copied verbatim from
[api-modelling.md](api-modelling.md)'s own verified sections — none of this
is freshly reasoned from the .NET XML.

`WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling` is assumed defined
above every snippet that uses it.

## Tolerance — set on every NEW RevolveBuilder / HolePackageBuilder

```python
builder.Tolerance = 0.01   # defaults to 0.0 — commits fine, breaks on re-open
```
Full trap: [api-modelling.md §1](api-modelling.md#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero).

## Find-or-open the right part (never blind `OpenDisplay`)

```python
wanted = model_path.replace('\\', '/').lower()
part = None
for candidate in session.Parts:
    if str(candidate.FullPath).replace('\\', '/').lower() == wanted:
        part = candidate
        break
if part is None:
    opened = session.Parts.OpenDisplay(model_path)
    part, status = opened[0], opened[1]
    if part is None:
        raise RuntimeError([status.GetStatusDescription(i)
                             for i in range(status.NumberUnloadedParts)])
session.Parts.SetDisplay(part, True, True)
assert str(session.Parts.Display.FullPath).replace('\\', '/').lower() == wanted
```
`OpenDisplay` on an already-displayed part raises `NXException: File already
exists` — the search loop above is what avoids it. Full context:
[api-modelling.md §2](api-modelling.md#2-getting-onto-the-right-part).

## Close exactly one active part without a dialog

```python
if save:
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
              NXOpen.BasePart.CloseAfterSave.FalseValue)
part.Close(NXOpen.BasePart.CloseWholeTree.TrueValue,
           NXOpen.BasePart.CloseModified.CloseModified,
           None)
```

`CloseModified` permits the modified part to close; it does not itself save.
Call `Save` first only when persistence was requested. Verified on a run-local,
SHA-256-checked copy in visible run `20260912T194302Z-c723423b`: one body was
listed, `save=False` closed the copy, and the following status reported no
active part. Full context: [api-modelling.md §2](api-modelling.md#2-getting-onto-the-right-part).

## Datum plane + real Sketch feature (not loose curves)

```python
def zx_datum_plane(part):
    builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return [e for e in feature.GetEntities() if isinstance(e, NXOpen.DatumPlane)][0]


def make_sketch(part, datum_plane, name, curves):
    builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    try:
        builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        builder.PlaneOrFace.Value = datum_plane   # PlaneReference is silently ignored
        sketch = builder.Commit()
    finally:
        builder.Destroy()
    sketch.SetName(name)
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    for curve in curves:
        sketch.AddGeometry(curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    return sketch
```
`NXOpen.Sketch` is a CLASS, not a namespace — do **not** `import NXOpen.Sketch`
(crashes script load; see nxopen-python-notes.md). Curves are created with
`part.Curves.CreateLine`/`CreateArc` first, in place, then passed to
`make_sketch` — the same curve list still works as the revolve/extrude
section afterward. Full context: [api-modelling.md §3](api-modelling.md#3-sketches-datums-and-why-loose-curves-are-a-defect).

## Revolve from a sketch profile (smart axis, tolerance set)

```python
def smart_x_axis(part):
    origin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN)
    return part.Axes.CreateAxis(origin, direction, WITHIN)   # prefer this smart
    # axis over the raw Point3d/Vector3d CreateAxis overload — that one
    # SIGSEGV'd at commit even with Tolerance set (provisional, one session).


def revolve_profile(part, datum_plane, profile):   # profile: [(x, radius), ...]
    points = [NXOpen.Point3d(x, 0.0, r) for x, r in profile]
    curves = [part.Curves.CreateLine(points[i], points[i + 1])
              for i in range(len(points) - 1)]
    sketch = make_sketch(part, datum_plane, 'SKIZZE_DREHKONTUR', curves)
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        section = part.Sections.CreateSection()
        section.AddToSection(
            [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None, None,
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        builder.Section = section
        builder.Axis = smart_x_axis(part)
        builder.Limits.StartExtend.Value.RightHandSide = '0'
        builder.Limits.EndExtend.Value.RightHandSide = '360'
        builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        builder.Tolerance = 0.01
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    body = list(feature.GetBodies())[0]
    return feature, body, sketch
```
An open profile touching the revolve axis at both ends is fine — NX closes it
implicitly, no explicit axis-line segment needed. Full context:
[api-modelling.md §1](api-modelling.md#1-the-trap-that-costs-the-most-time-tolerance-defaults-to-zero),
[§3](api-modelling.md#3-sketches-datums-and-why-loose-curves-are-a-defect).

## Sketched pocket / keyway (stadium, subtractive extrude)

```python
import math

def keyway_stadium(part, datum_plane, body, x_left_arc, x_right_arc, half_width,
                    floor_r, seat_r, cut_direction=-1.0):
    l1 = part.Curves.CreateLine(NXOpen.Point3d(x_left_arc, 0.0, -half_width),
                                 NXOpen.Point3d(x_right_arc, 0.0, -half_width))
    l2 = part.Curves.CreateLine(NXOpen.Point3d(x_left_arc, 0.0, half_width),
                                 NXOpen.Point3d(x_right_arc, 0.0, half_width))
    half_pi = math.pi / 2.0
    a_left = part.Curves.CreateArc(NXOpen.Point3d(x_left_arc, 0.0, 0.0),
                                    NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
                                    half_width, half_pi, 3.0 * half_pi)
    a_right = part.Curves.CreateArc(NXOpen.Point3d(x_right_arc, 0.0, 0.0),
                                     NXOpen.Vector3d(1.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 0.0, 1.0),
                                     half_width, 3.0 * half_pi, 5.0 * half_pi)
    curves = [l1, l2, a_left, a_right]
    sketch = make_sketch(part, datum_plane, 'SKIZZE_PASSFEDERNUT', curves)

    sec = part.Sections.CreateSection(0.01, 0.01, 0.01)
    sec.AddToSection([part.ScRuleFactory.CreateRuleCurveDumb(curves)], l1, None, None,
                      NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create)

    eb = part.Features.CreateExtrudeBuilder(None)
    try:
        eb.Section = sec
        eb.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, cut_direction, 0.0), WITHIN)
        eb.Limits.StartExtend.SetValue(str(floor_r))
        eb.Limits.EndExtend.SetValue(str(seat_r + 1.0))
        eb.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, body)
        feature = eb.CommitFeature()
    finally:
        eb.Destroy()
    return feature, sketch
```
`ExtrudeBuilder` limits use `.SetValue(str)`, NOT `.Value.RightHandSide` like
Revolve — different builders, different property shapes, verified per-call.
`cut_direction`: **which side the slot opens on is a real modelling choice**,
not cosmetic — it decides which face of the part the feature sits on, and a
cut on the wrong side does not render at all (not even dashed) in whichever
named view looks from the far side. Don't default to +Y without checking
`CANNED_VIEW_TOWARD_VIEWER` for the drawing's intended main view first (a
keyway extruded away from the viewing camera never shows up in that view —
caught 2026-09-07 by rendering with `cut_direction=+1.0` in a `Front` view;
verified fix is picking the view whose toward-viewer row matches the cut
sign, not flipping `cut_direction` blindly, since the sign also has to match
the intended manufacturing/visible face): see
[SNIPPETS-drafting.md "which canned view shows which end"](SNIPPETS-drafting.md#which-canned-view-shows-which-end)
for the verified axis table and the run ids. Full context:
[api-modelling.md §5](api-modelling.md#5-keyway-form-a-as-a-sketch-defined-extrusion).

## Threaded hole with real standard data (+ optional centering chamfer)

```python
def threaded_hole(part, body, position, thread_size='M6 x 1.0',
                   thread_depth='12', hole_depth='14', tip_angle='118',
                   start_chamfer_dia=None, start_chamfer_angle=None):
    builder = part.Features.CreateHolePackageBuilder(None)
    try:
        builder.Type = NXOpen.Features.HolePackageBuilderTypes.ThreadedHole
        builder.ThreadStandard = 'Metric Coarse'
        builder.ThreadSize = thread_size          # exact string from
        # UGII\modeling_standards\NX_Thread_Standard.xml — 'M6 x 1' (no .0)
        # fails with a misleading "Standard data not found".
        builder.RadialEngageOption = '0.75'
        pt = part.Points.CreatePoint(position)
        builder.HolePosition.AddSmartPoint(pt, 0.01)   # point must lie ON the
        # target face — default Projection (FaceNormal) needs that
        builder.ThreadLengthOption = NXOpen.Features.HolePackageBuilderThreadLengthOptions.Custom
        builder.ThreadDepth.RightHandSide = thread_depth
        builder.HoleDepthLimitOption = NXOpen.Features.HolePackageBuilderHoleDepthLimitOptions.Value
        builder.ThreadedHoleDepth.RightHandSide = hole_depth
        builder.ThreadedTipAngle.RightHandSide = tip_angle
        if start_chamfer_dia is not None:
            builder.ThreadedStartChamferEnabled = True
            builder.ThreadedStartChamferDiameter.RightHandSide = start_chamfer_dia
            # Angle is measured FROM THE FACE, not from the axis: for a cone
            # with half-angle A from the axis, pass (90 - A). A 60-deg-included
            # centering lead cone (half-angle 30 from axis) -> pass '60'.
            builder.ThreadedStartChamferAngle.RightHandSide = start_chamfer_angle
        builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        builder.BooleanOperation.SetTargetBodies([body])
        builder.Tolerance = 0.01
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feature
```
Do **not** cut a bore then add a thread separately — `ThreadBuilder` on an
already-turned cylinder is a dead end (24/24 combinations failed). Full
context: [api-modelling.md §4](api-modelling.md#4-a-threaded-hole-with-real-standard-data),
centering-cone norm values: [norm-knowledge.md](norm-knowledge.md#provisional-centre-hole-form-d-coaxial-with-m6-assumed--norm-original-pending).

## Measure the solid (don't trust the picture)

```python
def measure_faces(body):
    """Returns (cylinder_radii, planar_face_coord_by_axis_index) so a job can
    assert its own geometry instead of trusting a render. AskFaceData's point/
    direction are plain [x, y, z] FLOAT LISTS, not Point3d/Vector3d — point[i],
    never point.X/.Y/.Z."""
    uf = NXOpen.UF.UFSession.GetUFSession()
    cyl_radii, planar_points = [], []
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 16:      # cylinder
            cyl_radii.append(round(radius, 3))
        elif kind == 22:    # plane
            planar_points.append(tuple(round(c, 3) for c in point))
    return sorted(cyl_radii), planar_points
```
`kind`: 16 cylinder, 17 cone, 18 sphere, 19 torus, 22 plane. Full context:
[api-modelling.md §7](api-modelling.md#7-measuring-the-solid-instead-of-trusting-the-picture).

## STEP AP214 export (standalone, no NX session needed)

```cmd
STEP214UG\step214ug.exe <in.prt> o=<out.stp> d=STEP214UG\ugstep214.def l=<out.log>
```
Run from the `.stp`'s own intended directory — `o=<abs path>` is ignored, the
file lands under the translator's CWD instead. `DexManager.CreateStepCreator`
is a dead end (silent no-op). Full context:
[api-modelling.md §8](api-modelling.md#8-step-ap214-export).
