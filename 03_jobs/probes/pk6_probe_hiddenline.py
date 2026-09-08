"""Probe: what type is HiddenLinesViewStyle.Hiddenline, and does setting it
actually change AskVisibleObjects() count on a base view with occluded
circular edges? Scratch probe for the Pruefkoerper drawing job."""
import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Drawings


MODEL_PART_NAME = '20260907T221542Z-4cc24901.prt'


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False}
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

        sb = part.DrawingSheets.DrawingSheetBuilder(None)
        sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
        sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        sb.MetricSheetTemplateLocation = r'C:\Users\hanne\Documents\OnlineMachiningNX\templates\KUP_Zeichenvorlage.prt'
        sheet = sb.Commit()
        sb.Destroy()
        sheet.Open()
        part.Drafting.SetTemplateInstantiationIsComplete(True)
        sheet.SetName('PROBE_HL_' + out.name[-8:])

        right_view = model_part.ModelingViews.FindObject('RIGHT')
        end = sheet.SheetDraftingViews.CreateBaseView(
            right_view, NXOpen.Point3d(150.0, 150.0, 0.0), 1.0, False)
        part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
        end.Update()

        hl = end.Style.HiddenLines
        before_val = hl.Hiddenline
        result['hiddenline_type'] = type(before_val).__name__
        result['hiddenline_before'] = str(before_val)
        result['hiddenline_members'] = sorted(m for m in dir(hl) if not m.startswith('_'))
        before_count = len(list(end.AskVisibleObjects()))
        result['visible_before'] = before_count

        # Try boolean True first.
        try:
            hl.Hiddenline = True
            part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
            end.Update()
            result['after_bool_true'] = str(end.Style.HiddenLines.Hiddenline)
            result['visible_after_bool_true'] = len(list(end.AskVisibleObjects()))
        except Exception:
            result['bool_true_error'] = traceback.format_exc()

        try:
            result['self_hidden_before'] = str(hl.SelfHidden)
            hl.SelfHidden = True
            part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
            end.Update()
            result['self_hidden_after'] = str(end.Style.HiddenLines.SelfHidden)
            result['visible_after_self_hidden'] = len(list(end.AskVisibleObjects()))
        except Exception:
            result['self_hidden_error'] = traceback.format_exc()

        # Enumerate the enum type if Hiddenline is an enum, and try each value.
        enum_type = type(before_val)
        if hasattr(enum_type, '__members__'):
            result['enum_members'] = list(enum_type.__members__.keys())
            for name, val in enum_type.__members__.items():
                try:
                    hl.Hiddenline = val
                    part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
                    end.Update()
                    cnt = len(list(end.AskVisibleObjects()))
                    result.setdefault('enum_trials', {})[name] = cnt
                except Exception as exc:
                    result.setdefault('enum_trials', {})[name] = f'error: {exc}'

        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
