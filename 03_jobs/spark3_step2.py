"""SPARK3 Schritt 2: NUR UpdateViews(All) auf SPARK3_WATCH (kein Fit).

Framing-Isolation: Schritt 1 zeigte leeren Rahmen, linke Kante exakt auf
Blattkante. Jetzt fuellt sich die Ansicht -- entscheidende Beobachtung:
WO landet der Inhalt relativ zum Rahmen (ab Blatt-Null? ab Punkt 60?)?
Keine neue Ansicht, kein Fit, keine Masse. Mark-ID protokolliert.
result.json (UTF-8).
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

    result['stage'] = 'update all views'
    mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                              'SPARK3 Schritt2 UpdateViews')
    result['marks']['update'] = safe(lambda: str(mid))
    before = {safe(lambda v=v: v.Name): len(v.AskVisibleObjects())
              for v in sheet.SheetDraftingViews}
    result['before'] = before
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    after = {}
    for vw in sheet.SheetDraftingViews:
        after[safe(lambda v=vw: v.Name)] = {
            'out_of_date': bool(vw.IsOutOfDate),
            'visible_objects': len(vw.AskVisibleObjects())}
    result['after'] = after
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save (kein Fit, kein PDF)'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
