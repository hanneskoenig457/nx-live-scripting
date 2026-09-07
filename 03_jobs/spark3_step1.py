"""SPARK3 Schritt 1: EINE Basisansicht auf SPARK3_WATCH (kein Fit).

Framing-Isolation, ein Schritt pro Run. Erwartung zur Pruefung durch den
Zuschauer: Front-Ansicht erscheint; Lage relativ zum (bestaetigten)
Blattrahmen beobachten -- kreuzt Inhalt den Rahmen? Alle folgenden Runs
bauen auf diesem Blatt auf (fester Name, kein neues Blatt pro Schritt).
Mark-IDs werden protokolliert. result.json (UTF-8).
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Drawings

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260906T153508Z-a28c46ac/20260906T153508Z-a28c46ac.prt')
WATCH = 'SPARK3_WATCH'


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'marks': {}}
    try:
        run(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result, watchable=True):
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
    shown = safe(lambda: str(session.Parts.Display.FullPath))
    if not (isinstance(shown, str) and shown.replace('\\', '/').lower()
            == BASE_PRT.lower()):
        session.Parts.SetDisplay(want)
    part = want

    result['stage'] = 'find sheet'
    sheets = [s for s in part.DrawingSheets
              if safe(lambda x=s: x.Name) == WATCH]
    assert len(sheets) == 1, {'watch sheet state': [
        safe(lambda s=s: s.Name) for s in part.DrawingSheets]}
    sheet = sheets[0]
    sheet.Open()

    result['stage'] = 'one base view'
    mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                              'SPARK3 Schritt1 Front')
    result['marks']['front'] = safe(lambda: str(mid))
    mv = part.ModelingViews.FindObject('Front')
    vw = sheet.SheetDraftingViews.CreateBaseView(
        mv, NXOpen.Point3d(60.0, 110.0, 0.0), 2.0, False)
    vw.Update()
    result['view'] = {'name': safe(lambda: vw.Name),
                      'out_of_date': bool(vw.IsOutOfDate),
                      'visible_objects': len(vw.AskVisibleObjects()),
                      'scale_at_creation': safe(lambda: str(vw.Scale))}
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save (no Fit, no PDF -- Beobachtungsschritt)'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
