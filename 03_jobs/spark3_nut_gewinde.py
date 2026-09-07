"""SPARK3 Schritt 2d: ECHTER Schnitt am Schritt-1-Teil (Nut 6 Form A + M6).

params: {"base_prt": <VM-Pfad Schritt-1-Teil>} -- per FullPath-Match
wiederverwendet (Probe 2b-Muster, verifiziert), kein CloseAll.
Vermessene Abbildung (Run 20260906T153137Z-8c04fc81, Scratch):
  Block: Length->X, Width->Y, Height->Z.
  Nut oben: Length 14 (x 50..64), Width 4.5 (y 6.5..11), Height 6 (z -3..+3),
  Corner (50, 6.5, -3), Subtract via Feature.BooleanType.
Runde Enden: 2x GeneralHole Oe6 Tiefe 3.5, Punkte AUF der Mantelflaeche
  (50/64, 10, 0), Projektion Default (FaceNormal), Tolerance 0.01 -- im
  selben Run auf Scratch verifiziert (r=3, Achse Y, x=50/64).
M6 stirnseitig (Rezept S3 + hole_probe): ThreadedHole, Metric Coarse,
  'M6 x 1.0', RadialEngage 0.75, Punkt (70,0,0) auf der Stirnflaeche,
  ThreadDepth 12, ThreadedHoleDepth 14, Tip 118, Startfase Oe6.4/30 Grad
  (von der Flaeche), Subtract, Tolerance 0.01.
Offen/下方 dokumentiert: koaxiale Zentrierbohrung DIN 332-A/R zum Gewinde
  ist nach Schicht-3-Regel unzulaessig (braucht Form D) -- nur Gewinde,
  kein Zentrum. Entscheidung beim naechsten Schritt.
Jeder Schritt: eigene Undo-Marke, Repaint, 1.5 s Takt, Checkpoint.
result.json (UTF-8) mit Soll/Ist -- falsche Assoziation = failed Run.
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.UF


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'checks': []}
    try:
        run(out, result)
        result['ok'] = all(c.get('ok', False) for c in result['checks'])
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def check(result, label, nominal, found, tol, extra=None):
    entry = {'label': label, 'nominal': nominal, 'found': found,
             'ok': (found is not None) and abs(found - nominal) <= tol}
    if extra is not None:
        entry['extra'] = extra
    result['checks'].append(entry)
    return entry['ok']


def run(out, result, watchable=True):
    session = NXOpen.Session.GetSession()
    uf = NXOpen.UF.UFSession.GetUFSession()
    params = json.loads((out / 'parameters.json').read_text())
    want = params.get('base_prt', '')
    norm = want.replace('\\', '/').lower()

    result['stage'] = 'find base part'
    part = None
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        if isinstance(full, str) and full.replace('\\', '/').lower() == norm:
            part = p
            break
    assert part is not None, {'base not open': want}
    result['part'] = safe(lambda: part.JournalIdentifier)

    result['stage'] = 'display base part'
    disp = safe(lambda: session.Parts.SetDisplayPart(part))
    result['set_display'] = disp if isinstance(disp, str) else 'ok'
    view = None
    try:
        view = part.ModelingViews.WorkView
        result['workview'] = 'ok'
    except Exception as error:
        result['workview'] = 'WARN: ' + str(error)[:200]

    def repaint():
        if view is None:
            return
        try:
            view.Orient(NXOpen.View.Canned.Trimetric,
                        NXOpen.View.ScaleAdjustment.Fit)
            view.UpdateDisplay()
        except Exception as error:
            result['repaint'] = 'WARN: ' + str(error)[:200]

    body = list(part.Bodies)[0]

    # --- Basis pruefen (falsches Teil => lauter Fail, kein falscher Schnitt)
    radii = []
    for face in body.GetFaces():
        try:
            data = uf.Modeling.AskFaceData(face.Tag)
        except Exception:
            continue
        if data[0] == 16:
            radii.append(round(float(data[4]), 4))
    result['base_radii'] = sorted(radii)
    for expected in (12.5, 10.0, 9.5):
        assert any(abs(r - expected) < 0.01 for r in radii), \
            {'wrong base part, missing radius': expected, 'radii': radii}

    def snapshot():
        planes, cyls = [], []
        for face in body.GetFaces():
            try:
                kind, point, direction, box, radius, rad, normv = \
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
        return planes, cyls

    # --- Nut-Mitte ---
    result['stage'] = 'keyway block'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Passfedernut')
    block = part.Features.CreateBlockFeatureBuilder(None)
    try:
        block.Type = getattr(
            NXOpen.Features, 'BlockFeatureBuilderTypes').OriginAndEdgeLengths
        block.SetLength('14')
        block.SetWidth('4.5')
        block.SetHeight('6')
        block.Origin = NXOpen.Point3d(50.0, 6.5, -3.0)
        block.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Subtract, body)
        block_feature = block.CommitFeature()
        result['block'] = block_feature.JournalIdentifier
    finally:
        try:
            block.Destroy()
        except Exception:
            pass
    repaint()
    if watchable:
        time.sleep(1.5)

    # --- Runde Enden ---
    result['stage'] = 'keyway ends'
    result['hole_features'] = []
    for i, xc in enumerate((50.0, 64.0)):
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                            'SPARK3 Nut-Radius %d' % (i + 1))
        hole = part.Features.CreateHolePackageBuilder(None)
        try:
            hole.Type = getattr(
                NXOpen.Features, 'HolePackageBuilderTypes').GeneralHole
            hole.GeneralSimpleHoleDiameter.RightHandSide = '6'
            hole.GeneralSimpleHoleDepth.RightHandSide = '3.5'
            pt = part.Points.CreatePoint(NXOpen.Point3d(xc, 10.0, 0.0))
            hole.HolePosition.AddSmartPoint(pt, 0.01)
            hole.BooleanOperation.Type = NXOpen.GeometricUtilities \
                .BooleanOperation.BooleanType.Subtract
            hole.BooleanOperation.SetTargetBodies([body])
            hole.Tolerance = 0.01
            feat = hole.CommitFeature()
            result['hole_features'].append(feat.JournalIdentifier)
        finally:
            try:
                hole.Destroy()
            except Exception:
                pass
        repaint()
        if watchable:
            time.sleep(1.5)

    # --- M6 stirnseitig ---
    result['stage'] = 'thread M6'
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'SPARK3 M6')
    thread = part.Features.CreateHolePackageBuilder(None)
    try:
        thread.Type = getattr(
            NXOpen.Features, 'HolePackageBuilderTypes').ThreadedHole
        thread.ThreadStandard = 'Metric Coarse'
        thread.ThreadSize = 'M6 x 1.0'
        thread.RadialEngageOption = '0.75'
        pt = part.Points.CreatePoint(NXOpen.Point3d(70.0, 0.0, 0.0))
        thread.HolePosition.AddSmartPoint(pt, 0.01)
        thread.ProjectionDirection.DirectionType = NXOpen.GeometricUtilities \
            .ProjectionOptionsDirectionType.FaceNormal
        thread.ThreadLengthOption = getattr(
            NXOpen.Features,
            'HolePackageBuilderThreadLengthOptions').Custom
        thread.ThreadDepth.RightHandSide = '12'
        thread.HoleDepthLimitOption = getattr(
            NXOpen.Features,
            'HolePackageBuilderHoleDepthLimitOptions').Value
        thread.ThreadedHoleDepth.RightHandSide = '14'
        thread.ThreadedTipAngle.RightHandSide = '118'
        thread.ThreadedStartChamferEnabled = True
        thread.ThreadedStartChamferDiameter.RightHandSide = '6.4'
        thread.ThreadedStartChamferAngle.RightHandSide = '30'
        thread.BooleanOperation.Type = NXOpen.GeometricUtilities \
            .BooleanOperation.BooleanType.Subtract
        thread.BooleanOperation.SetTargetBodies([body])
        thread.Tolerance = 0.01
        thread_feature = thread.CommitFeature()
        result['thread'] = thread_feature.JournalIdentifier
    finally:
        try:
            thread.Destroy()
        except Exception:
            pass
    repaint()
    if watchable:
        time.sleep(1.5)

    # --- Selbstpruefung Soll/Ist ---
    result['stage'] = 'verify'
    planes, cyls = snapshot()
    floor = [f for f in planes if abs(f['n'][1] - 1.0) < 1e-6
             and abs(f['p'][1] - 6.5) < 0.02
             and 50.0 - 0.05 <= f['p'][0] <= 64.0 + 0.05]
    check(result, 'Nutboden y', 6.5,
          (floor[0]['p'][1] if floor else None), 0.02,
          {'faces': len(floor)})
    flank_m = [f for f in planes if abs(f['n'][2] - 1.0) < 1e-6
               and abs(f['p'][2] + 3.0) < 0.02]
    check(result, 'Nutflanke z=-3', -3.0,
          (flank_m[0]['p'][2] if flank_m else None), 0.02,
          {'faces': len(flank_m)})
    flank_p = [f for f in planes if abs(f['n'][2] + 1.0) < 1e-6
               and abs(f['p'][2] - 3.0) < 0.02]
    check(result, 'Nutflanke z=+3', 3.0,
          (flank_p[0]['p'][2] if flank_p else None), 0.02,
          {'faces': len(flank_p)})
    ends = sorted(f['p'][0] for f in planes
                  if abs(abs(f['n'][0]) - 1.0) < 1e-6
                  and abs(f['p'][0] - 50.0) < 0.05 or
                  abs(abs(f['n'][0]) - 1.0) < 1e-6
                  and abs(f['p'][0] - 64.0) < 0.05)
    check(result, 'Nutenden x=50/64', 1.0,
          (1.0 if (any(abs(x - 50.0) < 0.05 for x in ends)
                   and any(abs(x - 64.0) < 0.05 for x in ends)) else 0.0),
          0.0, {'found_x': ends})
    r3 = [c for c in cyls if abs(c['r'] - 3.0) < 0.02
          and abs(abs(c['d'][1]) - 1.0) < 1e-6]
    r3x = sorted(c['p'][0] for c in r3)
    check(result, 'Rundungen Oe6 x=50/64', 1.0,
          (1.0 if (any(abs(x - 50.0) < 0.1 for x in r3x)
                   and any(abs(x - 64.0) < 0.1 for x in r3x)) else 0.0),
          0.0, {'found_x': r3x})
    tap = [c for c in cyls if abs(c['r'] - 2.5) < 0.15
           and abs(abs(c['d'][0]) - 1.0) < 1e-6 and c['p'][0] > 55.0]
    check(result, 'M6-Kernloch r~2.5 bei x>55', 2.5,
          (tap[0]['r'] if tap else None), 0.15,
          {'found': tap[:3]})
    result['cyl_summary'] = {'n': len(cyls), 'planes': len(planes)}

    result['stage'] = 'save'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['open_points'] = [
        'Zentrierbohrung DIN 332-A/R koaxial zu M6 nach Schicht-3-Regel '
        'unzulaessig (braucht Form D) -- nur Gewinde umgesetzt.',
        'Zeichnung + PDF + STEP-AP214 folgen als naechster Schritt.']
    result['stage'] = 'complete'
