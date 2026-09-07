"""Template for a dispatched NX job. Copy into 03_jobs/ and rename.

The dispatcher archives this file as job.py in a run directory inside the VM,
verifies its SHA-256, and calls the global main() with that directory. Everything
the job reports travels back in result.json; nothing else is evidence.
"""
import json
import os
import time
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': [],
              'rules': [], 'deviations': []}

    def checkpoint(stage):
        # Written as the job progresses: if NX blocks or the job is interrupted,
        # the last stage recorded is how far it got.
        result['stage'] = stage
        # UTF-8 explicitly: NX's embedded Python defaults to cp1252 and the
        # host's json.loads then fails on the first umlaut.
        (out / 'result.json').write_text(json.dumps(result, indent=2),
                                         encoding='utf-8')

    try:
        # Pre-flight first: declare every skill/project rule this job must
        # satisfy (rule ID + how it will be met). Reading the skill is not
        # compliance — an explicit per-task rule list is. Overall ok below
        # requires every rule resolved, not just green numbers.
        build(out, result, checkpoint)
        open_rules = [r['rule'] for r in result['rules']
                      if r.get('status') not in ('met', 'deviated')]
        assert not open_rules, {'unresolved rules': open_rules}
        result['ok'] = True
    except Exception:
        # An exception escaping into NX opens a modal dialog that blocks the NX
        # message loop, and with it the dispatcher, until someone clicks OK in
        # the VM. Every job reports its own failure instead.
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


def require_rule(result, rule_id, how):
    """Declare a rule BEFORE building (e.g. 'F-2 two views', 'R-2.1 nest').
    Dimensions/annotations record their rule alongside nominal/computed."""
    result['rules'].append({'rule': rule_id, 'how': how, 'status': 'open'})


def resolve_rule(result, rule_id, evidence):
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'met', 'evidence': evidence})


def deviate(result, rule_id, tried, fallback, why):
    """A fallback is not silent: record what was tried, what was kept, and
    why — with run id as evidence. An undocumented fallback is a defect."""
    result['deviations'].append({'rule': rule_id, 'tried': tried,
                                 'fallback': fallback, 'why': why})
    for r in result['rules']:
        if r['rule'] == rule_id:
            r.update({'status': 'deviated'})


def build(out, result, checkpoint, watchable=True):
    session = NXOpen.Session.GetSession()

    # The run directory name keeps the part unique: the session outlives a single
    # job and NewDisplay refuses a name already loaded.
    checkpoint('create part')
    part = session.Parts.NewDisplay(str(out / (out.name + '.prt')),
                                    NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView

    for label, diameter, height, x in [('Rohling', '25', '70', 0.0)]:
        # One visible undo mark per logical step, so a wrong step stays
        # recoverable by hand in the GUI.
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, label)
        checkpoint(label)
        feature = cylinder(part, diameter, height, x)
        # The job runs as one uninterrupted block on the NX main thread, so NX
        # repaints only when told.
        view.Orient(NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit)
        view.UpdateDisplay()
        result['steps'].append({'label': label, 'feature': feature.JournalIdentifier})
        if watchable:
            time.sleep(1.5)  # paced to be followed on screen; drop for unattended runs

    result['body_count'] = len(list(part.Bodies))
    # Verify what was produced rather than trusting the absence of an exception.
    assert result['body_count'] > 0, result


def cylinder(part, diameter, height, x):
    builder = part.Features.CreateCylinderBuilder(None)
    try:
        builder.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
        builder.Origin = NXOpen.Point3d(x, 0.0, 0.0)
        builder.Direction = NXOpen.Vector3d(1.0, 0.0, 0.0)
        # Expressions take strings; a float loses the parametric link.
        builder.Diameter.RightHandSide = diameter
        builder.Height.RightHandSide = height
        return builder.CommitFeature()
    finally:
        # A builder that is not destroyed leaks and makes later calls unpredictable.
        builder.Destroy()
