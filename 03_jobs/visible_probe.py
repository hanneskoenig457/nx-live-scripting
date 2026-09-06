"""Smoke test for the visible dispatcher: reports the NX process it ran in."""
import json
import os
import traceback
from pathlib import Path
import NXOpen


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False}
    try:
        work = NXOpen.Session.GetSession().Parts.Work
        result['pid'] = os.getpid()
        result['body_count'] = 0 if work is None else len(list(work.Bodies))
        result['ok'] = True
    except Exception:
        # An exception escaping into NX opens a modal dialog that stalls the queue.
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2))
