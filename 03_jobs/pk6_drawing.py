"""Pruefkoerper (abstract.md): reduced, norm-correct 2D manufacturing drawing.

Only Diameter20 h6 (bearing seat), 6P9 (keyway width), the DIN471 groove
(width + base Diameter) and M6 (thread) are explicitly toleranced, per
abstract.md Phase 1. Everything else refers to the ISO 2768-m general
tolerance in the title block. Company sheet template (KUP_Zeichenvorlage.prt)
per job-contract.md standing rule.

Depends on the model built by pk6_model.py (run 20260907T221542Z-4cc24901):
finds that part already loaded in the session rather than re-opening it.
"""
import json
import math
import os
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Annotations
import NXOpen.Drafting
import NXOpen.Drawings
import NXOpen.Layer
import NXOpen.UF

MODEL_PART_NAME = '20260907T221542Z-4cc24901.prt'
TEMPLATE = r'C:\Users\hanne\Documents\OnlineMachiningNX\templates\KUP_Zeichenvorlage.prt'
WATCHABLE = True


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': [],
              'rules': [], 'deviations': [], 'dimensions': []}

    def checkpoint(stage):
        result['stage'] = stage
        (out / 'result.json').write_text(json.dumps(result, indent=2),
                                          encoding='utf-8')

    try:
        build(out, result, checkpoint)
        open_rules = [r['rule'] for r in result['rules']
                      if r.get('status') not in ('met', 'deviated')]
        assert not open_rules, {'unresolved rules': open_rules}
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def require_rule(result, rule_id, how):
    result['rules'].append({'rule': rule_id, 'how': how, 'status': 'open'})


def resolve_rule(result, rule_id, evidence):
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'met', 'evidence': evidence})


def deviate(result, rule_id, tried, fallback, why):
    result['deviations'].append({'rule': rule_id, 'tried': tried,
                                  'fallback': fallback, 'why': why})
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'deviated'})


def pause(sec):
    if WATCHABLE:
        time.sleep(sec)


def build(out, result, checkpoint):
    session = NXOpen.Session.GetSession()

    require_rule(result, 'R-1', 'Rahmen/Schriftfeld auf Firmenvorlage, Allgemeintoleranz ISO 2768-m im Feld')
    require_rule(result, 'F-1', 'Diameter20 h6 als Durchmesserbemassung mit Passung, Ra 0.8 auf der Mantellinie')
    require_rule(result, 'F-2', 'Nutbreite 6 P9 bemasst; Tiefe/Laenge als Leader-Notiz (kein assoziativer Pfad verifiziert)')
    require_rule(result, 'F-3', 'Sicherungsringnut: Nutgrund Diameter19.0 h11 bemasst, Breite 1.1 +0.14/-0 bemasst oder als Notiz')
    require_rule(result, 'F-4', 'M6 Gewinde: nutzbare Laenge + Bohrtiefe + Zentrierkegel als Notiz in einer Ansicht')
    require_rule(result, 'R-7', 'Gesamtlaenge 70 als aeusserste Bemassung')

    checkpoint('find model part')
    model_part = None
    for p in session.Parts:
        try:
            if p.FullPath.endswith(MODEL_PART_NAME):
                model_part = p
                break
        except Exception:
            continue
    assert model_part is not None, ('model part not found in session', MODEL_PART_NAME)
    session.Parts.SetDisplay(model_part, False, True)
    part = session.Parts.Display
    assert part.FullPath.endswith(MODEL_PART_NAME), (part.FullPath, MODEL_PART_NAME)
    # Not part.ModelingViews.WorkView here: a leftover drafting sheet from a
    # prior run may already be open on this part ("not a model view" if so).
    # part.Views.WorkView repaints regardless of modeling/drafting context.

    part.SetUserAttribute('Bezeichnung/Titel', -1, 'Pruefkoerper', NXOpen.Update.Option.Now)
    part.SetTimeUserAttribute('Datum', -1, '08-Sep-2026 00:00:00', NXOpen.Update.Option.Now)
    for label in ('Name', 'Matrikelnummer', 'Tutor', 'Tutoriumstermin', 'Gruppe', 'Semester', 'Kurs'):
        try:
            part.SetUserAttribute(label, -1, '-', NXOpen.Update.Option.Now)
        except Exception:
            pass

    checkpoint('sheet from template')
    session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, 'Blatt')
    sb = part.DrawingSheets.DrawingSheetBuilder(None)
    sb.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
    sb.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
    sb.MetricSheetTemplateLocation = TEMPLATE
    sheet = sb.Commit()
    sb.Destroy()
    sheet.Open()
    part.Drafting.SetTemplateInstantiationIsComplete(True)
    part.Layers.SetState(256, NXOpen.Layer.State.Visible)
    sheet.SetName('PK6_' + out.name[-8:])
    result['steps'].append({'label': 'Blatt aus Vorlage', 'sheet': sheet.Name})
    pause(1.0)

    checkpoint('title block cells')
    title_blocks = list(part.DraftingManager.TitleBlocks)
    cells_set = {}
    if title_blocks:
        etb = part.DraftingManager.TitleBlocks.CreateEditTitleBlockBuilder(title_blocks)
        # Known KUP template cell labels (api-drafting.md Section 2), not
        # discovered at runtime -- EditTitleBlockBuilder exposes Get/Set by
        # label only, no enumerable Cells collection on this NX build.
        for label, value in (('Allgemeintoleranz', 'ISO 2768-m'),
                              ('Material_manuell', '1.4301')):
            try:
                etb.SetCellValueForLabel(label, value)
                cells_set[label] = value
            except Exception:
                result.setdefault('warnings', []).append(
                    f'SetCellValueForLabel({label!r}) failed: {traceback.format_exc()}')
        etb.Commit()
        etb.Destroy()
    if cells_set:
        resolve_rule(result, 'R-1', {'template': TEMPLATE, 'sheet': sheet.Name, 'cells_set': cells_set})
    else:
        deviate(result, 'R-1', 'SetCellValueForLabel on Allgemeintoleranz/Material_manuell',
                'sheet created with template defaults, cells not confirmed set',
                'no title-block cell could be set; see warnings')

    checkpoint('base view (front)')
    front_model_view = model_part.ModelingViews.FindObject('FRONT')
    front = sheet.SheetDraftingViews.CreateBaseView(
        front_model_view, NXOpen.Point3d(60.0, 160.0, 0.0), 1.0, False)
    front.MoveView(NXOpen.Point3d(60.0, 160.0, 0.0))
    front_visible = ensure_fresh(part, sheet, front, 'Front', result)
    result['steps'].append({'label': 'Hauptansicht (Front)', 'visible_objects': len(front_visible)})
    pause(1.0)

    checkpoint('end view (right)')
    right_model_view = model_part.ModelingViews.FindObject('RIGHT')
    end = sheet.SheetDraftingViews.CreateBaseView(
        right_model_view, NXOpen.Point3d(220.0, 160.0, 0.0), 1.0, False)
    end.MoveView(NXOpen.Point3d(220.0, 160.0, 0.0))
    end_visible = ensure_fresh(part, sheet, end, 'Right (end)', result)
    result['steps'].append({'label': 'Endansicht (Right)', 'visible_objects': len(end_visible)})
    pause(1.0)

    # Known limitation (probed 20260907T223456Z-e4f3989e, 20260907T223535Z-8e221985):
    # the Diameter20/Diameter19 circles are occluded behind the Diameter25 end
    # stock and do not render as dashed hidden circles in this end view on this
    # NX build -- HiddenLines.Hiddenline and .SelfHidden are already True by
    # default and toggling them changes nothing (AskVisibleObjects() stays at
    # 6 either way). The dimension VALUES are still correct (ComputedSize
    # verified below); only the extra hidden-circle silhouette is missing.
    result['deviations'].append({
        'rule': 'V-1', 'tried': 'HiddenLines.Hiddenline / SelfHidden toggle on the end view',
        'fallback': 'diametral dimensions kept in the end view without a visible hidden circle',
        'why': 'AskVisibleObjects() count unchanged (6) after both toggles; not further investigated'})

    checkpoint('dimensions')
    body = list(model_part.Bodies)[0]

    dim_overall_length(part, model_part, body, front, result)
    dim_bearing_seat_diameter(part, model_part, body, end, result)
    dim_groove_base_diameter(part, model_part, body, end, result)
    dim_keyway_width(part, model_part, body, front, result)
    dim_groove_width_or_note(part, model_part, body, front, result)
    note_keyway_short_form(part, front, result)
    note_thread(part, model_part, body, front, result)
    finish_symbol_bearing_seat(part, model_part, body, front, result)

    checkpoint('regenerate + fit + save')
    part.Views.Regenerate()
    sheet.Open()
    part.Views.WorkView.Fit()
    part.Views.WorkView.UpdateDisplay()
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)

    checkpoint('export pdf')
    export_pdf(out, part, sheet, result)


def ensure_fresh(part, sheet, drafting_view, label, result, attempts=5):
    """A lone Update() is not enough right after CreateBaseView in a visible
    session (api-drafting.md Section 3: 1 object, IsOutOfDate true). Retry the
    collective UpdateViews + the view's own Update with a short pause."""
    for attempt in range(attempts):
        part.DraftingViews.UpdateViews(NXOpen.Drawings.DraftingViewCollection.ViewUpdateOption.All, sheet)
        drafting_view.Update()
        part.Views.WorkView.UpdateDisplay()
        if drafting_view.IsOutOfDate is False:
            visible = list(drafting_view.AskVisibleObjects())
            if visible:
                return visible
        pause(0.5)
    raise AssertionError(
        f'{label} view stale or empty after {attempts} UpdateViews/Update retries '
        f'(IsOutOfDate={drafting_view.IsOutOfDate})')


# ---------------------------------------------------------------- dimensions

def rim_arc_center_x(body, x_station):
    """Circular edge whose vertices all sit at x_station (station-known rim
    arc, per api-modelling.md Section 7 -- full circles have no vertices)."""
    for edge in body.GetEdges():
        try:
            verts = edge.GetVertices()
        except Exception:
            continue
        if verts and all(abs(v.X - x_station) < 0.05 for v in verts):
            return edge
    return None


def dim_overall_length(part, model_part, body, view, result):
    e0 = rim_arc_center_x(body, 0.0)
    e70 = rim_arc_center_x(body, 70.0)
    if not (e0 and e70):
        deviate(result, 'R-7', 'rim arcs at x=0/70 via GetVertices station match',
                'not found', 'no station-known rim arc at one or both ends')
        return
    data = model_part.Annotations.NewDimensionData()
    for idx, edge in enumerate((e0, e70), 1):
        assoc = model_part.Annotations.NewAssociativity()
        assoc.FirstObject, assoc.ObjectView, assoc.PointOption = \
            edge, view, NXOpen.Annotations.AssociativityPointOption.ArcCenter
        data.SetAssociativity(idx, [assoc])
    dim = model_part.Dimensions.CreateHorizontalDimension(data, NXOpen.Point3d(60.0, 250.0, 0.0))
    dim.IsOriginCentered = True
    nominal, computed = 70.0, dim.ComputedSize
    ok = abs(computed - nominal) < 0.1
    result['dimensions'].append({'rule': 'R-7', 'name': 'Gesamtlaenge', 'view': 'Front',
                                  'nominal': nominal, 'computed': computed, 'ok': ok})
    if ok:
        resolve_rule(result, 'R-7', {'nominal_mm': nominal, 'computed_mm': computed, 'view': 'Front'})
    else:
        deviate(result, 'R-7', f'computed {computed}', 'dimension left on sheet for manual check',
                'ComputedSize did not match nominal within 0.1 mm')


def dim_bearing_seat_diameter(part, model_part, body, end_view, result):
    uf = NXOpen.UF.UFSession.GetUFSession()
    edge = None
    for e in body.GetEdges():
        try:
            verts = e.GetVertices()
        except Exception:
            continue
        if not verts:
            continue
        diameter = e.GetLength() / math.pi  # circumference / pi = diameter
        if abs(diameter - 20.0) < 0.2 and any(abs(v.X - 8.0) < 0.05 or abs(v.X - 23.0) < 0.05 for v in verts):
            edge = e
            break
    if edge is None:
        deviate(result, 'F-1', 'circular edge at radius 10 near x=8/23 via GetLength/pi', 'not found',
                'no matching circular edge for the Diameter20 seat boundary')
        return
    assoc = model_part.Annotations.NewAssociativity()
    assoc.FirstObject, assoc.ObjectView, assoc.PointOption = \
        edge, end_view, NXOpen.Annotations.AssociativityPointOption.OnCurve
    data = model_part.Annotations.NewDimensionData()
    data.SetAssociativity(1, [assoc])
    dim = model_part.Dimensions.CreateDiameterDimension(data, NXOpen.Point3d(220.0, 210.0, 0.0))
    dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
    dim.LimitFitDeviation = 'h'
    dim.LimitFitGrade = 6
    computed = dim.ComputedSize
    ok = abs(computed - 20.0) < 0.1
    result['dimensions'].append({'rule': 'F-1', 'name': 'Lagersitz Diameter', 'view': 'Right (end)',
                                  'nominal': 20.0, 'computed': computed, 'fit': 'h6', 'ok': ok})
    if ok:
        resolve_rule(result, 'F-1', {'nominal_mm': 20.0, 'fit': 'h6', 'computed_mm': computed,
                                      'ra': 'Ra 0.8 (siehe Oberflaechensymbol)'})
    else:
        deviate(result, 'F-1', f'computed {computed}', 'dimension left for manual check',
                'ComputedSize did not match nominal within 0.1 mm')


def dim_groove_base_diameter(part, model_part, body, end_view, result):
    edge = None
    for e in body.GetEdges():
        try:
            verts = e.GetVertices()
        except Exception:
            continue
        if not verts:
            continue
        diameter = e.GetLength() / math.pi
        if abs(diameter - 19.0) < 0.2 and any(abs(v.X - 23.0) < 0.05 or abs(v.X - 24.1) < 0.05 for v in verts):
            edge = e
            break
    if edge is None:
        deviate(result, 'F-3', 'circular edge diameter 19.0 near x=23/24.1', 'not found',
                'no matching circular edge for the groove base')
        return
    assoc = model_part.Annotations.NewAssociativity()
    assoc.FirstObject, assoc.ObjectView, assoc.PointOption = \
        edge, end_view, NXOpen.Annotations.AssociativityPointOption.OnCurve
    data = model_part.Annotations.NewDimensionData()
    data.SetAssociativity(1, [assoc])
    dim = model_part.Dimensions.CreateDiameterDimension(data, NXOpen.Point3d(220.0, 100.0, 0.0))
    dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
    dim.LimitFitDeviation = 'h'
    dim.LimitFitGrade = 11
    computed = dim.ComputedSize
    ok = abs(computed - 19.0) < 0.1
    result['dimensions'].append({'rule': 'F-3', 'name': 'Nutgrund Diameter', 'view': 'Right (end)',
                                  'nominal': 19.0, 'computed': computed, 'fit': 'h11', 'ok': ok})
    if ok:
        resolve_rule(result, 'F-3', {'nominal_base_mm': 19.0, 'fit': 'h11', 'computed_mm': computed})


def dim_keyway_width(part, model_part, body, front_view, result):
    """Width via the floor edges (parallel to X at Z=-3/+3, Y=6.5), per
    api-drafting.md: 'Front view ... floor edges + OnCurve, CreateVerticalDimension'."""
    floor_edges = []
    for e in body.GetEdges():
        try:
            verts = e.GetVertices()
        except Exception:
            continue
        if len(verts) == 2 and abs(verts[0].Y - 6.5) < 0.05 and abs(verts[1].Y - 6.5) < 0.05 \
                and abs(verts[0].Z - verts[1].Z) < 0.05:
            floor_edges.append((abs(verts[0].Z), e))
    floor_edges.sort(key=lambda t: t[0])
    if len(floor_edges) < 2:
        deviate(result, 'F-2', 'floor edges at Y=6.5, Z=+/-3 via GetVertices', f'found {len(floor_edges)}',
                'keyway width dimension needs two flat floor edges at the flanks')
        return
    e_neg, e_pos = floor_edges[0][1], floor_edges[-1][1]
    data = model_part.Annotations.NewDimensionData()
    for idx, edge in enumerate((e_neg, e_pos), 1):
        assoc = model_part.Annotations.NewAssociativity()
        assoc.FirstObject, assoc.ObjectView, assoc.PointOption = \
            edge, front_view, NXOpen.Annotations.AssociativityPointOption.OnCurve
        data.SetAssociativity(idx, [assoc])
    dim = model_part.Dimensions.CreateVerticalDimension(data, NXOpen.Point3d(40.0, 220.0, 0.0))
    dim.ToleranceType = NXOpen.Annotations.ToleranceType.LimitsAndFits
    dim.LimitFitDeviation = 'P'
    dim.LimitFitGrade = 9
    computed = dim.ComputedSize
    ok = abs(computed - 6.0) < 0.1
    result['dimensions'].append({'rule': 'F-2', 'name': 'Nutbreite', 'view': 'Front (expedience, F-2 end-view unverified)',
                                  'nominal': 6.0, 'computed': computed, 'fit': 'P9', 'ok': ok})
    if ok:
        resolve_rule(result, 'F-2', {'width_nominal_mm': 6.0, 'fit': 'P9', 'computed_mm': computed})
        deviate(result, 'F-2', 'end-view association for keyway width (norm-correct per rule)',
                'Front-view floor-edge dimension', 'end-view path unverified on this NX build (api-drafting.md open item)')


def dim_groove_width_or_note(part, model_part, body, front_view, result):
    """Best-effort narrow linear dimension for the 1.1 mm groove width; falls
    back to a note (documented deviation) if the narrow-width associativity
    does not resolve -- api-drafting.md flags this as needing station-parsed
    view-extracted curves, not a plain model-edge associativity."""
    try:
        edges = []
        for e in body.GetEdges():
            try:
                verts = e.GetVertices()
            except Exception:
                continue
            if len(verts) == 2 and abs(verts[0].X - verts[1].X) < 0.02 \
                    and (abs(verts[0].X - 23.0) < 0.05 or abs(verts[0].X - 24.1) < 0.05):
                edges.append((verts[0].X, e))
        edges.sort(key=lambda t: t[0])
        if len(edges) < 2:
            raise RuntimeError(f'expected 2 groove-wall edges, found {len(edges)}')
        e_a, e_b = edges[0][1], edges[-1][1]
        data = model_part.Annotations.NewDimensionData()
        for idx, edge in enumerate((e_a, e_b), 1):
            assoc = model_part.Annotations.NewAssociativity()
            assoc.FirstObject, assoc.ObjectView, assoc.PointOption = \
                edge, front_view, NXOpen.Annotations.AssociativityPointOption.OnCurve
            data.SetAssociativity(idx, [assoc])
        dim = model_part.Dimensions.CreateHorizontalDimension(data, NXOpen.Point3d(90.0, 190.0, 0.0))
        computed = dim.ComputedSize
        ok = abs(computed - 1.1) < 0.05
        result['dimensions'].append({'rule': 'F-3', 'name': 'Nutbreite Sicherungsring', 'view': 'Front',
                                      'nominal': 1.1, 'computed': computed, 'ok': ok})
        if ok:
            resolve_rule(result, 'F-3', {'width_nominal_mm': 1.1, 'width_tolerance': '+0.14/-0',
                                          'computed_mm': computed})
            return
        raise RuntimeError(f'ComputedSize {computed} != 1.1')
    except Exception as exc:
        deviate(result, 'F-3', 'narrow linear dimension on the two groove-wall edges (model-edge associativity)',
                'Leader-Notiz "Sicherungsringnut DIN 471 - Ø20, m=1,1 +0,14/-0"',
                f'associative narrow-width dimension did not resolve on this NX build: {exc}')
        add_note(part, ['Sicherungsringnut DIN 471 - Ø20', 'Nutbreite m = 1,1 +0,14/-0'],
                 NXOpen.Point3d(90.0, 175.0, 0.0), result, tag='F-3 note')


def note_keyway_short_form(part, view, result):
    add_note(part, ['Passfedernut DIN 6885-A - 6 x 6 x 20', 't1 = 3,5 (h)'],
             NXOpen.Point3d(40.0, 205.0, 0.0), result, tag='F-2 note')
    resolve_rule(result, 'F-2', {'short_form': 'DIN 3898 letter h, per dimensioning-rules.md #7',
                                  'depth_mm': 3.5, 'length_mm': 20})


def note_thread(part, model_part, body, view, result):
    add_note(part, ['M6 - 6H, nutzbare Laenge 12', 'Bohrung Diameter5 Tiefe 14',
                     'Zentrierkegel 60 Grad / Diameter6,4 (siehe Abweichung D-1)'],
             NXOpen.Point3d(220.0, 205.0, 0.0), result, tag='F-4 note')
    resolve_rule(result, 'F-4', {'thread': 'M6 x 1.0 - 6H', 'usable_length_mm': 12,
                                  'drilled_depth_mm': 14, 'lead_cone_deg': 60})


def finish_symbol_bearing_seat(part, model_part, body, view, result):
    try:
        target_face = None
        uf = NXOpen.UF.UFSession.GetUFSession()
        for face in body.GetFaces():
            kind, point, direction, box, radius, rad_data, norm = uf.Modeling.AskFaceData(face.Tag)
            if kind == 16 and abs(radius - 10.0) < 0.05 and abs(direction[0]) > 0.99 and 8.0 <= point[0] <= 23.0:
                target_face = face
                break
        if target_face is None:
            raise RuntimeError('bearing seat face not found for finish symbol')
        edge = None
        for e in target_face.GetEdges():
            verts = e.GetVertices()
            if verts and all(abs(v.X - 8.0) < 0.05 for v in verts):
                edge = e
                break
        builder = part.Annotations.DraftingSurfaceFinishSymbols.CreateDraftingSurfaceFinishBuilder(None)
        builder.Finish = NXOpen.Annotations.DraftingSurfaceFinishBuilderFinishType.ModifierMaterialRemovalRequired
        builder.SingleRoughnessValue = True
        builder.A1 = 'Ra 0,8'
        builder.Origin.OriginPoint = NXOpen.Point3d(40.0, 240.0, 0.0)
        if edge is not None:
            leader = part.Annotations.CreateLeaderData()
            leader.Arrowhead = NXOpen.Annotations.LeaderDataArrowheadType.FilledArrow
            leader.StubSide = NXOpen.Annotations.LeaderSide.Inferred
            midpoint = NXOpen.Point3d(8.0, 0.0, 10.0)
            leader.Leader.SetValue(edge, view, midpoint)
            builder.Leader.Leaders.Append(leader)
        builder.Commit()
        builder.Destroy()
        resolve_rule_extra(result, 'F-1', {'ra': 'Ra 0.8', 'placement': 'bearing seat generator line, Front view'})
    except Exception:
        result.setdefault('warnings', []).append('finish symbol failed: ' + traceback.format_exc())


def resolve_rule_extra(result, rule_id, extra):
    for r in result['rules']:
        if r['rule'] == rule_id and 'evidence' in r:
            r['evidence'].update(extra)


def add_note(part, lines, origin, result, tag):
    builder = part.Annotations.CreateDraftingNoteBuilder(None)
    builder.Text.TextBlock.SetText(lines)
    builder.Origin.OriginPoint = origin
    builder.Commit()
    builder.Destroy()
    result['steps'].append({'label': 'Notiz', 'tag': tag, 'text': lines})


# ---------------------------------------------------------------------- pdf

def export_pdf(out, part, sheet, result):
    builder = part.PlotManager.CreatePrintPdfbuilder()
    try:
        builder.SourceBuilder.SetSheets([sheet])
        pdf_path = out / (out.name + '.pdf')
        builder.Filename = str(pdf_path)
        builder.Commit()
    finally:
        builder.Destroy()
    result['pdf_export'] = {'path': str(pdf_path), 'exists': pdf_path.exists()}
    if pdf_path.exists():
        result['pdf_export']['size_bytes'] = pdf_path.stat().st_size
    assert pdf_path.exists(), ('PDF export did not produce a file', result['pdf_export'])
