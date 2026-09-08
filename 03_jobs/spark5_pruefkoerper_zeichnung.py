"""Spark5-Pruefkoerper: Blatt aus Firmenvorlage + Ansichten + PDF (Phase 1b, Teil 1).

Oeffnet das mit spark5_pruefkoerper_model.py gebaute Teil (Pfad kommt aus
parameters.json, siehe job-contract.md Regel 5 - kein os.environ), legt ein
Blatt auf der KUP-Vorlage an, setzt Basistitelattribute, erzeugt Front/Top/
Left-Ansichten (Muster aus api-drafting.md Paragraph 1-3) und exportiert eine
erste PDF. Bemassung/Toleranzen folgen in einem Folgejob.

Which canned view shows which end is checked BEFORE any NX call at all, via
CANNED_VIEW_X_END below, instead of reading it off a rendered PDF — that
found and fixed the earlier bug (M6 sits at x=0=min-X; 'Right' shows max-X,
so the M6 face was never in that render) with zero images and zero NX calls.
An attempted live check (compare view.AskVisibleObjects() Tags against the
model's own end-face Tags) was tried first and is a dead end: a drafting
view's AskVisibleObjects() returns view-local drafting-curve/body objects,
not the model's Face objects, so a Tag-based match against uf.Modeling.
AskFaceData() faces never fires — see api-drafting.md dead-ends.
"""
import json
import os
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Annotations
import NXOpen.Drawings
import NXOpen.Layer

TEMPLATE = r'C:\Users\hanne\Documents\OnlineMachiningNX\templates\KUP_Zeichenvorlage.prt'
SCALE = 1.0

# Empirically verified 2026-09-07, run 20260907T191233Z-a97821e0: NX's 'Right'
# canned view exposes a part's MAX-X end (camera looks toward -X in the
# absolute WCS); 'Left' is diametrically opposite in the standard orthographic
# arrangement (both first- and third-angle agree on which AXIS each named view
# looks along, only the sheet LAYOUT differs) and so shows MIN-X. Front/Top/
# Back/Bottom look along Y/Z, not X — they show the profile, not an X-end.
# This is a fixed, part-independent fact about NX's named views, not something
# to re-derive per part.
CANNED_VIEW_X_END = {'Right': 'max', 'Left': 'min'}


def assert_view_shows_x_end(model_view_name, expected_end, why):
    shown = CANNED_VIEW_X_END.get(model_view_name)
    assert shown == expected_end, {
        'wrong canned view for this feature': why,
        'model_view': model_view_name, 'shows_x_end': shown, 'need': expected_end}


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': [],
              'rules': [], 'deviations': [], 'views': {}}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    try:
        params = json.loads((out / 'parameters.json').read_text())
        build(out, params, result, checkpoint)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def build(out, params, result, checkpoint, watchable=True):
    session = NXOpen.Session.GetSession()

    checkpoint('open model')
    model_path = params['model_path']
    wanted = model_path.replace('\\', '/').lower()
    part = None
    for candidate in session.Parts:
        full = str(candidate.FullPath).replace('\\', '/').lower()
        if full == wanted:
            part = candidate
            break
    opened_fresh = False
    if part is None:
        opened = session.Parts.OpenDisplay(model_path)
        part, status = opened[0], opened[1]
        opened_fresh = True
        if part is None:
            raise RuntimeError({'open failed': [status.GetStatusDescription(i)
                                                 for i in range(status.NumberUnloadedParts)]})
    session.Parts.SetDisplay(part, True, True)
    shown = str(session.Parts.Display.FullPath).replace('\\', '/').lower()
    assert shown == wanted, {'wrong part displayed': shown, 'expected': wanted}
    result['steps'].append({'label': 'Modell bereit', 'path': shown, 'opened_fresh': opened_fresh})

    checkpoint('sheet from template')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Blatt aus Vorlage')
    sb = part.DrawingSheets.DrawingSheetBuilder(None)
    try:
        sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
        sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        sb.MetricSheetTemplateLocation = TEMPLATE
        sheet = sb.Commit()
    finally:
        sb.Destroy()
    sheet.Open()
    part.Drafting.SetTemplateInstantiationIsComplete(True)
    part.Layers.SetState(256, NXOpen.Layer.State.Visible)
    result['steps'].append({'label': 'Blatt angelegt', 'sheet': sheet.Name})
    if watchable:
        time.sleep(1.0)

    checkpoint('title block attrs')
    part.SetUserAttribute('Bezeichnung/Titel', -1,
                           'Pruefkoerper Online-Fertigung', NXOpen.Update.Option.Now)
    part.SetTimeUserAttribute('Datum', -1,
                               params.get('date', '07-Sep-2026 00:00:00'), NXOpen.Update.Option.Now)
    blocks = list(part.DraftingManager.TitleBlocks)
    if blocks:
        eb = part.DraftingManager.TitleBlocks.CreateEditTitleBlockBuilder([blocks[0]])
        try:
            eb.SetCellValueForLabel('Allgemeintoleranz', 'ISO 2768-m')
            eb.SetCellValueForLabel('Material, wird automatisch ausgefüllt', '1.4301')
            eb.Commit()
        finally:
            eb.Destroy()
    result['steps'].append({'label': 'Titelzellen gesetzt', 'blocks_found': len(blocks)})

    checkpoint('views')
    # M6+Zentrierung sitzt bei x=0 (min-X) - 'Left' statt 'Right' zeigt sie.
    assert_view_shows_x_end('Left', 'min', 'M6+Zentrierung liegt bei x=0')
    view_objects = {}  # NXOpen objects never go into `result` (job-contract.md rule 2)
    view_defs = (
        ('front', 'Front', NXOpen.Point3d(160.0, 170.0, 0.0), NXOpen.Point3d(60.0, 150.0, 0.0)),
        ('end', 'Left', NXOpen.Point3d(330.0, 170.0, 0.0), NXOpen.Point3d(230.0, 150.0, 0.0)),
        ('top', 'Top', NXOpen.Point3d(160.0, 70.0, 0.0), NXOpen.Point3d(60.0, 60.0, 0.0)),
    )
    for label, model_view, at, mv_to in view_defs:
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Ansicht ' + label)
        mv = part.ModelingViews.FindObject(model_view)
        vw = sheet.SheetDraftingViews.CreateBaseView(mv, at, SCALE, False)
        vw.Update()
        try:
            vw.MoveView(mv_to)
        except Exception:
            pass
        vw.Update()
        view_objects[label] = vw
        if watchable:
            time.sleep(1.0)

    part.DraftingViews.UpdateViews(
        NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)

    checkpoint('verify views fresh')
    fresh = {}
    for label, vw in view_objects.items():
        fresh[label] = {'out_of_date': bool(vw.IsOutOfDate),
                         'visible_objects': len(vw.AskVisibleObjects())}
    result['views'] = fresh
    checkpoint('verify views fresh')
    not_fresh = [label for label, v in fresh.items()
                 if v['out_of_date'] or v['visible_objects'] == 0]
    assert not not_fresh, {'views stale/empty': not_fresh, 'views': fresh}

    checkpoint('regenerate + fit + save')
    part.Views.Regenerate()
    sheet.Open()
    part.Views.WorkView.Fit()
    part.Views.WorkView.UpdateDisplay()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

    checkpoint('pdf export')
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
    result['pdf'] = pdf_path
    result['pdf_bytes'] = os.path.getsize(pdf_path)
    assert result['pdf_bytes'] > 1000, {'pdf too small': result['pdf_bytes']}
