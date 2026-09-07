"""SPARK3 Schritt 2c: Loch-Richtungs-Sweep + Z-Flanken-Check auf Scratch.

params: {"scratch_prt": <VM-Pfad des Scratch-Teils aus 2b>} (offen in Session,
wird per FullPath-Match wiederverwendet, kein OpenDisplay-Neuversuch).
1. Z-normale Planflaechen mit Extents (Kanten-Vertices min/max) -- klaert die
   +Z-Probe (Mitte z=1.5 statt 3.0) per Messung, nicht per Vermutung.
2. Dump aller *rojection*-Enums in NXOpen.GeometricUtilities (DirectionType,
   ProjectDirectionMethod) -- legt den Along-Vector-Pfad fuer spaeter fest.
3. Sweep V1/V2: GeneralHole Oe6 Tiefe 3.5 an den ECHTEN Endzentren x=50/64,
   Punkte auf der Mantelflaeche (y=10), Projektion Default, Tolerance 0.01,
   je eigene Undo-Marke. Erfolg => Nut auf Scratch vollstaendig + vermessen.
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


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start'}
    try:
        run(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    params = json.loads((out / 'parameters.json').read_text())
    want = params.get('scratch_prt', '')
    norm = want.replace('\\', '/').lower()
    part, cands = None, []
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        cands.append(full)
        if isinstance(full, str) and full.replace('\\', '/').lower() == norm:
            part = p
    assert part is not None, {'scratch not open': want, 'open': cands}
    result['scratch'] = safe(lambda: part.JournalIdentifier)
    body = list(part.Bodies)[0]
    view = part.ModelingViews.WorkView

    def snapshot(label):
        planes, zfaces, cyls = [], [], []
        for face in body.GetFaces():
            try:
                kind, point, direction, box, radius, rad, normv = \
                    uf.Modeling.AskFaceData(face.Tag)
            except Exception:
                continue
            if kind == 22:
                entry = {'p': [round(v, 3) for v in point],
                         'n': [round(v, 3) for v in direction]}
                planes.append(entry)
                if abs(abs(direction[2]) - 1.0) < 1e-6:
                    ext = {'xs': [], 'ys': [], 'zs': []}
                    try:
                        for edge in face.GetEdges():
                            try:
                                for v in edge.GetVertices():
                                    ext['xs'].append(round(v.X, 3))
                                    ext['ys'].append(round(v.Y, 3))
                                    ext['zs'].append(round(v.Z, 3))
                            except Exception:
                                continue
                    except Exception:
                        pass
                    entry['extent'] = {
                        k: ([min(v), max(v)] if v else 'n/a')
                        for k, v in ext.items()}
                    zfaces.append(entry)
            elif kind == 16:
                cyls.append({'p': [round(v, 3) for v in point],
                             'd': [round(v, 3) for v in direction],
                             'r': round(float(radius), 3)})
        return {'label': label, 'planes': len(planes), 'zfaces': zfaces,
                'cyls': len(cyls), 'cyl_list': cyls}

    result['stage'] = 'z-face check'
    result['before'] = snapshot('vor Loechern')
    result['hole_count_r3'] = len(
        [c for c in result['before']['cyl_list'] if abs(c['r'] - 3.0) < 0.01])

    result['stage'] = 'projection enums'
    proj_dump = {}
    for name in members(NXOpen.GeometricUtilities):
        if 'roject' in name.lower():
            try:
                obj = getattr(NXOpen.GeometricUtilities, name)
            except Exception:
                continue
            proj_dump[name] = members(obj) if isinstance(obj, type) else str(
                obj)[:200]
    result['projection_enums'] = proj_dump

    result['stage'] = 'hole sweep'
    result['holes'] = []
    for i, xc in enumerate((50.0, 64.0)):
        entry = {'x': xc}
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 Nut-Ende %d V2' % (i + 1))
        hole = part.Features.CreateHolePackageBuilder(None)
        try:
            hole.Type = getattr(
                NXOpen.Features, 'HolePackageBuilderTypes').GeneralHole
            hole.GeneralSimpleHoleDiameter.RightHandSide = '6'
            hole.GeneralSimpleHoleDepth.RightHandSide = '3.5'
            pt = part.Points.CreatePoint(NXOpen.Point3d(xc, 10.0, 0.0))
            entry['smartpoint'] = safe(
                lambda: str(hole.HolePosition.AddSmartPoint(pt, 0.01)))
            hole.BooleanOperation.Type = NXOpen.GeometricUtilities \
                .BooleanOperation.BooleanType.Subtract
            hole.BooleanOperation.SetTargetBodies([body])
            hole.Tolerance = 0.01
            feat = hole.CommitFeature()
            entry['feature'] = feat.JournalIdentifier
            entry['committed'] = True
        except Exception as error:
            entry['committed'] = False
            entry['error'] = str(error)[:400]
        finally:
            try:
                hole.Destroy()
            except Exception:
                pass
        result['holes'].append(entry)
        view.UpdateDisplay()

    result['stage'] = 'measure'
    result['after'] = snapshot('nach Loechern')
    r3 = [c for c in result['after']['cyl_list'] if abs(c['r'] - 3.0) < 0.02]
    result['r3_cyls'] = r3
    floors = [f for f in result['after']['zfaces']
              if abs(f['n'][2]) > 0.99] if False else None
    view.UpdateDisplay()
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
