"""SPARK3 Template-Inspektion (read-only, KEIN CloseAll, keine Commits).

Liest KUP_Zeichenvorlage.prt im Hintergrund und berichtet, was ein
Template-Blatt braucht: Bogen (Name/Groesse/Massstab), Schriftfeld-Namen,
Attribut-TITEL (danach fuellen Jobs die Zellen), Tabellen, Layer der
Rahmen-Objekte, Notiz-Probe. Legt nichts an, speichert nichts.
result.json (UTF-8).
"""
import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Annotations
import NXOpen.Drawings

TEMPLATE = r'C:/Users/hanne/Documents/OnlineMachiningNX/templates/KUP_Zeichenvorlage.prt'


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=500):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start'}
    try:
        run(out, result)
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')


def run(out, result):
    session = NXOpen.Session.GetSession()
    result['stage'] = 'open template'
    opened = session.Parts.Open(TEMPLATE)
    template = opened[0]
    assert template is not None, 'Template-Open gab None'
    result['template'] = safe(lambda: template.Name)

    result['stage'] = 'sheets'
    sheets = []
    for sh in template.DrawingSheets:
        entry = {}
        for attr in ('Name', 'Height', 'Length', 'Scale', 'Number',
                     'Revision'):
            entry[attr] = safe(lambda s=sh, a=attr: getattr(s, a))
        entry['objects'] = safe(lambda s=sh: len(s.GetAllObjects()))
        layers = {}
        try:
            for obj in sh.GetAllObjects():
                key = safe(lambda o=obj: str(o.Layer))
                layers[key] = layers.get(key, 0) + 1
        except Exception:
            pass
        entry['object_layers'] = layers
        sheets.append(entry)
    result['sheets'] = sheets

    result['stage'] = 'attributes'
    result['attributes'] = safe(lambda: [
        {'title': a.Title, 'type': str(a.Type),
         'value': safe(lambda aa=a: str(aa.StringValue))}
        for a in template.GetUserAttributes()])

    result['stage'] = 'title blocks + tables + notes'
    result['title_blocks'] = safe(lambda: [
        safe(lambda t=t: t.Name)
        for t in template.DraftingManager.TitleBlocks])
    result['table_count'] = safe(
        lambda: len(list(template.Annotations.Tables)))
    result['notes_sample'] = safe(lambda: [
        safe(lambda n=n: ' | '.join(n.GetText()))[:160]
        for n in list(template.Notes)][:25])
    result['stage'] = 'complete (offen gelassen, nichts gespeichert)'
