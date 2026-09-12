"""Execute a validated declarative plan in NX; never let an exception escape.

The operation vocabulary is inspired by the MIT-licensed DreamEnding/NX_MCP
project.  The NXOpen sequences below come from this toolkit's locally verified
SNIPPETS-modelling.md recipes and run through its visible-session dispatcher.
"""

import json
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer


WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling
PLAN_CONTRACT_VERSION = 1


def _write_result(job_dir, result):
    Path(job_dir, "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _object_summary(value):
    name = getattr(value, "Name", "")
    if callable(name):
        name = name()
    return {
        "name": str(name or type(value).__name__),
        "tag": int(value.Tag) if getattr(value, "Tag", None) is not None else None,
        "type": type(value).__name__,
    }


def _make_xz_sketch(part, name):
    datum_builder = part.Features.CreateDatumPlaneBuilder(None)
    try:
        datum_builder.SetFixedDatumPlane(NXOpen.Features.DatumPlaneBuilder.FixedType.Zx)
        datum_feature = datum_builder.CommitFeature()
    finally:
        datum_builder.Destroy()
    datum = [entity for entity in datum_feature.GetEntities() if isinstance(entity, NXOpen.DatumPlane)][0]

    sketch_builder = part.Sketches.CreateSketchInPlaceBuilder2(None)
    try:
        sketch_builder.PlaneOption = NXOpen.Sketch.PlaneOption.Inferred
        sketch_builder.PlaneOrFace.Value = datum
        sketch = sketch_builder.Commit()
    finally:
        sketch_builder.Destroy()
    sketch.SetName(name)
    sketch.Activate(NXOpen.Sketch.ViewReorient.FalseValue)
    return {
        "sketch": sketch,
        "datum": datum,
        "datum_feature": datum_feature,
        "curves": [],
        "finished": False,
    }


def _point_xz(value):
    return NXOpen.Point3d(float(value["x"]), 0.0, float(value["y"]))


def _add_line(part, sketch_state, start, end):
    curve = part.Curves.CreateLine(_point_xz(start), _point_xz(end))
    sketch_state["sketch"].AddGeometry(
        curve, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    )
    sketch_state["curves"].append(curve)
    return curve


def _finish_sketch(sketch_state):
    sketch = sketch_state["sketch"]
    sketch.Update()
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.FalseValue, NXOpen.Sketch.UpdateLevel.Model)
    sketch_state["finished"] = True
    return sketch


def _extrude(part, sketch_state, distance, reverse):
    curves = sketch_state["curves"]
    if not curves:
        raise RuntimeError("Cannot extrude an empty sketch")
    section = part.Sections.CreateSection(0.01, 0.01, 0.01)
    section.AddToSection(
        [part.ScRuleFactory.CreateRuleCurveDumb(curves)],
        curves[0],
        None,
        None,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create,
    )
    direction = part.Directions.CreateDirection(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, -1.0 if reverse else 1.0, 0.0),
        WITHIN,
    )
    builder = part.Features.CreateExtrudeBuilder(None)
    try:
        builder.Section = section
        builder.Direction = direction
        builder.Limits.StartExtend.SetValue("0")
        builder.Limits.EndExtend.SetValue(str(distance))
        builder.BooleanOperation.Type = (
            NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        )
        feature = builder.CommitFeature()
    finally:
        builder.Destroy()
    bodies = list(feature.GetBodies())
    if not bodies:
        raise RuntimeError("Extrude committed without creating a body")

    part.Layers.MoveDisplayableObjects(
        21, [sketch_state["sketch"]] + list(sketch_state["curves"])
    )
    part.Layers.MoveDisplayableObjects(61, [sketch_state["datum"]])
    part.Layers.SetState(21, NXOpen.Layer.State.Hidden)
    part.Layers.SetState(61, NXOpen.Layer.State.Hidden)
    part.Layers.WorkLayer = 1
    return feature, bodies[0]


def _execute_operation(session, state, operation):
    tool = operation["tool"]
    # The host normalizes this to an object for every operation.  Keeping the
    # empty-object default here makes the static runner defensive when a plan
    # is replayed directly through the documented batch diagnostic path.
    args = operation.get("args", {})
    operation_id = operation.get("id")
    part = state.get("part")

    if tool == "nx_create_part":
        requested = Path(args["path"])
        unique_name = requested.stem + "-" + state["job_dir"].name + requested.suffix
        destination = (state["job_dir"] / requested.parent / unique_name).resolve()
        if state["job_dir"] not in destination.parents:
            raise RuntimeError("Part path escaped the run directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        units = (
            NXOpen.Part.Units.Millimeters
            if args["units"] == "mm"
            else NXOpen.Part.Units.Inches
        )
        part = session.Parts.NewDisplay(str(destination), units)
        state["part"] = part
        output = {
            "part": _object_summary(part),
            "requested_path": args["path"],
            "path": str(destination),
        }
    elif tool == "nx_create_sketch":
        sketch_state = _make_xz_sketch(part, args["name"])
        state["refs"][operation_id] = sketch_state
        output = {"sketch": _object_summary(sketch_state["sketch"]), "plane": "XZ"}
    elif tool == "nx_sketch_line":
        sketch_state = state["refs"][args["sketch"]]
        output = {"curve": _object_summary(_add_line(part, sketch_state, args["start"], args["end"]))}
    elif tool == "nx_sketch_rectangle":
        sketch_state = state["refs"][args["sketch"]]
        first, second = args["corner1"], args["corner2"]
        corners = [
            {"x": first["x"], "y": first["y"]},
            {"x": second["x"], "y": first["y"]},
            {"x": second["x"], "y": second["y"]},
            {"x": first["x"], "y": second["y"]},
        ]
        curves = [
            _add_line(part, sketch_state, corners[index], corners[(index + 1) % 4])
            for index in range(4)
        ]
        output = {"curves": [_object_summary(curve) for curve in curves]}
    elif tool == "nx_finish_sketch":
        sketch_state = state["refs"][args["sketch"]]
        output = {"sketch": _object_summary(_finish_sketch(sketch_state))}
    elif tool == "nx_extrude":
        sketch_state = state["refs"][args["sketch"]]
        feature, body = _extrude(
            part, sketch_state, args["distance"], args.get("reverse", False)
        )
        if operation_id:
            state["refs"][operation_id] = {"feature": feature, "body": body}
        output = {"feature": _object_summary(feature), "body": _object_summary(body)}
    elif tool == "nx_list_sketches":
        output = {"objects": [_object_summary(value) for value in part.Sketches]}
    elif tool == "nx_list_bodies":
        output = {"objects": [_object_summary(value) for value in part.Bodies]}
    elif tool == "nx_list_features":
        output = {"objects": [_object_summary(value) for value in part.Features]}
    elif tool == "nx_fit_view":
        part.Views.WorkView.Fit()
        output = {"message": "View fitted"}
    elif tool == "nx_save_part":
        part.Save(
            NXOpen.BasePart.SaveComponents.TrueValue,
            NXOpen.BasePart.CloseAfterSave.FalseValue,
        )
        output = {"message": "Part saved", "path": str(part.FullPath)}
    else:
        raise RuntimeError("Unsupported tool reached NX: " + str(tool))
    if operation_id:
        output["id"] = operation_id
    return output


def main(job_dir):
    job_path = Path(job_dir).resolve()
    result = {
        "ok": False,
        "executor": "nx-high-level-plan-v1",
        "contract_version": PLAN_CONTRACT_VERSION,
        "steps": [],
    }
    session = None
    plan_mark = None
    try:
        plan = json.loads((job_path / "parameters.json").read_text(encoding="utf-8"))
        if plan.get("contract_version") != PLAN_CONTRACT_VERSION:
            raise RuntimeError(
                "High-level plan contract mismatch: expected "
                + str(PLAN_CONTRACT_VERSION)
                + ", received "
                + str(plan.get("contract_version"))
            )
        session = NXOpen.Session.GetSession()
        state = {"job_dir": job_path, "part": None, "refs": {}}
        for index, operation in enumerate(plan["operations"]):
            if operation["tool"] != "nx_create_part":
                session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Visible,
                    "NX high-level: " + operation["tool"],
                )
            output = _execute_operation(session, state, operation)
            result["steps"].append(
                {"index": index, "tool": operation["tool"], "ok": True, "output": output}
            )
            if operation["tool"] == "nx_create_part":
                # NewDisplay changes the active part and invalidates an undo mark
                # created in the previous part.  The atomic model mark therefore
                # begins immediately after the new, unique run-local part exists.
                plan_mark = session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Visible, "NX high-level plan"
                )
        result["ok"] = True
        result["part"] = _object_summary(state["part"])
    except Exception as error:
        rollback = {
            "scope": "model operations after run-local part creation",
            "container_part_retained": plan_mark is not None,
            "attempted": plan_mark is not None,
            "ok": False,
        }
        if session is not None and plan_mark is not None:
            try:
                session.UndoToMark(plan_mark, None)
                rollback["ok"] = True
            except Exception as rollback_error:
                rollback["error"] = str(rollback_error)
        result["error"] = {
            "layer": "nx_api",
            "type": type(error).__name__,
            "message": str(error),
            "nx_code": getattr(error, "ErrorCode", None),
            "traceback": traceback.format_exc(),
        }
        result["rollback"] = rollback
    finally:
        _write_result(job_path, result)


if __name__ == "__main__":
    main(Path(__file__).resolve().parent)
