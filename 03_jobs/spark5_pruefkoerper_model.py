"""Spark5-Pruefkoerper (99_3_Muse_Spark_5nd_impl_with_knowledge, abstract.md Phase 1).

Wellenstummel ca. O25 x 70, Werkstoff 1.4301/C45 (Materialwahl liegt beim
Anbieter/Bestellung, hier ohne Einfluss auf die Geometrie):

  * Lagersitz O20 h6, Ra 0.8
  * Passfedernut DIN 6885 Form A, 6 P9 (Breite), Nuttiefe t1 nach Norm-Tabelle
  * Sicherungsring-Einstich DIN 471 fuer Wellen-O20 (Breite 1.1 +0.14, Nutgrund O19.0 h11)
  * Stirnseitiges Innengewinde M6 mit Zentrierung (Form D, koaxial - ASSUMED,
    siehe references/norm-knowledge.md, Normoriginal steht aus)

Achsiale Stationen sind im Abstract nicht spezifiziert; die hier gewaehlte
Auslegung ist eine eigene, dokumentierte Konstruktionsentscheidung (siehe
result['rules'] / ASSUME-LAYOUT) und keine Norm- oder Kundenvorgabe.

Nur EIN Absatz (O25 -> O20h6): der Lagersitz laeuft bis zum rechten Wellenende
durch, axial gehalten durch den Absatz auf der einen und den Sicherungsring
auf der anderen Seite - ein zweiter Ruecksprung auf O25 waere funktionslos.

Rohkontur und Passfedernut sind als Skizzen-Features modelliert (Sketch auf
ZX-Datumebene), nicht als lose Kurven - siehe api-modelling.md Paragraph 3.

Frisch geschrieben fuer dieses Projekt anhand der Skill-Referenzen
(api-modelling.md, norm-knowledge.md, dimensioning-rules.md) - keine
Wiederverwendung der Vorgaenger-Implementierungen (spark3_*/spark4_*).
"""
import json
import os
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer
import NXOpen.UF

WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling

# --- eigene Auslegung (Radien/Stationen in mm) ---------------------------
R_STOCK = 12.5     # O25 Rohteil
R_SEAT = 10.0      # O20 h6 Lagersitz (Nennmass; Toleranz erst in der Zeichnung)
R_GROOVE = 9.5     # DIN 471 Nutgrund O19.0 (h11 auf Zeichnung)
R_KEY_FLOOR = 6.5  # Nuttiefe t1 = 3.5 fuer d=20 (Bereich 17-22, DIN 6885-1)
KEY_HALF_WIDTH = 3.0  # Nutbreite 6 (P9 auf Zeichnung)

X_SHOULDER = 20.0                    # einziger Absatz O25 -> O20h6
X_KEY_L, X_KEY_R = 26.0, 38.0        # Bogenmittelpunkte, Geradenlaenge 12 -> Gesamtlaenge 18
X_GROOVE_L, X_GROOVE_R = 46.5, 47.6  # Breite 1.1
X_END = 70.0                          # Lagersitz laeuft bis hierhin durch


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': [],
              'rules': [], 'deviations': [], 'marks': {}}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

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


def build(out, result, checkpoint, watchable=True):
    session = NXOpen.Session.GetSession()

    require_rule(result, 'ABSTRACT-2',
                 'O25x70 Wellenstummel mit 4 Passungsmerkmalen aus abstract.md Abschnitt 2')
    require_rule(result, 'ASSUME-LAYOUT',
                 'Abstract laesst axiale Stationen offen; eigene Auslegung, hier dokumentiert')
    require_rule(result, 'DIN6885-t1',
                 'Nuttiefe t1=3.5 fuer Wellendurchmesser 20 (Bereich 17-22) aus DIN 6885-1 Tabelle')
    require_rule(result, 'NORM-M6-ZENTR',
                 'M6+Zentrierung Form D nach norm-knowledge.md (ASSUMED, Normoriginal ISO 6411/DIN 332 pending)')

    part_name = out.name
    checkpoint('create part')
    part = session.Parts.NewDisplay(str(out / (part_name + '.prt')), NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView

    sketches = []
    datums = []

    profile = [
        (0.0, 0.0), (0.0, R_STOCK - 1.0), (1.0, R_STOCK),
        (X_SHOULDER, R_STOCK), (X_SHOULDER, R_SEAT),
        (X_GROOVE_L, R_SEAT), (X_GROOVE_L, R_GROOVE),
        (X_GROOVE_R, R_GROOVE), (X_GROOVE_R, R_SEAT),
        (X_END - 1.0, R_SEAT), (X_END, R_SEAT - 1.0), (X_END, 0.0),
    ]

    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Rohkoerper Revolve')
    checkpoint('revolve')
    datum_plane = zx_datum_plane(part)
    datums.append(datum_plane)
    revolve_feature, body, revolve_sketch = revolve_profile(part, datum_plane, profile)
    sketches.append(revolve_sketch)
    view.Orient(NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit)
    view.UpdateDisplay()
    result['steps'].append({'label': 'Rohkoerper Revolve',
                             'feature': revolve_feature.JournalIdentifier})
    resolve_rule(result, 'ABSTRACT-2', 'Revolve committed, 1 Body vorhanden')
    if watchable:
        time.sleep(1.5)

    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Passfedernut DIN 6885-A')
    checkpoint('keyway')
    key_feature, key_sketch = keyway(part, datum_plane, body, X_KEY_L, X_KEY_R,
                                      KEY_HALF_WIDTH, R_KEY_FLOOR, R_SEAT)
    sketches.append(key_sketch)
    view.UpdateDisplay()
    result['steps'].append({'label': 'Passfedernut', 'feature': key_feature.JournalIdentifier})
    resolve_rule(result, 'DIN6885-t1',
                 'Nutgrundradius %.1f = %.1f - 3.5' % (R_KEY_FLOOR, R_SEAT))
    if watchable:
        time.sleep(1.5)

    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'M6 + Zentrierung Form D')
    checkpoint('m6_center')
    thread_feature = m6_with_center(part, body)
    view.UpdateDisplay()
    result['steps'].append({'label': 'M6+Zentrierung', 'feature': thread_feature.JournalIdentifier})
    resolve_rule(result, 'NORM-M6-ZENTR',
                 'ThreadSize=M6 x 1.0, ThreadedStartChamferAngle=60 (Leitkegel 60 Grad eingeschlossen)')
    if watchable:
        time.sleep(1.5)

    resolve_rule(result, 'ASSUME-LAYOUT',
                 'x0..20 O25 | 20..70 O20h6 Sitz durchgehend (nur 1 Absatz bei x=20; '
                 'Nut Bogenmitten 26/38, Ring 46.5..47.6); siehe Docstring/result '
                 'fuer Begruendung; keine Norm- oder Kundenvorgabe')

    checkpoint('cleanup layers')
    if sketches:
        part.Layers.MoveDisplayableObjects(21, sketches)
        part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    if datums:
        part.Layers.MoveDisplayableObjects(61, datums)
        part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
    part.Layers.WorkLayer = 1

    checkpoint('measure')
    radii, planar_y = measure_faces(body)
    result['radii_found_mm'] = radii
    result['planar_y_found_mm'] = planar_y
    expected_cyl = {'stock_O25': R_STOCK, 'seat_O20h6': R_SEAT,
                    'din471_groove_O19': R_GROOVE}
    result['radii_expected_mm'] = expected_cyl
    missing = [name for name, exp in expected_cyl.items()
               if not any(abs(r - exp) < 0.05 for r in radii)]
    if not any(abs(y - (-R_KEY_FLOOR)) < 0.05 for y in planar_y):
        missing.append('keyway_floor_plane(Y=%.1f)' % -R_KEY_FLOOR)
    assert not missing, {'expected geometry not found on solid': missing,
                          'radii_found': radii, 'planar_y_found': planar_y}

    checkpoint('save')
    view.Fit()
    view.UpdateDisplay()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    result['body_count'] = len(list(part.Bodies))
    assert result['body_count'] == 1, result


def smart_x_axis(part):
    origin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN)
    return part.Axes.CreateAxis(origin, direction, WITHIN)


def zx_datum_plane(part):
    builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return [e for e in feature.GetEntities() if isinstance(e, NXOpen.DatumPlane)][0]


def make_sketch(part, datum_plane, name, curves):
    """Wraps already-created in-place curves into a real Sketch feature
    (api-modelling.md Paragraph 3) instead of leaving them as loose curves."""
    builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    try:
        builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        builder.PlaneOrFace.Value = datum_plane
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


def revolve_profile(part, datum_plane, profile):
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
    body.SetName('WELLENSTUMMEL')
    return feature, body, sketch


def keyway(part, datum_plane, body, x_left_arc, x_right_arc, half_width, floor_r, seat_r):
    import math
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
        # -Y statt +Y: die Nut soll zur Kamera der Front-Ansicht zeigen (dort
        # sichtbar), nicht auf der von ihr abgewandten Seite liegen.
        eb.Direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(0.0, -1.0, 0.0), WITHIN)
        eb.Limits.StartExtend.SetValue(str(floor_r))
        eb.Limits.EndExtend.SetValue(str(seat_r + 1.0))
        eb.BooleanOperation.SetBooleanOperationAndBody(
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract, body)
        feature = eb.CommitFeature()
    finally:
        eb.Destroy()
    return feature, sketch


def m6_with_center(part, body):
    builder = part.Features.CreateHolePackageBuilder(None)
    try:
        builder.Type = NXOpen.Features.HolePackageBuilderTypes.ThreadedHole
        builder.ThreadStandard = 'Metric Coarse'
        builder.ThreadSize = 'M6 x 1.0'
        builder.RadialEngageOption = '0.75'
        pt = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        builder.HolePosition.AddSmartPoint(pt, 0.01)
        builder.ThreadLengthOption = NXOpen.Features.HolePackageBuilderThreadLengthOptions.Custom
        builder.ThreadDepth.RightHandSide = '12'
        builder.HoleDepthLimitOption = NXOpen.Features.HolePackageBuilderHoleDepthLimitOptions.Value
        builder.ThreadedHoleDepth.RightHandSide = '14'
        builder.ThreadedTipAngle.RightHandSide = '118'
        builder.ThreadedStartChamferEnabled = True
        builder.ThreadedStartChamferDiameter.RightHandSide = '6.4'
        builder.ThreadedStartChamferAngle.RightHandSide = '60'
        builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Subtract
        builder.BooleanOperation.SetTargetBodies([body])
        builder.Tolerance = 0.01
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feature


def measure_faces(body):
    uf = NXOpen.UF.UFSession.GetUFSession()
    cyl_radii = []
    planar_y = []
    for face in body.GetFaces():
        kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
        if kind == 16:
            cyl_radii.append(round(radius, 3))
        elif kind == 22:
            # UF_MODL_ask_face_data returns point/dir as plain float lists [x, y, z],
            # not Point3d/Vector3d objects.
            planar_y.append(round(point[1], 3))
    return sorted(cyl_radii), sorted(planar_y)
