"""SPARK3 Probe: wie findet man das ANGEZEIGTE Teil? (read-only, keine Commits)

Dumpt members(session.Parts) + je offenem Teil FullPath/Name sowie ob
ModelingViews.WorkView und DrawingSheets lesbar sind. Klaert den
Display-Kontext fuer den Zeichnungs-Job.
"""
import json
import traceback
from pathlib import Path

import NXOpen


def members(obj):
    return sorted(n for n in dir(obj) if not n.startswith('_'))


def safe(fn, limit=300):
    try:
        return fn()
    except Exception as error:
        return 'ERR: ' + str(error)[:limit]


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start'}
    try:
        session = NXOpen.Session.GetSession()
        result['parts_members'] = members(session.Parts)
        parts = []
        for p in session.Parts:
            entry = {'full': safe(lambda q=p: str(q.FullPath)),
                     'name': safe(lambda q=p: str(q.Name)),
                     'workview': safe(lambda q=p: str(
                         q.ModelingViews.WorkView)),
                     'sheets': safe(lambda q=p: str(
                         list(q.DrawingSheets)))}
            parts.append(entry)
        result['open_parts'] = parts
        result['ok'] = True
        result['stage'] = 'complete'
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(
        json.dumps(result, indent=2), encoding='utf-8')
