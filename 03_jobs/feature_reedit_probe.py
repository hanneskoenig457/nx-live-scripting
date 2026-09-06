"""Can every feature of this part still be opened for editing?

A double-click in the part navigator re-creates the feature's builder. Features
built from a job can commit cleanly and still refuse that — most often because a
builder property was left at an invalid default (see
`skills/nx-live-scripting/references/verified-recipes.md`, section 0). The solid
and the drawing look fine, so nothing else catches it.

This job does the double-click for every feature and reports which ones fail,
with NX' own message. Run it on a part before handing it on.

    echo '{"part": "C:/…/pruefkoerper.prt"}' > /tmp/p.json
    .venv/bin/python 01_host/nx_remote.py feature_reedit_probe.py --parameters /tmp/p.json

Opens the part, changes nothing, saves nothing.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features

# Which builder re-creates which feature, keyed on FeatureType. The journal
# identifier is not a reliable key: the children of a hole package inherit the
# parent's name ("THREADED HOLE(7:1A)") while being a different feature type.
BUILDERS = {
    'SWP104': 'CreateRevolveBuilder',        # what NX calls a Revolve internally
    'REVOLVED': 'CreateRevolveBuilder',
    'EXTRUDE': 'CreateExtrudeBuilder',
    'CHAMFER': 'CreateChamferBuilder',
    'HOLE PACKAGE': 'CreateHolePackageBuilder',
    'CYLINDER': 'CreateCylinderBuilder',
    'DATUM_PLANE': 'CreateDatumPlaneBuilder',
    'ABSOLUTE_DATUM_PLANE': 'CreateDatumPlaneBuilder',
    'DATUM_AXIS': 'CreateDatumAxisBuilder',
    'ABSOLUTE_DATUM_AXIS': 'CreateDatumAxisBuilder',
}


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def parameters(out):
    source = out / 'parameters.json'
    if source.exists():
        try:
            return json.loads(source.read_text(encoding='utf-8-sig'))
        except Exception:
            return {}
    return {}


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'features': []}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    given = parameters(out).get('part')
    if not given:
        raise RuntimeError('No part given; pass {"part": "<full path>"} via --parameters')
    part = session.Parts.OpenDisplay(str(given))[0]
    if part is None:
        raise RuntimeError('Part did not open; run part_open_probe.py for the reason')

    failures = 0
    for feature in part.Features:
        identifier = str(safe(lambda f=feature: f.JournalIdentifier))
        kind = str(safe(lambda f=feature: f.FeatureType))
        entry = {'feature': identifier, 'type': kind}
        # A colon marks a feature internal to another one — the drilled hole and
        # the thread inside a hole package, for instance. Those are not editable
        # on their own; the parent is.
        if ':' in identifier:
            entry['reedit'] = 'internal to parent feature'
            result['features'].append(entry)
            continue
        factory_name = BUILDERS.get(kind.upper())
        if factory_name is None:
            entry['reedit'] = 'no builder mapped'
            result['features'].append(entry)
            continue
        factory = getattr(part.Features, factory_name, None)
        if factory is None:
            entry['reedit'] = 'builder %s not in this NX build' % factory_name
            result['features'].append(entry)
            continue
        builder = None
        try:
            builder = factory(feature)
            entry['reedit'] = 'ok'
        except Exception as error:
            entry['reedit'] = 'ERROR: ' + str(error)[:300]
            failures += 1
        finally:
            if builder is not None:
                safe(lambda b=builder: b.Destroy())
        result['features'].append(entry)

    result['failures'] = failures
    safe(lambda: session.Parts.CloseAll(
        NXOpen.BasePart.CloseModified.CloseModified, None))


if __name__ == '__main__':
    main(Path(__file__).resolve().parent)
