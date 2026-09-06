"""Rotation aus einer Skizze auf einem Datum-CSYS — und NX' eigene Fehlermeldung.

Stand der Diagnose: jede Rotation, die aus losen Kurven und einer aus Point3d
zusammengesetzten Achse gebaut wird, lässt sich nicht wieder öffnen; das Extrude
der Passfedernut mit derselben Kurvenart dagegen schon. Achsvariante, Profilform
und Achsberührung sind als Ursache ausgeschlossen.

Dieser Job prüft die verbleibende Vermutung: Skizze statt loser Kurven und eine
echte Datum-Achse als Mittellinie. Zusätzlich wird nach dem Fehlversuch der
Schwanz des NX-Syslogs mitgeliefert, das die ausführliche Meldung enthält.
"""
import json
import os
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities

PROFILE = [(0.0, 0.0), (0.0, 11.5), (1.0, 12.5), (30.0, 12.5),
           (30.0, 10.0), (69.0, 10.0), (70.0, 9.0), (70.0, 0.0)]
WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling
REORIENT = NXOpen.Sketch.ViewReorient.FalseValue


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=600):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def syslog_tail(lines=60):
    try:
        temp = Path(os.environ.get('TEMP', r'C:\Windows\Temp'))
        logs = sorted(temp.glob('*.syslog'), key=lambda p: p.stat().st_mtime)
        if not logs:
            return 'no syslog found'
        text = logs[-1].read_text(encoding='utf-8', errors='replace').splitlines()
        return {'file': str(logs[-1]), 'tail': text[-lines:]}
    except Exception as error:
        return 'ERR: ' + str(error)[:300]


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
    scratch = out / 'revolve_sketch.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    # --- Datum-CSYS: liefert Ebenen und Achsen mit echten Eltern ---------------
    csys = {'step': 'datum csys'}
    planes, axes = [], []
    try:
        builder = part.Features.CreateDatumCsysBuilder(None)
        try:
            csys['members'] = members(builder)
            feature = builder.CommitFeature()
        finally:
            builder.Destroy()
        csys['feature'] = feature.JournalIdentifier
        for entity in feature.GetEntities():
            if isinstance(entity, NXOpen.DatumPlane):
                planes.append(entity)
            elif isinstance(entity, NXOpen.DatumAxis):
                axes.append(entity)
        csys['planes'] = len(planes)
        csys['axes'] = len(axes)
        csys['plane_normals'] = [str(safe(lambda p=p: str(p.Normal))) for p in planes]
        csys['axis_directions'] = [str(safe(lambda a=a: str(a.Direction))) for a in axes]
    except Exception:
        csys['error'] = traceback.format_exc()[-900:]
    result['datum_csys'] = csys

    xz_plane = None
    for plane in planes:
        normal = safe(lambda p=plane: p.Normal)
        if not isinstance(normal, str) and abs(abs(normal.Y) - 1.0) < 1e-6:
            xz_plane = plane
            break
    x_axis = None
    for axis in axes:
        direction = safe(lambda a=axis: a.Direction)
        if not isinstance(direction, str) and abs(abs(direction.X) - 1.0) < 1e-6:
            x_axis = axis
            break
    result['found'] = {'xz_plane': xz_plane is not None, 'x_axis': x_axis is not None}

    # --- Variante S: Skizze auf der Datum-Ebene, Achse aus der Datum-Achse -----
    entry = {'variant': 'S_sketch_on_datum'}
    try:
        sketch = None
        if xz_plane is not None:
            builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
            try:
                builder.PlaneOption = NXOpen.Sketch.PlaneOption.ExistingPlane
                builder.PlaneReference = xz_plane
                sketch = builder.Commit()
            finally:
                builder.Destroy()
            entry['sketch'] = sketch.Name
        points = [NXOpen.Point3d(x, 0.0, r) for x, r in PROFILE]
        curves = [part.Curves.CreateLine(points[i], points[i + 1])
                  for i in range(len(points) - 1)]
        if sketch is not None:
            sketch.Activate(REORIENT)
            added = 0
            for curve in curves:
                try:
                    sketch.AddGeometry(
                        curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
                    added += 1
                except Exception as error:
                    entry.setdefault('add_errors', []).append(str(error)[:200])
            entry['added'] = added
            sketch.Update()
            sketch.Deactivate(REORIENT, NXOpen.Sketch.UpdateLevel.Model)
        axis = None
        if x_axis is not None:
            direction = part.Directions.CreateDirection(x_axis, NXOpen.Sense.Forward, WITHIN)
            axis = part.Axes.CreateAxis(
                part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)), direction, WITHIN)
        entry.update(revolve(session, part, curves, axis))
    except Exception:
        entry['error'] = traceback.format_exc()[-1200:]
    result['variants'].append(entry)
    result['syslog'] = syslog_tail()

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


def revolve(session, part, curves, axis):
    entry = {}
    builder = part.Features.CreateRevolveBuilder(None)
    try:
        section = part.Sections.CreateSection()
        section.AddToSection(
            [part.ScRuleFactory.CreateRuleCurveDumb(curves)], curves[0], None, None,
            NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
        builder.Section = section
        builder.Axis = axis if axis is not None else part.Axes.CreateAxis(
            part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0)),
            part.Directions.CreateDirection(
                NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Vector3d(1.0, 0.0, 0.0), WITHIN),
            WITHIN)
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
    return entry


if __name__ == '__main__':
    main()
