"""SPARK3 Reset: Modell-only + EIN leeres Blatt (Schritt-fuer-Schritt-Basis).

Anlass: Framing-/Rahmen-Mechanismus isoliert beobachten. Echte UndoToMark
geht nicht mehr (alte Mark-IDs nie protokolliert) -- daher sauberer Reset:
alle SPARK3_*-Boegen loeschen, EIN leeres Blatt 'SPARK3_WATCH' anlegen +
oeffnen, KEIN Fit (Fit ist eigene Variable, kommt spaeter).
Ab jetzt: JEDE Undo-Marke mit ID protokollieren ( Rueckweg offen halten).
Nur Drawing-Zweig; Modell-Features unberuehrt. result.json (UTF-8).
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Drawings

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260906T153508Z-a28c46ac/20260906T153508Z-a28c46ac.prt')
PREFIX = 'SPARK3_'
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


def mark(session, result, key, label):
    mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, label)
    result['marks'][key] = safe(lambda: str(mid))
    return mid


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
    result['part'] = safe(lambda: part.JournalIdentifier)

    result['stage'] = 'inventory'
    result['before'] = [safe(lambda s=s: s.Name)
                        for s in part.DrawingSheets]

    result['stage'] = 'purge'
    mark(session, result, 'purge', 'SPARK3 Reset Purge')
    purged = []
    for sh in list(part.DrawingSheets):
        nm = safe(lambda s=sh: str(s.Name))
        if isinstance(nm, str) and nm.startswith(PREFIX):
            m = session.SetUndoMark(
                NXOpen.Session.MarkVisibility.Invisible, 'Blatt weg')
            session.UpdateManager.AddToDeleteList([sh])
            session.UpdateManager.DoUpdate(m)
            purged.append(nm)
    result['purged'] = purged
    if watchable:
        time.sleep(1.0)

    result['stage'] = 'blank sheet'
    mark(session, result, 'sheet', 'SPARK3 leeres Blatt')
    sb = part.DrawingSheets.DrawingSheetBuilder(None)
    try:
        sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.CustomSize
        sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        sb.Length = 297.0
        sb.Height = 210.0
        sb.Name = WATCH
        sb.ScaleNumerator = 1.0
        sb.ScaleDenominator = 1.0
        sb.ProjectionAngle = NXOpen.Drawings.DrawingSheetBuilder \
            .SheetProjectionAngle.First
        sheet = sb.Commit()
    finally:
        sb.Destroy()
    sheet.Open()
    result['sheet'] = WATCH
    try:
        part.ModelingViews.WorkView.UpdateDisplay()
    except Exception as error:
        result['repaint'] = 'WARN: ' + str(error)[:200]
    if watchable:
        time.sleep(1.5)

    result['stage'] = 'verify+save'
    result['after'] = [safe(lambda s=s: s.Name)
                       for s in part.DrawingSheets]
    assert result['after'] == [WATCH], result['after']
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
