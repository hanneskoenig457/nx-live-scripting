"""SPARK3 Schritt 2a: Probe Block/Hole/Layer-API am Schritt-1-Teil (read-only).

Oeffnet das Schritt-1-Teil ueber parameters.json {"base_prt": <VM-Pfad>},
committet NICHTS, dumpt stattdessen die Builder-Oberflaeche in result.json:
- BlockFeatureBuilder (Nut-Mitte): Typen, Origin/Length/Width/Height-Achsen
- HolePackageBuilder GeneralHole (runde Enden): Durchmesser/Tiefe, Position,
  Projektionsrichtung
- Layer-Enum-Frage (SetState schlug mit 'no attribute Layer' fehl)
- Basis-Teil: Ladezustand, Koerper, Zylinder-Radien zur Referenz
"""
import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=500):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def describe(obj, children=()):
    out = {'type': safe(lambda: type(obj).__name__),
           'members': safe(lambda: members(obj))}
    nested = {}
    for name in out['members'] if isinstance(out['members'], list) else []:
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if isinstance(value, type):
            nested[name] = safe(lambda v=value: members(v))
    if nested:
        out['nested_types'] = nested
    for name in children:
        try:
            child = getattr(obj, name)
        except Exception as error:
            out.setdefault('children', {})[name] = 'ERR: ' + str(error)[:200]
            continue
        if isinstance(child, (str, int, float, bool, type(None))):
            out.setdefault('children', {})[name] = str(child)
        elif isinstance(child, type):
            out.setdefault('children', {})[name] = {
                'type_obj': True, 'members': safe(lambda c=child: members(c))}
        else:
            out.setdefault('children', {})[name] = {
                'type': type(child).__name__,
                'members': safe(lambda c=child: members(c))}
    return out


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start'}
    try:
        params = json.loads((out / 'parameters.json').read_text())
        result['params'] = {'base_prt': params.get('base_prt')}
        probe(out, result, params)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result, params):
    session = NXOpen.Session.GetSession()
    base = params.get('base_prt')
    assert base, 'parameters.json braucht base_prt (VM-Pfad aus Schritt 1)'
    result['stage'] = 'open base part'
    try:
        opened = session.Parts.OpenDisplay(base)
        part, status = opened[0], opened[1]
        assert part is not None, 'OpenDisplay gab None zurueck'
        unloaded = []
        try:
            for i in range(status.NumberUnloadedParts):
                unloaded.append({'part': str(status.GetPartName(i)),
                                 'why': str(status.GetStatusDescription(i))})
        except Exception as error:
            unloaded = ['status unreadable: ' + str(error)[:200]]
        result['open'] = {'mode': 'opened',
                          'part': part.JournalIdentifier,
                          'unloaded': unloaded}
        assert not unloaded, unloaded
    except Exception as error:
        if 'already exists' not in str(error).lower():
            raise
        norm = base.replace('\\', '/').lower()
        found, candidates = None, []
        for p in session.Parts:
            full = safe(lambda q=p: str(q.FullPath))
            name = safe(lambda q=p: str(q.Name))
            candidates.append({'full': full, 'name': name})
            if isinstance(full, str) and full.replace('\\', '/').lower() == norm:
                found = p
        if found is None:
            # Fallback: nimm das angezeigte Teil, melde es ehrlich.
            try:
                found = session.Parts.DisplayPart
                mode = 'display_part_fallback'
            except Exception:
                found, mode = None, 'none'
        else:
            mode = 'reused_open'
        assert found is not None, {'why': 'already open, none matched',
                                   'candidates': candidates}
        part = found
        result['open'] = {'mode': mode, 'part': safe(
            lambda: part.JournalIdentifier), 'candidates': candidates}
    bodies = list(part.Bodies)
    result['body_count'] = len(bodies)
    body = bodies[0]
    uf = NXOpen.UF.UFSession.GetUFSession()
    radii = []
    for face in body.GetFaces():
        try:
            data = uf.Modeling.AskFaceData(face.Tag)
        except Exception:
            continue
        if data[0] == 16:
            radii.append(round(float(data[4]), 4))
    result['base_cyl_radii'] = sorted(radii)

    result['stage'] = 'describe block builder'
    block = part.Features.CreateBlockFeatureBuilder(None)
    try:
        result['block'] = describe(
            block, children=('Origin', 'BooleanOperation'))
        try:
            holder = getattr(NXOpen.Features, 'BlockFeatureBuilderTypes')
            result['block']['Types_values'] = members(holder)
        except Exception as error:
            result['block']['Types_values'] = 'ERR: ' + str(error)[:200]
        # Achsfragen: WELCHE Welt Richtung ist Length/Width/Height?
        # Keine Commits hier -- nur lesbare Defaults melden.
        for prop in ('Type',):
            result['block'].setdefault('values', {})[prop] = safe(
                lambda b=block, p=prop: str(getattr(b, p)))
    finally:
        try:
            block.Destroy()
        except Exception:
            pass

    result['stage'] = 'describe hole builder'
    hole = part.Features.CreateHolePackageBuilder(None)
    try:
        result['hole'] = describe(
            hole, children=('HolePosition', 'ProjectionDirection',
                            'BooleanOperation', 'ThreadDepth',
                            'ThreadedHoleDepth'))
        try:
            holder = getattr(NXOpen.Features, 'HolePackageBuilderTypes')
            result['hole']['Types_values'] = members(holder)
        except Exception as error:
            result['hole']['Types_values'] = 'ERR: ' + str(error)[:200]
        for prop in ('Type', 'Tolerance', 'GeneralSimpleHoleDiameter',
                     'GeneralSimpleHoleDepth'):
            result['hole'].setdefault('values', {})[prop] = safe(
                lambda h=hole, p=prop: str(getattr(h, p)))
    finally:
        try:
            hole.Destroy()
        except Exception:
            pass

    result['stage'] = 'layer enum'
    result['layers_members'] = safe(lambda: members(part.Layers))
    layer_probe(result)
    result['stage'] = 'complete'


def layer_probe(result):
    try:
        import NXOpen.Layer  # noqa: F401 -- unverifiziert, nur Probe
        result['layer_import'] = 'ok'
        result['layer_state_values'] = safe(
            lambda: members(NXOpen.Layer.State))
    except Exception as error:
        result['layer_import'] = 'ERR: ' + str(error)[:300]
    result['nxopen_has_layer'] = safe(lambda: hasattr(NXOpen, 'Layer'))
