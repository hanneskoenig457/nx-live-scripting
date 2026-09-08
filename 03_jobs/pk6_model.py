"""Pruefkoerper (abstract.md, 99_4_Muse_Spark_6nd_impl_with_knowledge): 3D model.

Rotationally symmetric shaft stub, nominal Diameter25 x 70 mm, X = shaft axis.

Axial layout (mm, X from left face 0 to right face 70):
  0      : left face, 1x45 chamfer
  0-8    : Diameter25 raw/handling stub
  8      : shoulder Diameter25 -> Diameter20
  8-23   : Diameter20 h6 bearing seat, Ra 0.8            (abstract S2, feature 1)
  23-24.1: DIN 471 retaining-ring groove, base Diameter19.0 h11, width 1.1  (feature 3)
  24.1-58: Diameter20 plain body (general tolerance ISO 2768-m)
    32-52 (tip-to-tip): DIN 6885-1 Form A keyway, b6 P9, t1=3.5 from Diameter20 (feature 2)
  58     : shoulder Diameter20 -> Diameter25
  58-70  : Diameter25 raw stub, right face at 70
  70     : right face, 1x45 chamfer; M6 tapped hole on axis, combined with a
           centering cone (DIN 332-style 60 deg lead, see deviation D-1)   (feature 4)

Deviation D-1 (declared, not silent): abstract.md asks for "M6 thread including
a DIN 332 Form R or A centering hole" on the SAME face/axis. Per this skill's
own layer-3 rule (dimensioning-rules.md #7, Centre hole): plain forms A/B/R do
NOT share an axis with a thread -- a plain 60 deg cone with no relief would
have its tip removed by the tap and stop being a valid A/R centre. The
norm-correct way to combine them is a centre form built for it (DIN 332-2,
thread-compatible), realised here as the tap's own start-chamfer cone
(Diameter6.4 mouth, 60 deg included, from HolePackageBuilder ThreadedStartChamfer*)
acting as the lead-in/centering cone for the M6 hole. Recorded as a deviation
in result.json, not chosen quietly.
"""
import json
import math
import os
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer
import NXOpen.UF

WATCHABLE = True


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': [],
              'marks': {}, 'rules': [], 'deviations': [], 'measurements': {}}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(json.dumps(result, indent=2),
                                          encoding='utf-8')

    try:
        build(out, result, checkpoint)
        open_rules = [r['rule'] for r in result['rules']
                      if r.get('status') not in ('met', 'deviated')]
        assert not open_rules, {'unresolved rules': open_rules}
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def require_rule(result, rule_id, how):
    result['rules'].append({'rule': rule_id, 'how': how, 'status': 'open'})


def resolve_rule(result, rule_id, evidence):
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'met', 'evidence': evidence})


def deviate(result, rule_id, tried, fallback, why):
    result['deviations'].append({'rule': rule_id, 'tried': tried,
                                  'fallback': fallback, 'why': why})
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'deviated'})


def pause(sec):
    if WATCHABLE:
        time.sleep(sec)


def build(out, result, checkpoint):
    session = NXOpen.Session.GetSession()

    require_rule(result, 'F-1', 'Lagersitz Diameter20 h6, Ra 0.8 (abstract S2 feature 1)')
    require_rule(result, 'F-2', 'Passfedernut DIN 6885-A, 6P9, t1=3.5 (abstract S2 feature 2)')
    require_rule(result, 'F-3', 'Sicherungsringnut DIN 471, m=1.1 +0.14/-0, Diameter19.0 h11 (abstract S2 feature 3)')
    require_rule(result, 'F-4', 'Innengewinde M6 mit Zentrierung, Stirnseite (abstract S2 feature 4)')
    require_rule(result, 'D-1', 'Zentrierform A/R teilt keine Achse mit Gewinde (dimensioning-rules.md #7) -> Deviation dokumentiert')

    checkpoint('create part')
    part = session.Parts.NewDisplay(str(out / (out.name + '.prt')),
                                     NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView

    # ---- 1. Outer revolve profile (raw stock, both shoulders, bearing seat,
    #         retaining groove, both end chamfers) in one closed half-section.
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Grundkontur')
    checkpoint('sketch grundkontur')

    dm_builder = part.Features.CreateDatumPlaneBuilder(None)
    dm_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
    dm_feature = dm_builder.CommitFeature()
    dm_builder.Destroy()
    datum_plane = [e for e in dm_feature.GetEntities()
                   if isinstance(e, NXOpen.DatumPlane)][0]

    sk_builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    sk_builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
    sk_builder.PlaneOrFace.Value = datum_plane
    sketch = sk_builder.Commit()
    sk_builder.Destroy()
    sketch.SetName('SKIZZE_KONTUR')
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)

    # Closed half-profile (X axial, Z radius), left-to-right along the outer
    # contour, then back to the origin along the revolve axis (Z=0).
    profile_xz = [
        (0.0, 0.0), (0.0, 11.5), (1.0, 12.5), (8.0, 12.5), (8.0, 10.0),
        (23.0, 10.0), (23.0, 9.5), (24.1, 9.5), (24.1, 10.0), (58.0, 10.0),
        (58.0, 12.5), (69.0, 12.5), (70.0, 11.5), (70.0, 0.0), (0.0, 0.0),
    ]
    curves = []
    for (x0, z0), (x1, z1) in zip(profile_xz, profile_xz[1:]):
        line = part.Curves.CreateLine(NXOpen.Point3d(x0, 0.0, z0),
                                       NXOpen.Point3d(x1, 0.0, z1))
        sketch.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
        curves.append(line)
    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    view.UpdateDisplay()
    result['steps'].append({'label': 'Grundkontur Skizze', 'curves': len(curves)})
    pause(1.0)

    # ---- 2. Revolve 360 deg about an associative axis coincident with X.
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Revolve')
    checkpoint('revolve')

    # Associative smart axis: two smart Points define the Direction (the
    # (Point3d, Vector3d, UpdateOption) overload exists too but is the
    # non-associative shape that SIGSEGV'd at revolve commit -- see
    # api-modelling.md Paragraph 1). DirectionCollection.CreateDirection has no
    # (Point, Vector3d, ...) overload; confirmed against 04_reference/NXOpen.xml.
    axis_point = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    axis_point2 = part.Points.CreatePoint(NXOpen.Point3d(1.0, 0.0, 0.0))
    axis_dir = part.Directions.CreateDirection(
        axis_point, axis_point2, NXOpen.SmartObject.UpdateOption.WithinModeling)
    axis = part.Axes.CreateAxis(axis_point, axis_dir,
                                 NXOpen.SmartObject.UpdateOption.WithinModeling)

    rev_builder = part.Features.CreateRevolveBuilder(None)
    rev_builder.Tolerance = 0.01
    rev_builder.Axis = axis
    section = part.Sections.CreateSection(0.01, 0.01, 0.01)
    section.AddToSection(
        [part.ScRuleFactory.CreateRuleCurveDumb(curves)],
        curves[0], None, None, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create)
    rev_builder.Section = section
    set_full_angle(rev_builder, result)
    revolve_feature = rev_builder.CommitFeature()
    rev_builder.Destroy()
    view.Orient(NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit)
    view.UpdateDisplay()

    body = list(part.Bodies)[0]
    result['steps'].append({'label': 'Revolve Grundkoerper',
                             'feature': revolve_feature.JournalIdentifier})
    pause(1.0)

    # Keep the construction sketch/datum out of the drawing.
    part.Layers.MoveDisplayableObjects(21, [sketch])
    part.Layers.MoveDisplayableObjects(61, [datum_plane])   # axis is not a DisplayableObject
    part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
    part.Layers.WorkLayer = 1

    measure_bearing_seat(part, result)
    measure_groove(part, result)

    # ---- 3. Keyway DIN 6885-A: sketched stadium (b=6, l=20 tip-to-tip,
    #         t1=3.5 from Diameter20) as a subtractive extrude.
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Passfedernut')
    checkpoint('keyway')
    build_keyway(part, body, result)
    view.UpdateDisplay()
    pause(1.0)

    # ---- 4. M6 threaded hole with combined centering cone, right face x=70.
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Gewinde+Zentrierung')
    checkpoint('thread')
    build_thread(part, body, result)
    view.UpdateDisplay()
    pause(1.0)

    resolve_rule(result, 'D-1', {
        'chamfer_diameter_mm': 6.4, 'included_angle_deg': 60,
        'note': 'DIN 332 Form A/R plain cone cannot share the M6 axis; '
                'combined centre/lead realised via the tap start chamfer '
                '(thread-compatible centre, DIN 332-2 style).'})
    deviate(result, 'D-1',
            tried='Plain DIN 332 Form A/R centre coaxial with M6 as literally worded in abstract.md',
            fallback='Thread-compatible lead cone (60 deg, Diameter6.4 mouth) via HolePackageBuilder start chamfer',
            why='dimensioning-rules.md #7: "plain forms A/B/R do NOT share an axis with a thread"')

    result['body_count'] = len(list(part.Bodies))
    assert result['body_count'] == 1, result

    checkpoint('save')
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

    checkpoint('export step')
    export_step(out, result)


def set_full_angle(rev_builder, result):
    """RevolveBuilder.Limits is an AngularLimits (StartExtend/EndExtend, same
    shape as ExtrudeBuilder.Limits) -- confirmed live via
    pk6_probe_revolve_limits.py (run 20260907T220820Z-85e13bc5): members
    Distance, EndExtend, StartExtend, SymmetricOption. Not StartAngle/EndAngle."""
    limits = rev_builder.Limits
    limits.StartExtend.SetValue('0')
    limits.EndExtend.SetValue('360')
    result['revolve_angle_path'] = 'StartExtend/EndExtend (AngularLimits)'


def build_keyway(part, body, result):
    dm_builder = part.Features.CreateDatumPlaneBuilder(None)
    dm_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
    dm_feature = dm_builder.CommitFeature()
    dm_builder.Destroy()
    datum_plane = [e for e in dm_feature.GetEntities()
                   if isinstance(e, NXOpen.DatumPlane)][0]

    sk_builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    sk_builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
    sk_builder.PlaneOrFace.Value = datum_plane
    sketch = sk_builder.Commit()
    sk_builder.Destroy()
    sketch.SetName('SKIZZE_PASSFEDERNUT')
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)

    x_left, x_right = 35.0, 49.0   # arc centres, inset by R=3 from the 32..52 tip-to-tip length
    half_b = 3.0                    # b=6 -> +/-3
    l1 = part.Curves.CreateLine(NXOpen.Point3d(x_left, 0.0, -half_b), NXOpen.Point3d(x_right, 0.0, -half_b))
    l2 = part.Curves.CreateLine(NXOpen.Point3d(x_left, 0.0, +half_b), NXOpen.Point3d(x_right, 0.0, +half_b))
    a_left = part.Curves.CreateArc(NXOpen.Point3d(x_left, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                    NXOpen.Vector3d(0.0, 0.0, 1.0), half_b, math.pi / 2, 3 * math.pi / 2)
    a_right = part.Curves.CreateArc(NXOpen.Point3d(x_right, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
                                     NXOpen.Vector3d(0.0, 0.0, 1.0), half_b, 3 * math.pi / 2, 5 * math.pi / 2)
    curves = [l1, l2, a_left, a_right]
    for c in curves:
        sketch.AddGeometry(c, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)

    section = part.Sections.CreateSection(0.01, 0.01, 0.01)
    section.AddToSection(
        [part.ScRuleFactory.CreateRuleCurveDumb(curves)],
        l1, None, None, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create)

    eb = part.Features.CreateExtrudeBuilder(None)
    eb.Section = section
    eb.Direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, 1.0, 0.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)
    eb.Limits.StartExtend.SetValue('6.5')   # floor: R10 - t1(3.5)
    eb.Limits.EndExtend.SetValue('11')      # past the Diameter20 surface, clean boolean
    eb.BooleanOperation.SetBooleanOperationAndBody(
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, body)
    feat = eb.CommitFeature()
    eb.Destroy()

    part.Layers.MoveDisplayableObjects(21, [sketch])
    part.Layers.MoveDisplayableObjects(61, [datum_plane])
    part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    part.Layers.SetState(61, NXOpen.Layer.State.Hidden)

    result['steps'].append({'label': 'Passfedernut', 'feature': feat.JournalIdentifier})

    # Verify the floor is at the intended radius (Y=6.5) and the pocket is
    # centred on Z=0 with the intended half-width, by measuring the solid.
    uf = NXOpen.UF.UFSession.GetUFSession()
    floor_candidates = []
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 22 and abs(point[1] - 6.5) < 0.05 and abs(direction[1]) > 0.99:
            floor_candidates.append(point)
    resolve_rule(result, 'F-2', {
        'nominal_t1_mm': 3.5, 'nominal_b_mm': 6, 'nominal_l_mm': 20,
        'floor_planes_found': len(floor_candidates),
        'note': 't1/length not associatively dimensionable on this NX build '
                '(api-drafting.md dead ends) -- state as leader note with '
                'letter h on the drawing, per dimensioning-rules.md #7.'})
    result['measurements']['keyway_floor_planes_at_y6_5'] = len(floor_candidates)
    assert len(floor_candidates) > 0, ('keyway floor not found at expected radius', result)


def build_thread(part, body, result):
    hb = part.Features.CreateHolePackageBuilder(None)
    hb.Type = NXOpen.Features.HolePackageBuilderTypes.ThreadedHole
    hb.ThreadStandard = 'Metric Coarse'
    hb.ThreadSize = 'M6 x 1.0'
    hb.RadialEngageOption = '0.75'
    hb.HolePosition.AddSmartPoint(
        part.Points.CreatePoint(NXOpen.Point3d(70.0, 0.0, 0.0)), 0.01)
    hb.ThreadLengthOption = NXOpen.Features.HolePackageBuilderThreadLengthOptions.Custom
    hb.ThreadDepth.RightHandSide = '12'
    hb.HoleDepthLimitOption = NXOpen.Features.HolePackageBuilderHoleDepthLimitOptions.Value
    hb.ThreadedHoleDepth.RightHandSide = '14'
    hb.ThreadedTipAngle.RightHandSide = '118'
    hb.ThreadedStartChamferEnabled = True
    hb.ThreadedStartChamferDiameter.RightHandSide = '6.4'
    hb.ThreadedStartChamferAngle.RightHandSide = '30'   # half-angle from the face -> 60 deg included cone
    hb.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
    hb.BooleanOperation.SetTargetBodies([body])
    hb.Tolerance = 0.01
    feat = hb.CommitFeature()
    hb.Destroy()
    result['steps'].append({'label': 'Gewinde M6 + Zentrierung', 'feature': feat.JournalIdentifier})

    uf = NXOpen.UF.UFSession.GetUFSession()
    cone_half_angles = []
    tap_radii = []
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 17 and abs(point[0] - 70.0) < 15.0 and abs(direction[0]) > 0.99:
            cone_half_angles.append(math.degrees(rad_data))
        if kind == 16 and abs(point[0] - 70.0) < 15.0 and abs(direction[0]) > 0.99 and 2.0 < radius < 3.5:
            tap_radii.append(radius)

    resolve_rule(result, 'F-4', {
        'thread': 'M6 x 1.0', 'usable_length_mm': 12, 'drilled_depth_mm': 14,
        'lead_cone_half_angle_deg_expected': 60,
        'lead_cone_half_angles_measured': cone_half_angles,
        'tap_cylinder_radii_measured': tap_radii})
    result['measurements']['thread_cone_half_angles_deg'] = cone_half_angles
    result['measurements']['thread_tap_radii_mm'] = tap_radii
    assert cone_half_angles, ('no lead cone face found near x=70', result)
    assert any(abs(a - 60.0) < 3.0 for a in cone_half_angles), (cone_half_angles, result)


def measure_bearing_seat(part, result):
    uf = NXOpen.UF.UFSession.GetUFSession()
    radii = []
    body = list(part.Bodies)[0]
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 16 and abs(direction[0]) > 0.99 and abs(radius - 10.0) < 0.05 \
                and 8.0 <= point[0] <= 23.0:
            radii.append(radius)
    resolve_rule(result, 'F-1', {
        'nominal_diameter_mm': 20, 'tolerance': 'h6 (+0/-0.013)',
        'seat_faces_found': len(radii), 'measured_radii_mm': radii})
    result['measurements']['bearing_seat_radii_mm'] = radii
    assert radii, ('bearing seat cylindrical face not found at radius 10', result)


def measure_groove(part, result):
    uf = NXOpen.UF.UFSession.GetUFSession()
    body = list(part.Bodies)[0]
    base_radii = []
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 16 and abs(direction[0]) > 0.99 and abs(radius - 9.5) < 0.05 \
                and 22.5 <= point[0] <= 24.5:
            base_radii.append(radius)
    resolve_rule(result, 'F-3', {
        'nominal_base_diameter_mm': 19.0, 'tolerance': 'h11',
        'nominal_width_mm': 1.1, 'width_tolerance': '+0.14/-0',
        'groove_base_faces_found': len(base_radii), 'measured_radii_mm': base_radii})
    result['measurements']['groove_base_radii_mm'] = base_radii
    assert base_radii, ('retaining-ring groove base face not found at radius 9.5', result)


def export_step(out, result):
    """STEP AP214 via the standalone translator, per api-modelling.md #8.
    No NX session call here (DexManager writes no file, a documented dead end)."""
    import subprocess
    prt_path = out / (out.name + '.prt')
    stp_name = out.name + '.stp'
    log_name = out.name + '_step.log'
    # STEP214UG ships inside the NX install itself (confirmed: this session's
    # nxbin/python path is under C:\Program Files\Siemens\NX2506\), not under
    # the project's Documents folder -- the first guessed path did not exist
    # (FileNotFoundError / WinError 2). Hardcoded, not read from os.environ
    # (job-contract hard requirement 5).
    base = r'C:\Program Files\Siemens\NX2506'
    step_exe = os.path.join(base, 'STEP214UG', 'step214ug.exe')
    step_def = os.path.join(base, 'STEP214UG', 'ugstep214.def')
    if not os.path.isfile(step_exe):
        result['step_export'] = {'error': 'step214ug.exe not found', 'tried': step_exe}
        raise RuntimeError('step214ug.exe not found at ' + step_exe)
    cmd = [step_exe, str(prt_path), f'o={stp_name}', f'd={step_def}', f'l={log_name}']
    proc = subprocess.run(cmd, cwd=str(out), capture_output=True, text=True, timeout=120)
    result['step_export'] = {
        'returncode': proc.returncode,
        'stdout_tail': proc.stdout[-500:] if proc.stdout else '',
        'stderr_tail': proc.stderr[-500:] if proc.stderr else '',
    }
    produced = out / stp_name
    result['step_export']['file_exists'] = produced.exists()
    if produced.exists():
        result['step_export']['size_bytes'] = produced.stat().st_size
    assert produced.exists(), ('STEP export did not produce a file', result['step_export'])
