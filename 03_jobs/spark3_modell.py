"""SPARK3 Modell (Phase 1, vollständig, wiederholbar): Wellenrohling + Nut + M6.

Baut auf NEUEM Teil (NewDisplay => angezeigt, kein Session-State-Kampf):
1. Revolve Halbprofil Oe25/Sitz Oe20/Ringnut Oe19 (Schritt 1, ok:true,
   Run 20260906T151807Z-b8fcf525, Re-Edit ok).
2. Passfedernut Form A: Block Length 14 (X 50..64) / Width 4.5 (Y 6.5..11)
/ Height 6 (Z -3..+3), Corner (50, 6.5, -3) -- Abbildung Length->X,
   Width->Y, Height->Z auf Scratch vermessen (Run 20260906T153137Z-8c04fc81).
3. Runde Enden: 2x GeneralHole Oe6 Tiefe 3.5, Punkte auf Mantel (50/64,10,0),
   Tolerance 0.01 -- auf Scratch verifiziert (r=3, Achse Y).
4. M6 stirnseitig (Rezept S3 + hole_probe-Form): Metric Coarse 'M6 x 1.0',
   RadialEngage 0.75, Punkt (70,0,0) auf Stirn, FaceNormal, ThreadDepth 12,
   HoleDepth 14, Tip 118, Startfase Oe6.4/30 (ab Flaeche), Tolerance 0.01.
Offen (kein Raten): koaxiale Zentrierbohrung DIN 332-A/R (braucht Form D).
Undo-Marke je Schritt, Repaint+Takt, Checkpoints, UTF-8, Destroy-finally.
Nur vermessene Zahlen setzen ok:true (dim-Checks mit ComputedSize-Logik:
falsche Assoziation = failed Run, keine falsche Zeichnung spaeter).
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

PROFILE = [
    (0.0, 0.0), (0.0, 11.5), (1.0, 12.5), (45.0, 12.5), (45.0, 10.0),
    (57.45, 10.0), (57.45, 9.5), (58.55, 9.5), (58.55, 10.0),
    (69.0, 10.0), (70.0, 9.0), (70.0, 0.0),
]

REORIENT = NXOpen.Sketch.ViewReorient.FalseValue
WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'steps': [], 'checks': [],
              'assumptions': {
                  'total_length': 70.0, 'main_dia': 25.0,
                  'seat_dia': 20.0, 'seat_range': [45.0, 70.0],
                  'groove_width': 1.1, 'groove_range': [57.45, 58.55],
                  'groove_base_dia': 19.0, 'chamfer': '1x45 both ends',
                  'keyway': 'Form A B6, x 47..67 (Mitte 50..64), '
                            'Boden y=6.5, Flanken z=+-3',
                  'thread': 'M6x1 stirn x=70, Tiefe 12/Bohr 14',
                  'open': 'Zentrierbohrung Form D statt A/R (Regel)'}}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')

    try:
        build(out, result, checkpoint)
        result['ok'] = all(c.get('ok', False) for c in result['checks'])
    except Exception:
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def check(result, label, nominal, found, tol, extra=None):
    entry = {'label': label, 'nominal': nominal, 'found': found,
             'ok': (found is not None) and abs(found - nominal) <= tol}
    if extra is not None:
        entry['extra'] = extra
    result['checks'].append(entry)


def build(out, result, checkpoint, watchable=True):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()

    checkpoint('create part')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 Teil')
    part_path = str(out / (out.name + '.prt'))
    part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView
    result['part'] = part_path

    def repaint():
        try:
            view.Orient(NXOpen.View.Canned.Trimetric,
                        NXOpen.View.ScaleAdjustment.Fit)
            view.UpdateDisplay()
        except Exception as error:
            result['repaint'] = 'WARN: ' + str(error)[:200]

    # --- 1. Datum + Skizze + Revolve ---
    checkpoint('datum')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Datum ZX')
    builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        builder.SetFixedDatumPlane(
            NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        datum_feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    datum_plane = [e for e in datum_feature.GetEntities()
                   if isinstance(e, NXOpen.DatumPlane)][0]

    checkpoint('sketch+revolve')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Rotation')
    builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    try:
        builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        builder.PlaneOrFace.Value = datum_plane
        sketch = builder.Commit()
    finally:
        builder.Destroy()
    sketch.SetName('SKIZZE_DREHKONTUR')
    sketch.Activate(REORIENT)
    points = [NXOpen.Point3d(x, 0.0, r) for x, r in PROFILE]
    curves = [part.Curves.CreateLine(points[i], points[i + 1])
              for i in range(len(points) - 1)]
    curves.append(part.Curves.CreateLine(points[-1], points[0]))
    for curve in curves:
        sketch.AddGeometry(
            curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.Update()
    sketch.Deactivate(REORIENT, NXOpen.Sketch.UpdateLevel.Model)
    section = part.Sections.CreateSection()
    section.AddToSection(
        [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None,
        None, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create,
        False)
    axis = part.Axes.CreateAxis(
        part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)),
        part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN), WITHIN)
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        builder.Section = section
        builder.Axis = axis
        builder.Limits.StartExtend.Value.RightHandSide = '0'
        builder.Limits.EndExtend.Value.RightHandSide = '360'
        builder.BooleanOperation.Type = \
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        builder.Tolerance = 0.01
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    result['steps'].append(
        {'label': 'Rotation', 'feature': feature.JournalIdentifier})
    body = feature.GetBodies()[0]
    repaint()
    if watchable:
        time.sleep(1.5)

    # --- 2. Nut-Mitte (korrigiert: Width 4.5=Y, Height 6=Z) ---
    checkpoint('keyway block')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Passfedernut')
    block = part.Features.CreateBlockFeatureBuilder(None)
    try:
        block.Type = getattr(
            NXOpen.Features, 'BlockFeatureBuilderTypes').OriginAndEdgeLengths
        block.SetLength('14')
        block.SetWidth('4.5')
        block.SetHeight('6')
        block.Origin = NXOpen.Point3d(50.0, 6.5, -3.0)
        block.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Subtract, body)
        block_feature = block.CommitFeature()
        result['steps'].append(
            {'label': 'Nut-Mitte', 'feature': block_feature.JournalIdentifier})
    finally:
        try:
            block.Destroy()
        except Exception:
            pass
    repaint()
    if watchable:
        time.sleep(1.5)

    # --- 3. Runde Enden ---
    checkpoint('keyway ends')
    result['hole_features'] = []
    for i, xc in enumerate((50.0, 64.0)):
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 Nut-Radius %d' % (i + 1))
        hole = part.Features.CreateHolePackageBuilder(None)
        try:
            hole.Type = getattr(
                NXOpen.Features, 'HolePackageBuilderTypes').GeneralHole
            hole.GeneralSimpleHoleDiameter.RightHandSide = '6'
            hole.GeneralSimpleHoleDepth.RightHandSide = '3.5'
            pt = part.Points.CreatePoint(NXOpen.Point3d(xc, 10.0, 0.0))
            hole.HolePosition.AddSmartPoint(pt, 0.01)
            hole.BooleanOperation.Type = NXOpen.GeometricUtilities \
                .BooleanOperation.BooleanType.Subtract
            hole.BooleanOperation.SetTargetBodies([body])
            hole.Tolerance = 0.01
            feat = hole.CommitFeature()
            result['hole_features'].append(feat.JournalIdentifier)
        finally:
            try:
                hole.Destroy()
            except Exception:
                pass
        repaint()
        if watchable:
            time.sleep(1.5)
    result['steps'].append(
        {'label': 'Nut-Radien', 'features': list(result['hole_features'])})

    # --- 4. M6 ---
    checkpoint('thread M6')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 M6')
    thread = part.Features.CreateHolePackageBuilder(None)
    try:
        thread.Type = getattr(
            NXOpen.Features, 'HolePackageBuilderTypes').ThreadedHole
        thread.ThreadStandard = 'Metric Coarse'
        thread.ThreadSize = 'M6 x 1.0'
        thread.RadialEngageOption = '0.75'
        pt = part.Points.CreatePoint(NXOpen.Point3d(70.0, 0.0, 0.0))
        thread.HolePosition.AddSmartPoint(pt, 0.01)
        # ProjectionDirection.DirectionType ist read-only (Run ...434Z);
        # Default (FaceNormal) reicht -- Punkt liegt auf der Stirnflaeche,
        # gleiches Muster wie die Nutlocher (Default, verifiziert).
        thread.ThreadLengthOption = getattr(
            NXOpen.Features,
            'HolePackageBuilderThreadLengthOptions').Custom
        thread.ThreadDepth.RightHandSide = '12'
        thread.HoleDepthLimitOption = getattr(
            NXOpen.Features,
            'HolePackageBuilderHoleDepthLimitOptions').Value
        thread.ThreadedHoleDepth.RightHandSide = '14'
        thread.ThreadedTipAngle.RightHandSide = '118'
        thread.ThreadedStartChamferEnabled = True
        thread.ThreadedStartChamferDiameter.RightHandSide = '6.4'
        thread.ThreadedStartChamferAngle.RightHandSide = '30'
        thread.BooleanOperation.Type = NXOpen.GeometricUtilities \
            .BooleanOperation.BooleanType.Subtract
        thread.BooleanOperation.SetTargetBodies([body])
        thread.Tolerance = 0.01
        thread_feature = thread.CommitFeature()
        result['steps'].append(
            {'label': 'M6', 'feature': thread_feature.JournalIdentifier})
    finally:
        try:
            thread.Destroy()
        except Exception:
            pass
    repaint()
    if watchable:
        time.sleep(1.5)

    # --- 5. Selbstpruefung ---
    checkpoint('verify')
    planes, cyls = [], []
    for face in body.GetFaces():
        try:
            kind, point, direction, box, radius, rad, normv = \
                uf.Modeling.AskFaceData(face.Tag)
        except Exception:
            continue
        if kind == 22:
            planes.append({'p': [round(v, 3) for v in point],
                           'n': [round(v, 3) for v in direction]})
        elif kind == 16:
            cyls.append({'p': [round(v, 3) for v in point],
                         'd': [round(v, 3) for v in direction],
                         'r': round(float(radius), 3)})
    check(result, 'Welle Oe25 r=12.5', 12.5,
          next((c['r'] for c in cyls if abs(c['r'] - 12.5) < 0.01), None),
          0.01)
    check(result, 'Sitz Oe20 r=10', 10.0,
          next((c['r'] for c in cyls if abs(c['r'] - 10.0) < 0.01), None),
          0.01)
    check(result, 'Nutgrund Oe19 r=9.5', 9.5,
          next((c['r'] for c in cyls if abs(c['r'] - 9.5) < 0.01), None),
          0.01)
    floor = [f for f in planes if abs(f['n'][1] - 1.0) < 1e-6
             and abs(f['p'][1] - 6.5) < 0.02]
    check(result, 'Nutboden y=6.5', 6.5,
          (floor[0]['p'][1] if floor else None), 0.02,
          {'faces': len(floor)})
    flm = [f for f in planes if abs(f['n'][2] - 1.0) < 1e-6
           and abs(f['p'][2] + 3.0) < 0.02]
    check(result, 'Nutflanke z=-3', -3.0,
          (flm[0]['p'][2] if flm else None), 0.02, {'faces': len(flm)})
    flp = [f for f in planes if abs(f['n'][2] + 1.0) < 1e-6
           and abs(f['p'][2] - 3.0) < 0.02]
    check(result, 'Nutflanke z=+3', 3.0,
          (flp[0]['p'][2] if flp else None), 0.02, {'faces': len(flp)})
    r3x = sorted(c['p'][0] for c in cyls if abs(c['r'] - 3.0) < 0.02
                 and abs(abs(c['d'][1]) - 1.0) < 1e-6)
    check(result, 'Nutradien Oe6 x=50+64', 1.0,
          (1.0 if (any(abs(x - 50.0) < 0.15 for x in r3x)
                   and any(abs(x - 64.0) < 0.15 for x in r3x)) else 0.0),
          0.0, {'x': r3x})
    tap = [c for c in cyls if abs(c['r'] - 2.5) < 0.2
           and abs(abs(c['d'][0]) - 1.0) < 1e-6 and c['p'][0] > 55.0]
    check(result, 'M6-Kernloch r~2.5 x>55', 2.5,
          (tap[0]['r'] if tap else None), 0.2, {'n': len(tap)})
    result['counts'] = {'planes': len(planes), 'cyls': len(cyls),
                        'bodies': len(list(part.Bodies))}

    checkpoint('save')
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    checkpoint('complete')
