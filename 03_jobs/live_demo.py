"""Live demonstration: builds geometry step by step in the visible NX session.

Each step gets its own undo mark and repaints the view before pausing, so the
construction can be followed on screen. Setup specimen, not production CAD.
"""
import json
import os
import time
import traceback
from pathlib import Path
import NXOpen
import NXOpen.Features

PLAN = [
    ('Rohling', '25', '70', 0.0),
    ('Lagersitz', '20', '18', 70.0),
    ('Zapfen', '12', '10', 88.0),
]


def cylinder(part, diameter, height, x):
    builder = part.Features.CreateCylinderBuilder(None)
    try:
        builder.Type = NXOpen.Features.CylinderBuilder.Types.AxisDiameterAndHeight
        builder.Origin = NXOpen.Point3d(x, 0.0, 0.0)
        builder.Direction = NXOpen.Vector3d(1.0, 0.0, 0.0)
        builder.Diameter.RightHandSide = diameter
        builder.Height.RightHandSide = height
        return builder.CommitFeature()
    finally:
        builder.Destroy()


def main(job_dir):
    out = Path(job_dir)
    result = {'ok': False, 'pid': os.getpid(), 'steps': []}
    try:
        build(out, result)
        result['ok'] = True
    except Exception:
        # An exception escaping into NX opens a modal dialog that stalls the queue,
        # so every job reports its own failure instead.
        result['error'] = traceback.format_exc()
    (out / 'result.json').write_text(json.dumps(result, indent=2))


def build(out, result):
    session = NXOpen.Session.GetSession()
    # The run directory name keeps the part unique: NX refuses a second part with a
    # name already loaded in the session, and the session outlives a single job.
    part = session.Parts.NewDisplay(str(out / (out.name + '.prt')), NXOpen.Part.Units.Millimeters)
    view = part.ModelingViews.WorkView
    for label, diameter, height, x in PLAN:
        session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible, label)
        feature = cylinder(part, diameter, height, x)
        view.Orient(NXOpen.View.Canned.Trimetric, NXOpen.View.ScaleAdjustment.Fit)
        view.UpdateDisplay()
        result['steps'].append({'label': label, 'feature': feature.JournalIdentifier})
        # Paced so the construction is watchable; remove for unattended runs.
        time.sleep(1.5)
    result['body_count'] = len(list(part.Bodies))
