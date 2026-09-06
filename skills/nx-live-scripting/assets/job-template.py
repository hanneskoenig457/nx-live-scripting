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
    result = {'ok': False, 'stage': 'start', 'pid': os.getpid(), 'steps': []}

    def checkpoint(stage):
        # Written as the job progresses: if NX blocks or the job is interrupted,
        # the last stage recorded is how far it got.
        result['stage'] = stage
        (out / 'result.json').write_text(json.dumps(result, indent=2))

    try:
        build(out, result, checkpoint)
        result['ok'] = True
    except Exception:
        # An exception escaping into NX opens a modal dialog that blocks the NX
        # message loop, and with it the dispatcher, until someone clicks OK in
        # the VM. Every job reports its own failure instead.
        result['error'] = traceback.format_exc()
    checkpoint(result['stage'])


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
