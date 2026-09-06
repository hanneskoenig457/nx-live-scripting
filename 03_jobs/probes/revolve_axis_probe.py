"""Welche Rotationsachse überlebt das Wiederöffnen des Revolve-Builders?

Vorlauf: alle vier Profilvarianten (offen/geschlossen, an der Achse/abgerückt)
scheitern beim Wiederöffnen gleichermaßen mit "Tolerance error", das Extrude der
Passfedernut dagegen nicht. Der einzige Unterschied zwischen beiden Features ist
die Achse. Dieser Job baut dieselbe Rotation mit vier Achskonstruktionen und
versucht bei jeder den Doppelklick.

  A  Point + Direction + Axis, alle UpdateOption.WithinModeling   (heutiger Stand)
  B  die Point3d/Vector3d-Überladung von CreateAxis
  C  Achse aus einem Datum-Axis-Feature (PointAndDir)
  D  Achse aus dem Datum-Axis-Feature der XC-Achse
  E  dieselben Objekte mit UpdateOption.AfterParentBody
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

PROFILE = [(0.0, 0.0), (0.0, 11.5), (1.0, 12.5), (30.0, 12.5),
           (30.0, 10.0), (69.0, 10.0), (70.0, 9.0), (70.0, 0.0)]
WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling
DONT = NXOpen.SmartObject.UpdateOption.DontUpdate


def safe(fn, limit=600):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def axis_within(part, entry):
    origin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN)
    return part.Axes.CreateAxis(origin, direction, WITHIN)


def axis_raw(part, entry):
    # Die Überladung, die die NXOpen-Referenz als feature-intern kennzeichnet.
    return part.Axes.CreateAxis(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN)


def datum_axis(part, entry, kind):
    builder = part.Features.CreateDatumAxisBuilder(None)
    try:
        if kind == 'point':
            builder.Type = NXOpen.Features.DatumAxisBuilder.Types.PointAndDir
            builder.SetPointAndDirection(
                part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)),
                part.Directions.CreateDirection(
                    NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN))
        else:
            builder.Type = NXOpen.Features.DatumAxisBuilder.Types.XcAxis
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    entry['datum_axis_feature'] = feature.JournalIdentifier
    datum = None
    for candidate in feature.GetEntities():
        if isinstance(candidate, NXOpen.DatumAxis):
            datum = candidate
            break
    entry['datum_axis_found'] = datum is not None
    direction = part.Directions.CreateDirection(datum, NXOpen.Sense.Forward, WITHIN)
    return part.Axes.CreateAxis(
        part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)), direction, WITHIN)


def axis_after_parent(part, entry):
    option = NXOpen.SmartObject.UpdateOption.AfterParentBody
    origin = part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), option)
    return part.Axes.CreateAxis(origin, direction, option)


VARIANTS = (('A_within', axis_within),
            ('B_raw_overload', axis_raw),
            ('C_datum_pointdir', lambda p, e: datum_axis(p, e, 'point')),
            ('D_datum_xc', lambda p, e: datum_axis(p, e, 'xc')),
            ('E_after_parent', axis_after_parent))


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
    scratch = out / 'revolve_axis.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    for label, factory in VARIANTS:
        entry = {'variant': label}
        try:
            entry.update(build(session, part, factory, entry))
        except Exception:
            entry['build_error'] = traceback.format_exc()[-1000:]
        result['variants'].append(entry)

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


def build(session, part, axis_factory, entry):
    points = [NXOpen.Point3d(x, 0.0, r) for x, r in PROFILE]
    curves = [part.Curves.CreateLine(points[i], points[i + 1])
              for i in range(len(points) - 1)]
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        section = part.Sections.CreateSection()
        section.AddToSection(
            [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None, None,
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        builder.Section = section
        builder.Axis = axis_factory(part, entry)
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

    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'weg')
    session.UpdateManager.AddToDeleteList([feature])
    entry['deleted'] = safe(lambda: str(session.UpdateManager.DoUpdate(mark)))
    return entry


if __name__ == '__main__':
    main()
