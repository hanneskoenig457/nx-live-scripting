"""SPARK3 Diagnose 2: Blatt-Rahmen + View-Ausdehnung (read-only, keine Commits).

Offen aus dem User-Screenshot: Inhalt scheint links an einer gestrichelten
Linie abgeschnitten. BordersAndZones ist None (Run 20260907T062735Z...Diag).
Neue Hypothesen, hier entschieden:
(a) Die Linie sind echte Kurven: sheet.GetDraftingSketches() -> Rahmen?
    -> Name, Kurvenzahl, Strichtyp, Bounding Box je Skizze.
(b) Views laufen aus dem Blatt: CalculateMinMaxBox mit ECHTEN Koordinaten
    (nicht str()) + Origin + Scale je Ansicht.
(c) Scale-Raetsel: Views melden 3.16 statt 2.0 -> GetExpandedScale dazu.
Kein Commit, kein Save. Alles in result.json (UTF-8).
"""
import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Drawings

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260906T153508Z-a28c46ac/20260906T153508Z-a28c46ac.prt')


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=500):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def pt(p):
    try:
        return [round(float(p.X), 3), round(float(p.Y), 3),
                round(float(p.Z), 3)]
    except Exception:
        return 'ERR'


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
    want = None
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        if isinstance(full, str) and full.replace('\\', '/').lower() == \
                BASE_PRT.lower():
            want = p
            break
    assert want is not None, {'verified part not open': BASE_PRT}
    part = want
    sheet = list(part.DrawingSheets)[0]
    result['sheet'] = {'name': safe(lambda: sheet.Name),
                       'len': safe(lambda: float(sheet.Length)),
                       'h': safe(lambda: float(sheet.Height))}
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Diagnose 2 lesend')
    sheet.Open()

    result['stage'] = 'sketches'
    sks = []
    try:
        sketches = list(sheet.GetDraftingSketches())
    except Exception as error:
        sketches = []
        sks.append({'error': str(error)[:200]})
    for sk in sketches:
        entry = {'name': safe(lambda s=sk: s.Name)}
        try:
            geos = list(sk.GetAllGeometry())
        except Exception:
            geos = []
        entry['n_curves'] = len(geos)
        xs, ys = [], []
        fonts = set()
        for c in geos:
            try:
                leverage = c.GetVertices()
            except Exception:
                leverage = []
            for v in leverage:
                try:
                    xs.append(round(float(v.X), 2))
                    ys.append(round(float(v.Y), 2))
                except Exception:
                    continue
            fonts.add(safe(lambda cc=c: str(cc.LineFont)))
        entry['bbox'] = {'x': [min(xs), max(xs)] if xs else None,
                         'y': [min(ys), max(ys)] if ys else None}
        entry['fonts'] = sorted(fonts)[:6]
        sks.append(entry)
    result['drafting_sketches'] = sks

    result['stage'] = 'views'
    vreps = []
    for vw in sheet.SheetDraftingViews:
        try:
            mm = vw.CalculateMinMaxBox()
            box = [pt(mm[0]), pt(mm[1])]
        except Exception as error:
            box = 'ERR: ' + str(error)[:200]
        vreps.append({
            'name': safe(lambda v=vw: v.Name),
            'origin': safe(lambda v=vw: pt(v.Origin)),
            'scale': safe(lambda v=vw: float(v.Scale)),
            'expanded': safe(lambda v=vw: str(v.GetExpandedScale())),
            'minmax': box,
            'out_of_date': safe(lambda v=vw: bool(v.IsOutOfDate)),
            'n_visible': safe(lambda v=vw: len(v.AskVisibleObjects()))})
    result['views'] = vreps
    result['stage'] = 'complete'
