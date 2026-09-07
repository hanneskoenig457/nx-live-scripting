"""SPARK3 Diagnose: Was ist die gestrichelte Linie? (read-only, keine Commits)

User-Screenshot: Blatt-Inhalt scheint links an einer gestrichelten Linie
abgeschnitten. Das PDF (Blatt-Wahrheit, 297x210) ist vollstaendig -- also
ist die Linie etwas anderes als die Blattkante. Dieser Job liest nur:
- Blatt Length/Height (als gebaut: 297x210?)
- BordersAndZones: Members + Elemente (Name, Typ) -- Kandidat Nr. 1
- je Drafting-Ansicht: Name, Origin, Scale, CalculateMinMaxBox, Objekte
- WorkView-Typ bei offenem Blatt
Kein Commit, kein Save, kein Undo-Mark-Verbrauch ausser einer sichtbaren
Klammer ums Oeffnen. Alles in result.json (UTF-8).
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
    result['stage'] = 'context'
    want = None
    for p in session.Parts:
        full = safe(lambda q=p: str(q.FullPath))
        if isinstance(full, str) and full.replace('\\', '/').lower() == \
                BASE_PRT.lower():
            want = p
            break
    assert want is not None, {'verified part not open': BASE_PRT}
    part = want

    result['stage'] = 'sheets'
    sheets = [{'name': safe(lambda s=s: s.Name),
               'len': safe(lambda s=s: float(s.Length)),
               'h': safe(lambda s=s: float(s.Height)),
               'unit': safe(lambda s=s: str(s.Unit)),
               'proj': safe(lambda s=s: str(s.ProjectionAngleType)),
               'stdsize': safe(lambda s=s: str(s.StandardSheetSize))}
              for s in part.DrawingSheets]
    result['sheets'] = sheets
    assert len(sheets) == 1, {'expected exactly the final sheet': sheets}
    sheet = list(part.DrawingSheets)[0]
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                        'SPARK3 Diagnose lesend')
    sheet.Open()

    result['stage'] = 'borders'
    bz = sheet.BordersAndZones
    bz_info = {'type': type(bz).__name__, 'members': members(bz)}
    elems = []
    for cand in ('GetElements', 'GetBorderElements', 'AskElements'):
        fn = getattr(bz, cand, None)
        if fn is None:
            continue
        try:
            got = fn()
        except Exception as error:
            elems.append({'via': cand, 'error': str(error)[:200]})
            continue
        try:
            items = list(got)
        except Exception:
            items = [got]
        for it in items:
            elems.append({'via': cand, 'type': type(it).__name__,
                          'str': safe(lambda i=it: str(i)),
                          'members': safe(lambda i=it: members(i), 600)})
    bz_info['elements'] = elems
    result['borders_and_zones'] = bz_info

    result['stage'] = 'views'
    vreps = []
    for vw in sheet.SheetDraftingViews:
        rep = {'name': safe(lambda v=vw: v.Name),
               'origin': safe(lambda v=vw: str(v.Origin)),
               'scale': safe(lambda v=vw: str(v.Scale)),
               'scale_factor': safe(lambda v=vw: str(v.ScaleFactor)),
               'minmax': safe(lambda v=vw: str(v.CalculateMinMaxBox())),
               'out_of_date': safe(lambda v=vw: bool(v.IsOutOfDate)),
               'n_visible': safe(lambda v=vw: len(v.AskVisibleObjects()))}
        vreps.append(rep)
    result['views'] = vreps
    result['workview'] = safe(lambda: type(part.Views.WorkView).__name__
                              + '/' + str(part.Views.WorkView.Name))
    result['stage'] = 'complete'
