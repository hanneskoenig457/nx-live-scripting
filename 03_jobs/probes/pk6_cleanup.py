"""Drafting-only cleanup: remove leftover/failed sheets from earlier
Pruefkoerper drawing iterations, keeping only the accepted final sheet.
Model features are never touched (api-drafting.md Section 7)."""
import json
import os
import traceback
from pathlib import Path

import NXOpen

MODEL_PART_NAME = '20260907T221542Z-4cc24901.prt'
KEEP_SHEET_NAME = 'PK6_0b0c669f'


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

        sheets = list(part.DrawingSheets)
        result['inventory'] = [{'name': s.Name} for s in sheets]

        keep = [s for s in sheets if s.Name == KEEP_SHEET_NAME]
        assert keep, (f'{KEEP_SHEET_NAME} not found among sheets', result['inventory'])
        keep[0].Open()

        to_delete = [s for s in sheets
                     if (s.Name.startswith('PK6_') or s.Name.startswith('PROBE_HL_'))
                     and s.Name != KEEP_SHEET_NAME]
        result['to_delete'] = [s.Name for s in to_delete]

        if to_delete:
            mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, 'Zwischenblaetter loeschen')
            session.UpdateManager.AddToDeleteList(to_delete)
            session.UpdateManager.DoUpdate(mark)

        remaining = [s.Name for s in part.DrawingSheets]
        result['remaining'] = remaining
        assert KEEP_SHEET_NAME in remaining, ('kept sheet missing after cleanup', result)
        assert all(name not in remaining for name in result['to_delete']), ('a targeted sheet survived', result)

        keep[0].Open()
        part.Views.WorkView.Fit()
        part.Views.WorkView.UpdateDisplay()
        part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
