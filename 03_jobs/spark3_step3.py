"""SPARK3 Schritt 3: Ansicht per MoveView/SetOrigin verschieben (HYBRID-Sweep).

Stand (User-Befund): Inhalt klebt bei Blatt-x~0 (Punkt ignoriert), Massstab
2.0 ok (70 Modell -> ~133 Blatt). Jetzt: Front-Ansicht auf freie Position
verschieben. Kandidaten der Reihe nach, jeder mit eigenem Befund:
  1. MoveView(Point3d(100,110,0)) -- Sheet-Ziel vermutet
  2. SetOrigin(Point3d(100,110,0)) -- Setter-Sibling zu read-only Origin
Erfolg = kein Fehler + danach Screenshot-Urteil. Mark-IDs protokolliert.
Kein Fit, kein PDF. result.json (UTF-8).
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
TARGET = (100.0, 110.0)


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'marks': {}, 'attempts': []}
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

    sheets = [s for s in part.DrawingSheets
              if safe(lambda x=s: x.Name) == WATCH]
    assert len(sheets) == 1, {'watch sheet state': [
        safe(lambda s=s: s.Name) for s in part.DrawingSheets]}
    sheet = sheets[0]
    sheet.Open()
    vws = [v for v in sheet.SheetDraftingViews
           if safe(lambda x=v: x.Name).startswith('Front')]
    assert vws, 'keine Front-Ansicht auf WATCH'
    vw = vws[0]
    result['view'] = safe(lambda: vw.Name)
    before = {'origin': safe(lambda: [round(float(vw.Origin.X), 2),
                                      round(float(vw.Origin.Y), 2),
                                      round(float(vw.Origin.Z), 2)]),
              'out_of_date': bool(vw.IsOutOfDate),
              'visible_objects': len(vw.AskVisibleObjects())}
    result['before'] = before

    result['stage'] = 'move attempts'
    mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                              'SPARK3 Schritt3 Move')
    result['marks']['move'] = safe(lambda: str(mid))
    target = NXOpen.Point3d(TARGET[0], TARGET[1], 0.0)
    moved = False
    for how in ('MoveView', 'SetOrigin'):
        entry = {'how': how}
        try:
            getattr(vw, how)(target)
            entry['called'] = True
            moved = True
            result['move_used'] = how
            break
        except Exception as error:
            entry['error'] = str(error)[:250]
        result['attempts'].append(entry)
    assert moved, {'move failed': result['attempts']}
    try:
        vw.Update()
    except Exception as error:
        result['update'] = 'WARN: ' + str(error)[:150]
    result['after'] = {
        'origin': safe(lambda: [round(float(vw.Origin.X), 2),
                                round(float(vw.Origin.Y), 2),
                                round(float(vw.Origin.Z), 2)]),
        'out_of_date': bool(vw.IsOutOfDate),
        'visible_objects': len(vw.AskVisibleObjects())}
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'save (kein Fit, kein PDF)'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
