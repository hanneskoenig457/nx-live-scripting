"""Probe: what does RevolveBuilder.Limits actually expose in this NX build?
Scratch probe for the Pruefkoerper (abstract.md) job, not a deliverable."""
import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False}
    try:
        session = NXOpen.Session.GetSession()
        part = session.Parts.NewDisplay(str(out / (out.name + '.prt')),
                                         NXOpen.Part.Units.Millimeters)
        builder = part.Features.CreateRevolveBuilder(None)
        try:
            limits = builder.Limits
            result['limits_type'] = type(limits).__name__
            result['limits_members'] = sorted(
                m for m in dir(limits) if not m.startswith('_'))
            for name in ('StartAngle', 'EndAngle', 'FullAngle'):
                if hasattr(limits, name):
                    val = getattr(limits, name)
                    result[name] = {
                        'type': type(val).__name__,
                        'members': sorted(m for m in dir(val)
                                           if not m.startswith('_')),
                    }
        finally:
            builder.Destroy()
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
