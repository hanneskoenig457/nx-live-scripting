"""SPARK3 Schritt 2b: Nut-Schnitt-Test auf SCRATCH (nicht am Schritt-1-Teil).

Annahme aus Rezept S8 (verifiziert an SPARK2, dortiger Code liegt ausserhalb
dieses Skills und wird NICHT kopiert -- nur die Masszahlen 14/6/4.5):
Block Mitte: Origin-Corner (50, 6.5, -3), Length 14 (X axial), Width 6
(Z quer, Flanken +-3), Height 4.5 (Y hoch, Boden 6.5 bis 11 ueber Flaeche).
Runde Enden: 2x GeneralHole Oe6 an (50,11,0)/(64,11,0), Tolerance 0.01,
Projektion Default. Der Job MISST nach (UF AskFaceData) statt zu glauben:
Bodenebene y=6.5, Flanken z=+-3, Oe6-Zylinder Radius 3 mit Lage/Achse.
Falsche Orientierung => Zahlen weichen ab => geplanter Fail, kein stilles
falsches Teil. Undo-Marke je Schritt, alles in result.json (UTF-8).
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


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'trials': []}
    try:
        run(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result, watchable=True):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()

    result['stage'] = 'scratch revolve'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 scratch')
    scratch_path = str(out / (out.name + '_scratch.prt'))
    part = session.Parts.NewDisplay(scratch_path,
                                    NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView
    result['scratch'] = scratch_path

    builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        builder.SetFixedDatumPlane(
            NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        datum_feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    datum_plane = [e for e in datum_feature.GetEntities()
                   if isinstance(e, NXOpen.DatumPlane)][0]
    builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    try:
        builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        builder.PlaneOrFace.Value = datum_plane
        sketch = builder.Commit()
    finally:
        builder.Destroy()
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
    body = feature.GetBodies()[0]

    def faces_snapshot(label):
        planes, cyls = [], []
        for face in body.GetFaces():
            try:
                kind, point, direction, box, radius, rad, norm = \
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
        result['trials'].append(
            {'label': label, 'planes': len(planes), 'cyls': len(cyls),
             'plane_list': planes, 'cyl_list': cyls})

    faces_snapshot('nach revolve (Referenz)')
    view.Orient(NXOpen.View.Canned.Trimetric,
                NXOpen.View.ScaleAdjustment.Fit)
    view.UpdateDisplay()
    if watchable:
        time.sleep(1.5)

    # --- Trial Block ---
    result['stage'] = 'trial block'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Nut-Mitte Trial')
    block = part.Features.CreateBlockFeatureBuilder(None)
    try:
        block.Type = getattr(
            NXOpen.Features, 'BlockFeatureBuilderTypes').OriginAndEdgeLengths
        block.SetLength('14')
        block.SetWidth('6')
        block.SetHeight('4.5')
        block.Origin = NXOpen.Point3d(50.0, 6.5, -3.0)
        try:
            boolean_type = NXOpen.Features.Feature.BooleanType.Subtract
        except Exception:
            boolean_type = NXOpen.GeometricUtilities.BooleanOperation \
                .BooleanType.Subtract
        block.SetBooleanOperationAndTarget(boolean_type, body)
        block_feature = block.CommitFeature()
        result['block_feature'] = block_feature.JournalIdentifier
        result['block_boolean_path'] = 'Feature.BooleanType' if hasattr(
            NXOpen.Features.Feature, 'BooleanType') else 'GeometricUtilities'
    finally:
        try:
            block.Destroy()
        except Exception:
            pass
    faces_snapshot('nach Block (Erwartung: Boden y=6.5 n=-Y, Flanken z=+-3)')
    view.UpdateDisplay()
    if watchable:
        time.sleep(1.5)

    # --- Trial runde Enden ---
    result['stage'] = 'trial holes'
    hole_ids = []
    for i, xc in enumerate((50.0, 64.0)):
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 Nut-Ende %d Trial' % (i + 1))
        hole = part.Features.CreateHolePackageBuilder(None)
        try:
            hole.Type = getattr(
                NXOpen.Features, 'HolePackageBuilderTypes').GeneralHole
            hole.GeneralSimpleHoleDiameter.RightHandSide = '6'
            hole.GeneralSimpleHoleDepth.RightHandSide = '5'
            pt = part.Points.CreatePoint(NXOpen.Point3d(xc, 11.0, 0.0))
            hole.HolePosition.AddSmartPoint(pt, 0.01)
            hole.BooleanOperation.Type = NXOpen.GeometricUtilities \
                .BooleanOperation.BooleanType.Subtract
            hole.BooleanOperation.SetTargetBodies([body])
            hole.Tolerance = 0.01
            feat = hole.CommitFeature()
            hole_ids.append(feat.JournalIdentifier)
        finally:
            try:
                hole.Destroy()
            except Exception:
                pass
    result['hole_features'] = hole_ids
    faces_snapshot('nach 2x Oe6 (Erwartung: 2 Zylinder r=3, Achse Y, x=50/64)')
    view.UpdateDisplay()
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save scratch'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['note'] = ('Scratch-Teil bleibt geladen (eindeutiger Run-Name); '
                      'kein CloseAll (Session anderer Arbeit respektieren).')
    result['stage'] = 'complete'
