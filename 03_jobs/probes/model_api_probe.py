"""Probe: the modelling APIs for a sketch- and feature-driven specimen.

The current specimen is built from loose wireframe curves. Those curves stay in
the part and are drawn into the drafting views, which is one of the defects in
the first drawing. This probe reports what this NX build offers instead:
sketches, chamfer, groove, slot and — the open question from the first run —
a hole feature that carries real thread data.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities


def members(obj):
    return sorted(name for name in dir(obj) if not name.startswith('_'))


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def describe(obj):
    out = {'type': safe(lambda: type(obj).__name__), 'members': safe(lambda: members(obj))}
    nested = {}
    for name in out['members'] if isinstance(out['members'], list) else []:
        value = safe(lambda o=obj, n=name: getattr(o, n))
        if isinstance(value, type):
            nested[name] = safe(lambda v=value: members(v))
    if nested:
        out['nested'] = nested
    return out


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    scratch = out / 'model_api_probe.prt'
    if scratch.exists():
        scratch.unlink()
    part = session.Parts.NewDisplay(str(scratch), NXOpen.Part.Units.Millimeters)

    api = {}
    feature_members = members(part.Features)
    api['feature_creators'] = [n for n in feature_members
                               if any(k in n for k in ('Thread', 'Hole', 'Chamfer', 'Groove',
                                                       'Slot', 'Sketch', 'Datum', 'Revolve',
                                                       'Extrude', 'Cylinder'))]
    api['sketch_collection'] = describe(part.Sketches)

    def builder_probe(label, factory, children=()):
        obj = None
        try:
            obj = factory()
            api[label] = describe(obj)
            for name in children:
                child = safe(lambda o=obj, n=name: getattr(o, n))
                if not isinstance(child, str):
                    api[label].setdefault('children', {})[name] = describe(child)
        except Exception as error:
            api[label] = {'error': str(error)[:600]}
        finally:
            if obj is not None:
                safe(lambda o=obj: o.Destroy())

    builder_probe('hole_package', lambda: part.Features.CreateHolePackageBuilder(None),
                  children=('ThreadDimension', 'Diameter', 'Depth', 'HoleDiameter'))
    builder_probe('symbolic_thread', lambda: part.Features.CreateSymbolicThreadBuilder(None))
    builder_probe('thread', lambda: part.Features.CreateThreadBuilder(None))
    builder_probe('chamfer', lambda: part.Features.CreateChamferBuilder(None))
    builder_probe('groove', lambda: part.Features.CreateGrooveBuilder(None))
    builder_probe('slot', lambda: part.Features.CreateSlotBuilder(None))
    builder_probe('sketch_in_place', lambda: part.Sketches.CreateSketchInPlaceBuilder2(None))
    builder_probe('datum_plane', lambda: part.Features.CreateDatumPlaneBuilder(None))

    # Thread data availability is the open question from the first specimen run.
    try:
        cylinder = part.Features.CreateCylinderBuilder(None)
        cylinder.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
        cylinder.Origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        cylinder.Direction = NXOpen.Vector3d(1.0, 0.0, 0.0)
        cylinder.Diameter.RightHandSide = '20'
        cylinder.Height.RightHandSide = '30'
        feature = cylinder.CommitFeature()
        cylinder.Destroy()
        body = feature.GetBodies()[0]
        result['probe_body'] = body.JournalIdentifier

        hole = part.Features.CreateHolePackageBuilder(None)
        try:
            api['hole_package_live'] = describe(hole)
            for name in ('Type', 'HoleDiameter', 'StandardThread', 'ThreadSize',
                         'ThreadStandard', 'ThreadDimension', 'ThreadedHoleThreadDimension'):
                value = safe(lambda h=hole, n=name: getattr(h, n))
                api.setdefault('hole_package_values', {})[name] = (
                    describe(value) if not isinstance(value, (str, int, float, bool, type(None)))
                    else str(value))
        finally:
            hole.Destroy()
    except Exception:
        result['hole_probe_error'] = traceback.format_exc()[-1500:]

    result['api'] = api
    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch.exists():
        safe(lambda: scratch.unlink())


if __name__ == '__main__':
    main()
