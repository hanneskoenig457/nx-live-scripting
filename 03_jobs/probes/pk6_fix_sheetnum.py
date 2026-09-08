"""Fix cosmetic sheet-numbering leftover: the surviving sheet was created as
the 7th of what were then 7 sheets (6 failed/probe iterations since deleted
by pk6_cleanup.py), so its auto-filled 'Blatt/von' cells still read 7/7.
Only one sheet exists now; it should read 1/1."""
import json
import os
import traceback
from pathlib import Path

import NXOpen

MODEL_PART_NAME = '20260907T221542Z-4cc24901.prt'
SHEET_NAME = 'PK6_0b0c669f'


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'pid': os.getpid()}
    try:
        session = NXOpen.Session.GetSession()
        model_part = None
        for p in session.Parts:
            try:
                if p.FullPath.endswith(MODEL_PART_NAME):
                    model_part = p
                    break
            except Exception:
                continue
        assert model_part is not None
        session.Parts.SetDisplay(model_part, False, True)
        part = session.Parts.Display

        sheets = [s for s in part.DrawingSheets if s.Name == SHEET_NAME]
        assert sheets, ('sheet not found', [s.Name for s in part.DrawingSheets])
        sheet = sheets[0]
        sheet.Open()

        try:
            result['before'] = {'SHEET_NUM': part.GetUserAttributeAsString('SHEET_NUM'),
                                 'NO_OF_SHEET': part.GetUserAttributeAsString('NO_OF_SHEET')}
        except Exception:
            result['before'] = 'could not read: ' + traceback.format_exc()

        for label, value in (('SHEET_NUM', '1'), ('NO_OF_SHEET', '1')):
            try:
                part.SetUserAttribute(label, -1, value, NXOpen.Update.Option.Now)
                result.setdefault('set_ok', []).append(label)
            except Exception:
                result.setdefault('set_failed', {})[label] = traceback.format_exc()

        part.Views.Regenerate()
        part.Views.WorkView.Fit()
        part.Views.WorkView.UpdateDisplay()
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

        builder = part.PlotManager.CreatePrintPdfbuilder()
        try:
            builder.SourceBuilder.SetSheets([sheet])
            pdf_path = out / (out.name + '.pdf')
            builder.Filename = str(pdf_path)
            builder.Commit()
        finally:
            builder.Destroy()
        result['pdf_export'] = {'exists': pdf_path.exists(),
                                 'size_bytes': pdf_path.stat().st_size if pdf_path.exists() else 0}
        assert pdf_path.exists()

        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
