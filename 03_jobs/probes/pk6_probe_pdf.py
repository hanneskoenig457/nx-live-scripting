"""Probe: PrintPDFBuilder / its SourceBuilder shape on this NX build.
Scratch probe for the Pruefkoerper (abstract.md) drawing job, not a deliverable."""
import json
import traceback
from pathlib import Path

import NXOpen


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False}
    try:
        session = NXOpen.Session.GetSession()
        part = session.Parts.Display
        builder = part.PlotManager.CreatePrintPdfbuilder()
        try:
            result['builder_members'] = sorted(
                m for m in dir(builder) if not m.startswith('_'))
            src = builder.SourceBuilder
            result['source_builder_type'] = type(src).__name__
            result['source_builder_members'] = sorted(
                m for m in dir(src) if not m.startswith('_'))
        finally:
            builder.Destroy()
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
