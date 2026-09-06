"""Probe: what the CMTS/TU-Berlin drawing template offers and which NX APIs reach it.

Read-only. Answers, before any drawing code is written:
 1. What KUP_Zeichenvorlage.prt contains (sheets, frame, title block, and which
    part attributes the title block reads).
 2. Whether DrawingSheetBuilder.SheetOption.UseTemplate accepts a full path, so
    the template works without administrator rights on the NX installation.
 3. Which members the builders for section views, surface finish symbols, title
    blocks and the drafting standard expose in this NX build.

Runs headless through run_journal and through the visible dispatcher alike.
"""
import json
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Annotations
import NXOpen.Drafting
import NXOpen.Drawings
import NXOpen.Preferences

TEMPLATE_DIR = Path(r'C:\Users\hanne\Documents\OnlineMachiningNX\templates')
DRAWING_TEMPLATE = TEMPLATE_DIR / 'KUP_Zeichenvorlage.prt'


def members(obj):
    return sorted(name for name in dir(obj) if not name.startswith('_'))


def safe(fn, limit=400):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir=None):
    out = Path(job_dir) if job_dir else Path(__file__).resolve().parent
    result = {'ok': False}
    try:
        probe(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))


def inspect_template(session, result):
    template = session.Parts.Open(str(DRAWING_TEMPLATE))[0]
    info = {'name': template.Name, 'sheets': []}
    sheets = list(template.DrawingSheets)
    for sheet in sheets:
        entry = {}
        for attr in ('Name', 'Height', 'Length', 'Scale', 'Number', 'Revision'):
            entry[attr] = safe(lambda s=sheet, a=attr: getattr(s, a))
        entry['objects'] = safe(lambda s=sheet: len(s.GetAllObjects()))
        info['sheets'].append(entry)
    if sheets:
        info['sheet_members'] = members(sheets[0])
    info['attributes'] = safe(lambda: [
        {'title': a.Title, 'type': str(a.Type),
         'value': safe(lambda a=a: str(a.StringValue))}
        for a in template.GetUserAttributes()])
    info['notes'] = safe(lambda: [safe(lambda n=n: ' | '.join(n.GetText()))
                                  for n in list(template.Notes)][:120])
    info['table_count'] = safe(lambda: len(list(template.Annotations.Tables)))
    info['table_section_count'] = safe(lambda: len(list(template.Annotations.TableSections)))
    tables = safe(lambda: list(template.Annotations.Tables))
    if isinstance(tables, list) and tables:
        info['table_members'] = members(tables[0])
    info['title_blocks'] = safe(lambda: [
        safe(lambda t=t: t.Name) for t in template.DraftingManager.TitleBlocks])
    info['title_block_collection_members'] = safe(
        lambda: members(template.DraftingManager.TitleBlocks))
    info['drafting_manager_members'] = safe(lambda: members(template.DraftingManager))
    layers = {}
    for obj in safe(lambda: sheets[0].GetAllObjects()) or []:
        key = safe(lambda o=obj: str(o.Layer))
        layers[key] = layers.get(key, 0) + 1
    info['sheet_object_layers'] = layers
    result['template'] = info


def probe(out, result):
    session = NXOpen.Session.GetSession()
    result['release'] = safe(lambda: session.FullReleaseNumber)
    result['is_batch'] = safe(lambda: session.IsBatch)
    result['template_exists'] = DRAWING_TEMPLATE.exists()
    session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None)

    try:
        inspect_template(session, result)
    except Exception:
        result['template_error'] = traceback.format_exc()[-1500:]
    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))

    scratch_file = out / 'template_probe_scratch.prt'
    if scratch_file.exists():
        scratch_file.unlink()
    part = session.Parts.NewDisplay(str(scratch_file), NXOpen.Part.Units.Millimeters)
    session.ApplicationSwitchImmediate('UG_APP_DRAFTING')

    trials = {}
    for label, location in (('full_path', str(DRAWING_TEMPLATE)),
                            ('bare_name', 'KUP_Zeichenvorlage.prt')):
        entry = {}
        builder = None
        try:
            builder = part.DrawingSheets.DrawingSheetBuilder(None)
            entry['builder_members'] = members(builder)
            builder.Option = NXOpen.Drawings.DrawingSheetBuilder.SheetOption.UseTemplate
            builder.Units = NXOpen.Drawings.DrawingSheetBuilder.SheetUnits.Metric
            builder.MetricSheetTemplateLocation = location
            builder.Name = 'PROBE_' + label.upper()
            sheet = builder.Commit()
            entry['ok'] = True
            for attr in ('Name', 'Length', 'Height'):
                entry[attr] = safe(lambda s=sheet, a=attr: getattr(s, a))
            entry['objects'] = safe(lambda s=sheet: len(s.GetAllObjects()))
            entry['section_lines_member'] = safe(lambda s=sheet: members(s.SheetSectionLines))
        except Exception as error:
            entry['ok'] = False
            entry['error'] = str(error)[:600]
        finally:
            if builder is not None:
                safe(lambda b=builder: b.Destroy())
        trials[label] = entry
    result['use_template'] = trials

    api = {}
    api['sheet_option_values'] = members(NXOpen.Drawings.DrawingSheetBuilder.SheetOption)
    api['annotations_manager'] = members(part.Annotations)
    api['drafting_views_collection'] = members(part.DraftingViews)
    api['drafting_manager'] = safe(lambda: members(part.DraftingManager))
    api['drafting_namespace'] = members(NXOpen.Drafting)

    def builder_members(label, factory, extra=()):
        entry = {}
        obj = None
        try:
            obj = factory()
            entry['members'] = members(obj)
            for name in extra:
                entry[name] = safe(lambda o=obj, n=name: members(getattr(o, n)))
        except Exception as error:
            entry['error'] = str(error)[:600]
        finally:
            if obj is not None:
                safe(lambda o=obj: o.Destroy())
        api[label] = entry

    builder_members('section_view',
                    lambda: part.DraftingViews.CreateSectionViewBuilder(None),
                    extra=('Method', 'Parent'))
    builder_members('surface_finish',
                    lambda: part.Annotations.DraftingSurfaceFinishSymbols
                    .CreateDraftingSurfaceFinishSymbolBuilder(None))
    builder_members('load_drafting_standard',
                    lambda: session.Preferences.Drafting.CreateLoadDraftingStandardBuilder())
    builder_members('distribute_annotations',
                    lambda: part.Drafting.CreateDistributeAnnotationsBuilder(None))
    api['drafting_preference_manager'] = safe(lambda: members(session.Preferences.Drafting))
    api['part_drafting_preferences'] = safe(lambda: members(part.Preferences.Drafting))
    api['part_drafting'] = safe(lambda: members(part.Drafting))
    api['section_view_enums'] = safe(
        lambda: {n: members(getattr(NXOpen.Drawings.SectionViewBuilder, n))
                 for n in members(NXOpen.Drawings.SectionViewBuilder)
                 if n[0].isupper() and isinstance(getattr(NXOpen.Drawings.SectionViewBuilder, n), type)})
    result['api'] = api

    safe(lambda: session.Parts.CloseAll(NXOpen.BasePart.CloseModified.CloseModified, None))
    if scratch_file.exists():
        safe(lambda: scratch_file.unlink())


if __name__ == '__main__':
    main()
