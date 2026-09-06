"""Warum meldet eine Rotation beim Wiederöffnen "Tolerance error"?

Der Prüfkörper hat zwei Rotationen; beide scheitern beim Wiederöffnen des
Builders, das Extrude der Passfedernut nicht. Dieser Job baut dieselbe Kontur in
vier Varianten auf und versucht bei jeder den Doppelklick, damit die Ursache
belegt statt vermutet wird:

  A  offenes Profil, Endpunkte auf der Achse, lose Kurven      (heutiger Stand)
  B  offenes Profil, Endpunkte auf der Achse, in einer Skizze
  C  geschlossenes Profil mit Segment auf der Achse, lose Kurven
  D  geschlossenes Profil mit Segment auf der Achse, in einer Skizze
  E  offenes Profil um 0,5 von der Achse abgerückt, lose Kurven
  F  geschlossenes Profil um 0,5 abgerückt, lose Kurven

Jede Variante wird gebaut, wieder geöffnet und dann gelöscht. Der Bau gelingt in
allen Fällen — die Frage ist allein, welche sich wieder öffnen lässt.

Legt ein Wegwerfteil an und löscht es wieder.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

OPEN_PROFILE = [(0.0, 0.0), (0.0, 11.5), (1.0, 12.5), (30.0, 12.5),
                (30.0, 10.0), (69.0, 10.0), (70.0, 9.0), (70.0, 0.0)]
CLOSED_PROFILE = OPEN_PROFILE + [(0.0, 0.0)]

VIEW_REORIENT_FALSE = NXOpen.Sketch.ViewReorient.FalseValue


def safe(fn, limit=600):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def matrix_xz():
    matrix = NXOpen.Matrix3x3()
    matrix.Xx, matrix.Xy, matrix.Xz = 1.0, 0.0, 0.0
    matrix.Yx, matrix.Yy, matrix.Yz = 0.0, 0.0, 1.0
    matrix.Zx, matrix.Zy, matrix.Zz = 0.0, -1.0, 0.0
    return matrix


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False, 'variants': []}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    scratch = out / 'revolve_variants.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    for label, profile, use_sketch, offset in (('A_open_dumb', OPEN_PROFILE, False, 0.0),
                                               ('C_closed_dumb', CLOSED_PROFILE, False, 0.0),
                                               ('E_open_offaxis', OPEN_PROFILE, False, 0.5),
                                               ('F_closed_offaxis', CLOSED_PROFILE, False, 0.5)):
        entry = {'variant': label}
        try:
            entry.update(build_variant(part, profile, use_sketch, offset))
        except Exception:
            entry['build_error'] = traceback.format_exc()[-1200:]
        result['variants'].append(entry)

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


def build_variant(part, profile, use_sketch, offset):
    entry = {}
    points = [NXOpen.Point3d(x, 0.0, r + offset) for x, r in profile]
    curves = [part.Curves.CreateLine(points[i], points[i + 1])
              for i in range(len(points) - 1)
              if points[i].X != points[i + 1].X or points[i].Z != points[i + 1].Z]
    entry['curves'] = len(curves)

    if use_sketch:
        plane = part.Planes.CreateFixedTypePlane(
            NXOpen.Point3d(0.0, 0.0, 0.0), matrix_xz(),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
        try:
            builder.PlaneOption = NXOpen.Sketch.PlaneOption.ExistingPlane
            entry['plane_or_face'] = safe(lambda b=builder: str(
                sorted(n for n in dir(b.PlaneOrFace) if not n.startswith('_'))))
            entry['set_plane_or_face'] = safe(lambda b=builder, p=plane: str(
                setattr(b.PlaneOrFace, 'Value', p)))
            builder.PlaneReference = plane
            builder.SketchOrigin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
            sketch = builder.Commit()
        finally:
            builder.Destroy()
        entry['sketch_plane'] = safe(lambda s=sketch: str(s.GetPlane().Tag))
        sketch.Activate(VIEW_REORIENT_FALSE)
        for curve in curves:
            sketch.AddGeometry(curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
        entry['fully_fixed'] = safe(lambda: str(sketch.CreateFullyFixedConstraints(False)))
        sketch.Update()
        sketch.Deactivate(VIEW_REORIENT_FALSE, NXOpen.Sketch.UpdateLevel.Model)
        entry['sketch'] = sketch.Name

    builder = part.Features.CreateRevolveBuilder(None)
    try:
        section = part.Sections.CreateSection()
        section.AddToSection(
            [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None, None,
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        builder.Section = section
        origin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
        direction = part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Axis = part.Axes.CreateAxis(
            origin, direction, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Limits.StartExtend.Value.RightHandSide = '0'
        builder.Limits.EndExtend.Value.RightHandSide = '360'
        builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        entry['validate'] = safe(lambda b=builder: str(b.Validate()))
        feature = builder.CommitFeature()
        entry['feature'] = feature.JournalIdentifier
    finally:
        builder.Destroy()

    reopened = None
    try:
        reopened = part.Features.CreateRevolveBuilder(feature)
        entry['reedit'] = 'ok'
    except Exception as error:
        entry['reedit'] = 'ERROR: ' + str(error)[:300]
    finally:
        if reopened is not None:
            safe(lambda b=reopened: b.Destroy())

    session = NXOpen.Session.GetSession()
    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'weg')
    entry['deleted'] = safe(lambda: str(cleanup(session, feature, mark)))
    return entry


def cleanup(session, feature, mark):
    session.UpdateManager.AddToDeleteList([feature])
    return session.UpdateManager.DoUpdate(mark)


if __name__ == '__main__':
    main()
