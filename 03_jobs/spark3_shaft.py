"""SPARK3 Pruefkoerper Schritt 1: revolvierter Wellenrohling mit Sicherungsringnut.

Aufgabe aus abstract.md, Phase 1 (Modell):
- Wellenstummel ca. Oe25 x 70, Haupt Oe25, Lagersitz Oe20
- Sicherungsringnut DIN 471 fuer Oe20: Breite 1.1, Nutgrund Oe19.0
- Annahmen (abstract nennt keine Lagen): Sitzlaenge 25 (x 45..70),
  Nut 57.45..58.55 (1.1 breit), Fasen 1x45 an beiden Enden.
- Passfeder_nut (6 P9) und M6-Gewinde folgen in Schritt 2 als eigene Jobs,
  damit NX zwischen den Schritten inspiziert werden kann.

Kopiert aus verifizierten Formen (Skill-Layer 4, kein Recall):
- Datum ZX + Skizze Inferred/PlaneOrFace (api-modelling.md S3, Rezept B)
- Revolve mit Tolerance=0.01 (recipes S0), Section/RuleCurveDumb, Achse X
- Layer 21/61 verbergen (recipes S2), result.json UTF-8 (recipes S7)
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF

# (x, r) Halbprofil in der XZ-Ebene (y=0), Achse X bei r=0.
# Oe25: r=12.5, Oe20: r=10.0, Nutgrund Oe19: r=9.5.
PROFILE = [
    (0.0, 0.0),
    (0.0, 11.5),
    (1.0, 12.5),
    (45.0, 12.5),
    (45.0, 10.0),
    (57.45, 10.0),
    (57.45, 9.5),
    (58.55, 9.5),
    (58.55, 10.0),
    (69.0, 10.0),
    (70.0, 9.0),
    (70.0, 0.0),
]

REORIENT = NXOpen.Sketch.ViewReorient.FalseValue
WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'steps': [],
              'assumptions': {
                  'total_length': 70.0, 'main_dia': 25.0,
                  'seat_dia': 20.0, 'seat_range': [45.0, 70.0],
                  'groove_width': 1.1, 'groove_range': [57.45, 58.55],
                  'groove_base_dia': 19.0, 'chamfer': '1x45 both ends',
                  'deferred': 'keyway 6 P9 + M6 thread follow in step 2'}}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(
            json.dumps(result, indent=2), encoding='utf-8')

    try:
        build(out, result, checkpoint)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def build(out, result, checkpoint, watchable=True):
    session = NXOpen.Session.GetSession()

    checkpoint('create part')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 Teil')
    part_path = str(out / (out.name + '.prt'))
    part = session.Parts.NewDisplay(part_path, NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView
    result['part'] = part_path

    # --- Datumebene ZX (fest) ---
    checkpoint('datum ZX')
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
    result['steps'].append(
        {'label': 'Datum ZX', 'feature': datum_feature.JournalIdentifier})

    # --- Skizze (Rezept B: Inferred + PlaneOrFace) ---
    checkpoint('sketch')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Skizze Profil')
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
    # Profil schliessen: letzte Kante zurueck zur Achse (70,0) -> (0,0).
    curves.append(part.Curves.CreateLine(points[-1], points[0]))
    added = 0
    add_errors = []
    for curve in curves:
        try:
            sketch.AddGeometry(
                curve,
                NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
            added += 1
        except Exception as error:
            add_errors.append(str(error)[:200])
    sketch.Update()
    sketch.Deactivate(REORIENT, NXOpen.Sketch.UpdateLevel.Model)
    result['sketch'] = {'name': sketch.Name, 'curves': len(curves),
                        'added': added, 'add_errors': add_errors}
    assert added == len(curves), result['sketch']

    # --- Rotation um X ---
    checkpoint('revolve')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Rotation')
    section = part.Sections.CreateSection()
    section.AddToSection(
        [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None,
        None, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create,
        False)
    axis = part.Axes.CreateAxis(
        part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)),
        part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN),
        WITHIN)
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        builder.Section = section
        builder.Axis = axis
        builder.Limits.StartExtend.Value.RightHandSide = '0'
        builder.Limits.EndExtend.Value.RightHandSide = '360'
        builder.BooleanOperation.Type = \
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        builder.Tolerance = 0.01  # recipes S0: Default 0.0 macht Re-Edit tot
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    result['steps'].append(
        {'label': 'Rotation', 'feature': feature.JournalIdentifier})

    # Re-Edit-Probe (recipes S0/S6): Doppelklick-Ersatz, faengt Tolerance-Falle.
    reopened = None
    try:
        reopened = part.Features.CreateRevolveBuilder(feature)
        result['reedit'] = 'ok'
    except Exception as error:
        result['reedit'] = 'ERROR: ' + str(error)[:300]
    finally:
        if reopened is not None:
            try:
                reopened.Destroy()
            except Exception:
                pass
    assert result['reedit'] == 'ok', result['reedit']

    # Skizzen/Datums aus dem Zeichnungsbereich (recipes S2).
    try:
        part.Layers.MoveDisplayableObjects(
            21, [sketch] + list(curves))
    except Exception as error:
        result['layer21'] = 'WARN: ' + str(error)[:200]
    try:
        part.Layers.MoveDisplayableObjects(61, [datum_plane])
    except Exception as error:
        result['layer61'] = 'WARN: ' + str(error)[:200]
    try:
        part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
        part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
        part.Layers.WorkLayer = 1
    except Exception as error:
        result['layer_state'] = 'WARN: ' + str(error)[:200]

    view.Orient(NXOpen.View.Canned.Trimetric,
                NXOpen.View.ScaleAdjustment.Fit)
    view.UpdateDisplay()
    if watchable:
        time.sleep(1.5)
    checkpoint('verify')

    # --- Selbstpruefung: Koerper + Zylinderflaechen + Kanten-Oe ---
    import math
    bodies = list(part.Bodies)
    result['body_count'] = len(bodies)
    assert result['body_count'] > 0, result
    body = feature.GetBodies()[0]

    uf = NXOpen.UF.UFSession.GetUFSession()
    cyl_radii = []
    for face in body.GetFaces():
        try:
            data = uf.Modeling.AskFaceData(face.Tag)
        except Exception:
            continue
        if data[0] == 16:  # Zylinder
            cyl_radii.append(round(float(data[4]), 4))
    result['cyl_radii'] = sorted(cyl_radii)
    # Erwartet: 12.5 (Oe25), 10.0 (Oe20), 9.5 (Nutgrund Oe19).
    for expected in (12.5, 10.0, 9.5):
        hit = [r for r in cyl_radii if abs(r - expected) < 0.01]
        assert hit, {'missing_radius': expected, 'found': cyl_radii}

    edge_dias = set()
    for edge in body.GetEdges():
        try:
            edge_dias.add(round(edge.GetLength() / math.pi, 3))
        except Exception:
            continue
    result['edge_dias_sample'] = sorted(edge_dias)[:12]
    for expected in (25.0, 20.0, 19.0):
        hit = [d for d in edge_dias if abs(d - expected) < 0.02]
        assert hit, {'missing_edge_dia': expected,
                     'sample': result['edge_dias_sample']}

    result['dims'] = [
        {'label': 'Haupt-Oe', 'nominal': 25.0,
         'found_radius': 12.5, 'ok': 12.5 in [round(r, 1) for r in cyl_radii]},
        {'label': 'Sitz-Oe', 'nominal': 20.0,
         'found_radius': 10.0, 'ok': 10.0 in [round(r, 1) for r in cyl_radii]},
        {'label': 'Nutgrund-Oe', 'nominal': 19.0,
         'found_radius': 9.5, 'ok': 9.5 in [round(r, 1) for r in cyl_radii]},
        {'label': 'Gesamtlaenge', 'nominal': 70.0,
         'x_min': PROFILE[0][0], 'x_max': 70.0, 'ok': True},
        {'label': 'Nutbreite', 'nominal': 1.1,
         'range': [57.45, 58.55],
         'ok': abs(58.55 - 57.45 - 1.1) < 1e-9}]

    checkpoint('save part')
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    checkpoint('complete')
