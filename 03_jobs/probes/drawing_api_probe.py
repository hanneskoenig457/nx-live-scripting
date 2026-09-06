"""Probe: the drawing APIs the rebuilt Fertigungszeichnung needs.

Read-only for the model. Creates a throw-away sheet from the TU-Berlin template
on the specimen, hangs one view and one dimension on it, and reports the member
surface of everything the new drawing job will touch: dimension text placement,
ISO limits-and-fits tolerancing, surface finish symbols, section and detail
views, the title block, and the symbolic thread. Nothing is saved.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Annotations
import NXOpen.Drawings
import NXOpen.Features
import NXOpen.Preferences

TEMPLATE = Path(r'C:\Users\hanne\Documents\OnlineMachiningNX\templates\KUP_Zeichenvorlage.prt')
PART_NAME = 'pruefkoerper'


def members(obj):
    return sorted(name for name in dir(obj) if not name.startswith('_'))


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def describe(obj):
    """Members of an object plus the values of every enum type nested in it."""
    out = {'type': safe(lambda: type(obj).__name__), 'members': safe(lambda: members(obj))}
    nested = {}
    for name in out['members'] if isinstance(out['members'], list) else []:
        value = safe(lambda o=obj, n=name: getattr(o, n))
        if isinstance(value, type):
            nested[name] = safe(lambda v=value: members(v))
    if nested:
        out['nested'] = nested
    return out


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def probe(out, result):
    session = NXOpen.Session.GetSession()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)
    part_file = out.parent / 'specimen' / (PART_NAME + '.prt')
    part = session.Parts.OpenDisplay(str(part_file))[0]
    session.ApplicationSwitchImmediate('UG_APP_DRAFTING')
    body = list(part.Bodies)[0]

    api = {}
    api['annotations_namespace'] = [n for n in members(NXOpen.Annotations)
                                    if any(k in n for k in ('Text', 'Placement', 'Position',
                                                            'Orientation', 'LimitFit',
                                                            'SurfaceFinish', 'Arrow'))]
    api['part_drafting_preferences'] = describe(part.Preferences.Drafting)
    api['annotation_preferences'] = describe(safe(lambda: part.Annotations.Preferences))
    api['surface_finish_symbols'] = describe(safe(lambda: part.Annotations.DraftingSurfaceFinishSymbols))
    api['surface_finish_symbol'] = describe(safe(lambda: part.Annotations.DraftingSurfaceFinishSymbol))

    builder = None
    try:
        builder = part.DrawingSheets.DrawingSheetBuilder(None)
        builder.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
        builder.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
        builder.MetricSheetTemplateLocation = str(TEMPLATE)
        sheet = builder.Commit()
    finally:
        if builder is not None:
            safe(lambda: builder.Destroy())
    sheet.Open()
    result['sheet'] = {'name': safe(lambda: sheet.Name),
                       'size': [safe(lambda: sheet.Length), safe(lambda: sheet.Height)],
                       'scale': safe(lambda: sheet.GetScale()),
                       'views': safe(lambda: len(list(sheet.SheetDraftingViews)))}
    result['sheet_set_parameters_doc'] = safe(lambda: str(sheet.SetParameters.__doc__)[:1200])
    result['title_blocks'] = safe(lambda: [safe(lambda t=t: t.JournalIdentifier)
                                           for t in part.DraftingManager.TitleBlocks])
    api['edit_title_block'] = safe(lambda: describe(
        part.DraftingManager.TitleBlocks.CreateEditTitleBlockBuilder(
            list(part.DraftingManager.TitleBlocks)[0])))

    view = sheet.SheetDraftingViews.CreateBaseView(
        part.ModelingViews.FindObject('Front'), NXOpen.Point3d(140.0, 200.0, 0.0), 2.0, False)
    view.Update()
    api['drafting_view'] = describe(view)

    # One dimension, so the real object can be inspected rather than the class.
    edges = [e for e in body.GetEdges()
             if e.GetVertices() and abs(float(e.GetVertices()[0].X)) < 0.02]
    dim = None
    try:
        data = part.Annotations.NewDimensionData()
        assoc = part.Annotations.NewAssociativity()
        assoc.FirstObject = edges[0]
        assoc.ObjectView = view
        assoc.PointOption = NXOpen.Annotations.AssociativityPointOption.ArcCenter
        data.SetAssociativity(1, [assoc])
        assoc2 = part.Annotations.NewAssociativity()
        far = [e for e in body.GetEdges()
               if e.GetVertices() and abs(float(e.GetVertices()[0].X) - 70.0) < 0.02]
        assoc2.FirstObject = far[0]
        assoc2.ObjectView = view
        assoc2.PointOption = NXOpen.Annotations.AssociativityPointOption.ArcCenter
        data.SetAssociativity(2, [assoc2])
        dim = part.Dimensions.CreateHorizontalDimension(data, NXOpen.Point3d(140.0, 150.0, 0.0))
    except Exception:
        result['dimension_error'] = traceback.format_exc()[-1200:]
    api['dimension'] = describe(dim) if dim is not None else 'not created'
    if dim is not None:
        prefs = safe(lambda: dim.GetDimensionPreferences()) if hasattr(dim, 'GetDimensionPreferences') \
            else 'no GetDimensionPreferences'
        api['dimension_preferences'] = describe(prefs)
        api['dimension_lettering'] = describe(safe(lambda: dim.GetLetteringPreferences())) \
            if hasattr(dim, 'GetLetteringPreferences') else 'no getter'
        api['dimension_line_arrow'] = describe(safe(lambda: dim.GetLineAndArrowPreferences())) \
            if hasattr(dim, 'GetLineAndArrowPreferences') else 'no getter'
        api['associate_dimension_builder'] = safe(lambda: describe(
            part.Annotations.CreateAssociateDimensionBuilder(dim)))

    def builder_probe(label, factory):
        obj = None
        try:
            obj = factory()
            api[label] = describe(obj)
            for name in ('ViewPlacement', 'ViewOrientation', 'ViewStyle', 'SectionLineSegments',
                         'Leader', 'Origin', 'Text', 'Symbol', 'Material'):
                child = safe(lambda o=obj, n=name: getattr(o, n))
                if not isinstance(child, str):
                    api[label].setdefault('children', {})[name] = describe(child)
        except Exception as error:
            api[label] = {'error': str(error)[:600]}
        finally:
            if obj is not None:
                safe(lambda o=obj: o.Destroy())

    builder_probe('section_view_builder', lambda: part.DraftingViews.CreateSectionViewBuilder(None))
    builder_probe('detail_view_builder', lambda: part.DraftingViews.CreateDetailViewBuilder(None))
    builder_probe('section_in_view_builder', lambda: part.DraftingViews.CreateSectionInViewBuilder(None))
    builder_probe('note_builder', lambda: part.Annotations.CreateDraftingNoteBuilder(None))
    builder_probe('surface_finish_builder',
                  lambda: part.Annotations.DraftingSurfaceFinishSymbols
                  .CreateDraftingSurfaceFinishBuilder(None))
    builder_probe('symbolic_thread_builder',
                  lambda: part.Features.CreateSymbolicThreadBuilder(None))
    builder_probe('centerline_builder',
                  lambda: part.Annotations.Centerlines.CreateCenterlineBuilder(None))
    result['api'] = api
    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))


if __name__ == '__main__':
    main()
