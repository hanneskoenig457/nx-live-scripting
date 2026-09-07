"""SPARK3 Titelzellen-Fix: mK -> m, Werkstoff -> 1.4301 (Mikro-Run).

Befund Run 20260907T072753Z-dd2d4cfe: 11/13 Zellen folgen den Attributen,
aber Allgemeintoleranz bleibt 'DIN ISO 2768-mK' und Werkstoff leer
(Readback der Attribute ist korrekt -> Zell-Verknuepfung statisch/anders).
Fix: Labels lesen (Kartierung), Text direkt setzen, Commit, Ruecklesung,
PDF-Re-Export. Kein neues Blatt, kein Purge. Mark-IDs protokolliert.
ok = Zellen ok AND pdf ok. result.json (UTF-8).
"""
import json
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Annotations
import NXOpen.Drawings

BASE_PRT = ('C:/Users/hanne/Documents/OnlineMachiningNX/'
            '20260907T072108Z-24b9e214/20260907T072108Z-24b9e214.prt')


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'marks': {}, 'cells': []}
    try:
        run(out, result)
        result['ok'] = bool(result.get('cells_ok', False)
                            and result.get('pdf_ok', False))
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
    assert want is not None, {'model part not open': BASE_PRT}
    shown = safe(lambda: str(session.Parts.Display.FullPath))
    if not (isinstance(shown, str) and shown.replace('\\', '/').lower()
            == BASE_PRT.lower()):
        session.Parts.SetDisplay(want)
    part = want

    sheets = list(part.DrawingSheets)
    assert len(sheets) == 1, {'sheet state': [
        safe(lambda s=s: s.Name) for s in sheets]}
    sheet = sheets[0]
    sheet.Open()
    result['sheet'] = safe(lambda: sheet.Name)

    result['stage'] = 'map cells'
    mid = session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                              'SPARK3 Titelzellen')
    result['marks']['cells'] = safe(lambda: str(mid))
    blocks = list(part.DraftingManager.TitleBlocks)
    assert blocks, 'kein Schriftfeld'
    eb = part.DraftingManager.TitleBlocks \
        .CreateEditTitleBlockBuilder([blocks[0]])
    try:
        n = eb.Cells.Length
        result['n_cells'] = n
        grid = []
        for i in range(n):
            c = eb.Cells.FindItem(i)
            info = {'index': i}
            info['label'] = safe(lambda cc=c: str(cc.Label))
            info['text_before'] = safe(lambda cc=c: str(cc.Text))[:80]
            info['editable'] = safe(lambda cc=c: str(cc.EditableText))
            grid.append(info)
        result['cells'] = grid

        result['stage'] = 'edit cells'
        eb3 = part.DraftingManager.TitleBlocks \
            .CreateEditTitleBlockBuilder([blocks[0]])
        try:
            result['editbuilder_members'] = [
                m for m in members(eb3) if 'Cell' in m or 'Value' in m]
            assert hasattr(eb3, 'SetCellValueForLabel'), \
                'SetCellValueForLabel fehlt'
            eb3.SetCellValueForLabel('Allgemeintoleranz', 'DIN ISO 2768-m')
            result['set_tol'] = 'called'
            try:
                eb3.SetCellValueForLabel(
                    'Material, wird automatisch ausgefüllt', '1.4301')
                result['set_mat'] = 'called'
            except Exception as error:
                result['set_mat'] = 'ERR: ' + str(error)[:200]
            eb3.Commit()
            result['committed'] = True
        except Exception as error:
            result['set_error'] = str(error)[:300]
            result['committed'] = False
        finally:
            try:
                eb3.Destroy()
            except Exception:
                pass
    finally:
        try:
            eb.Destroy()
        except Exception:
            pass
    result['stage'] = 'verify cells'
    eb2 = part.DraftingManager.TitleBlocks \
        .CreateEditTitleBlockBuilder([blocks[0]])
    try:
        texts = []
        for i in range(eb2.Cells.Length):
            texts.append(safe(
                lambda cc=eb2.Cells.FindItem(i): str(cc.Text))[:80])
        result['verify_texts'] = texts
        joined = '\n'.join(texts)
        result['cells_ok'] = ('2768-mK' not in joined) and \
            ('1.4301' in joined)
    finally:
        try:
            eb2.Destroy()
        except Exception:
            pass
    if watchable:
        time.sleep(1.0)

    result['stage'] = 're-export PDF'
    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
    pdf_path = str(out / (out.name + '.pdf'))
    pdf = part.PlotManager.CreatePrintPdfbuilder()
    try:
        pdf.Filename = pdf_path
        pdf.SourceBuilder.SetSheets([sheet])
        pdf.Colors = NXOpen.PrintPDFBuilder.Color.BlackOnWhite
        pdf.Size = NXOpen.PrintPDFBuilder.SizeOption.FullScale
        pdf.OutputText = NXOpen.PrintPDFBuilder.OutputTextOption.Text
        pdf.Commit()
    finally:
        pdf.Destroy()
    import os
    result['pdf'] = pdf_path
    result['pdf_bytes'] = os.path.getsize(pdf_path)
    result['pdf_ok'] = result['pdf_bytes'] > 1000

    result['stage'] = 'save'
    status = part.Save(NXOpen.BasePart.SaveComponents.TrueValue,
                       NXOpen.BasePart.CloseAfterSave.FalseValue)
    status.Dispose()
    result['saved'] = True
    result['stage'] = 'complete'
