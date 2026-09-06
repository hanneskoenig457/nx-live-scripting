"""Belegt die Ursache des "Tolerance error" und die Gegenmaßnahme.

Das NX-Syslog meldet beim Wiederöffnen wörtlich "+++ Invalid tolerance" aus
revolve_builder_definitions.c. RevolveBuilder hat eine Eigenschaft `Tolerance`;
wird sie beim Erzeugen nie gesetzt, speichert NX 0 am Feature und weist sie beim
Wiederöffnen zurück. Dieser Job baut dieselbe Rotation dreimal und versucht bei
jeder den Doppelklick:

  A  Tolerance nie angefasst                (heutiger Stand)
  B  Tolerance = 0,01
  C  Tolerance = Vorgabewert des Builders, zurückgelesen und wieder gesetzt
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


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


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
    scratch = out / 'revolve_tolerance.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    for label, tolerance in (('A_untouched', None), ('B_explicit', 0.01), ('C_default', 'default')):
        entry = {'variant': label}
        try:
            entry.update(build(session, part, tolerance))
        except Exception:
            entry['error'] = traceback.format_exc()[-900:]
        result['variants'].append(entry)

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


def build(session, part, tolerance):
    entry = {}
    points = [NXOpen.Point3d(x, 0.0, r) for x, r in PROFILE]
    curves = [part.Curves.CreateLine(points[i], points[i + 1]) for i in range(len(points) - 1)]
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        entry['tolerance_before'] = safe(lambda b=builder: b.Tolerance)
        section = part.Sections.CreateSection()
        section.AddToSection(
            [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None, None,
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        builder.Section = section
        builder.Axis = part.Axes.CreateAxis(
            part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)),
            part.Directions.CreateDirection(
                NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN),
            WITHIN)
        builder.Limits.StartExtend.Value.RightHandSide = '0'
        builder.Limits.EndExtend.Value.RightHandSide = '360'
        builder.BooleanOperation.Type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        if tolerance == 'default':
            builder.Tolerance = builder.Tolerance or 0.0254
        elif tolerance is not None:
            builder.Tolerance = tolerance
        entry['tolerance_set'] = safe(lambda b=builder: b.Tolerance)
        feature = builder.CommitFeature()
        entry['feature'] = feature.JournalIdentifier
    finally:
        builder.Destroy()

    reopened = None
    try:
        reopened = part.Features.CreateRevolveBuilder(feature)
        entry['reedit'] = 'ok'
        entry['tolerance_reread'] = safe(lambda b=reopened: b.Tolerance)
    except Exception as error:
        entry['reedit'] = 'ERROR: ' + str(error)[:200]
    finally:
        if reopened is not None:
            safe(lambda b=reopened: b.Destroy())

    mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'weg')
    session.UpdateManager.AddToDeleteList([feature])
    entry['deleted'] = safe(lambda: str(session.UpdateManager.DoUpdate(mark)))
    return entry


if __name__ == '__main__':
    main()
