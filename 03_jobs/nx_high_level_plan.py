"""Execute a validated declarative plan in NX; never let an exception escape.

The operation vocabulary is inspired by the MIT-licensed DreamEnding/NX_MCP
project.  The NXOpen sequences below come from this toolkit's locally verified
SNIPPETS-modelling.md recipes and run through its visible-session dispatcher.
"""

import json
import hashlib
import os
import subprocess
import traceback
from pathlib import Path

import NXOpen
import NXOpen.Features
import NXOpen.GeometricUtilities
import NXOpen.Layer


WITHIN = NXOpen.SmartObject.UpdateOption.WithinModeling
PLAN_CONTRACT_VERSION = 2
MODEL_MUTATIONS = {
    "nx_create_sketch",
    "nx_sketch_line",
    "nx_sketch_rectangle",
    "nx_finish_sketch",
    "nx_extrude",
}


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


def _part_summary(part):
    if part is None:
        return None
    result = _object_summary(part)
    result["path"] = str(part.FullPath)
    return result


def _nx_version(session):
    try:
        value = session.GetEnvironmentVariableValue("UGII_VERSION")
        if value:
            return str(value)
    except Exception:
        pass
    return "NX build unknown"


def _snapshot_refs(refs):
    snapshot = {}
    for key, value in refs.items():
        if isinstance(value, dict):
            copied = dict(value)
            if "curves" in copied:
                copied["curves"] = list(copied["curves"])
            snapshot[key] = copied
        else:
            snapshot[key] = value
    return snapshot


def _restore_snapshot(state, snapshot):
    state["refs"] = _snapshot_refs(snapshot["refs"])


def _open_staged_part(session, state, args):
    inputs_root = (state["job_dir"] / "inputs").resolve()
    source = (inputs_root / args["path"]).resolve()
    if inputs_root not in source.parents or not source.is_file():
        raise RuntimeError("Staged input part is missing or escaped inputs/")
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != args["sha256"]:
        raise RuntimeError("Staged input part SHA-256 mismatch")

    unique = source.with_name(
        source.stem + "-" + state["job_dir"].name + source.suffix
    )
    source.rename(unique)
    wanted = str(unique).replace("\\", "/").lower()
    part = None
    for candidate in session.Parts:
        if str(candidate.FullPath).replace("\\", "/").lower() == wanted:
            part = candidate
            break
    if part is None:
        opened = session.Parts.OpenDisplay(str(unique))
        part, status = opened[0], opened[1]
        if part is None:
            descriptions = [
                status.GetStatusDescription(index)
                for index in range(status.NumberUnloadedParts)
            ]
            raise RuntimeError("Part did not open: " + "; ".join(descriptions))
    session.Parts.SetDisplay(part, True, True)
    displayed = str(session.Parts.Display.FullPath).replace("\\", "/").lower()
    if displayed != wanted:
        raise RuntimeError("Opened part is not the active display part")
    state["part"] = part
    return {
        "part": _part_summary(part),
        "requested_path": args["requested_path"],
        "input_sha256": actual_hash,
    }


def _save_part(part):
    part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    return {"message": "Part saved", "path": str(part.FullPath)}


def _export_step(state, part, args):
    _save_part(part)
    destination = (state["job_dir"] / args["path"]).resolve()
    if state["job_dir"] not in destination.parents:
        raise RuntimeError("STEP path escaped the run directory")
    destination.parent.mkdir(parents=True, exist_ok=True)

    nx_base = r"C:\Program Files\Siemens\NX2506"
    step_exe = os.path.join(nx_base, "STEP214UG", "step214ug.exe")
    step_def = os.path.join(nx_base, "STEP214UG", "ugstep214.def")
    if not os.path.isfile(step_exe) or not os.path.isfile(step_def):
        raise RuntimeError("NX STEP214UG translator or definition file is missing")
    log_name = destination.stem + "-step214.log"
    process = subprocess.run(
        [
            step_exe,
            str(part.FullPath),
            "o=" + destination.name,
            "d=" + step_def,
            "l=" + log_name,
        ],
        cwd=str(destination.parent),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if process.returncode != 0 or not destination.is_file():
        raise RuntimeError(
            "STEP214UG failed: exit "
            + str(process.returncode)
            + "; "
            + (process.stderr or process.stdout or "no translator output")[-500:]
        )
    text = destination.read_text(encoding="utf-8", errors="ignore")
    ap214 = "AUTOMOTIVE_DESIGN" in text and "214" in text
    closed_shells = text.count("CLOSED_SHELL")
    advanced_faces = text.count("ADVANCED_FACE")
    if not ap214 or closed_shells < 1:
        raise RuntimeError("STEP output failed AP214/closed-shell verification")
    return {
        "message": "STEP AP214 exported",
        "path": str(destination),
        "size_bytes": destination.stat().st_size,
        "ap214": ap214,
        "closed_shells": closed_shells,
        "advanced_faces": advanced_faces,
        "translator_exit": process.returncode,
        "log_path": str(destination.parent / log_name),
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

    if tool == "nx_status":
        active = session.Parts.Work
        output = {
            "connected": True,
            "nx_version": _nx_version(session),
            "active_part": _part_summary(active),
        }
    elif tool == "nx_create_part":
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
            "part": _part_summary(part),
            "requested_path": args["path"],
            "path": str(destination),
        }
    elif tool == "nx_open_part":
        output = _open_staged_part(session, state, args)
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
        output = _save_part(part)
    elif tool == "nx_close_part":
        part_name = _object_summary(part)["name"]
        if args.get("save", True):
            _save_part(part)
        part.Close(
            NXOpen.BasePart.CloseWholeTree.TrueValue,
            NXOpen.BasePart.CloseModified.CloseModified,
            None,
        )
        state["part"] = None
        state["refs"] = {}
        state["undo_stack"] = []
        output = {"message": "Part closed", "part_name": part_name, "saved": args.get("save", True)}
    elif tool == "nx_export_step":
        output = _export_step(state, part, args)
    elif tool == "nx_undo":
        if not state["undo_stack"]:
            raise RuntimeError("No model mutation is available to undo")
        undo = state["undo_stack"].pop()
        session.UndoToMark(undo["mark"], None)
        _restore_snapshot(state, undo["snapshot"])
        output = {"message": "Undo successful", "undone_tool": undo["tool"]}
    else:
        raise RuntimeError("Unsupported tool reached NX: " + str(tool))
    if operation_id:
        output["id"] = operation_id
    return output


def main(job_dir):
    job_path = Path(job_dir).resolve()
    result = {
        "ok": False,
        "executor": "nx-high-level-plan-v2",
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
        state = {
            "job_dir": job_path,
            "part": None,
            "refs": {},
            "undo_stack": [],
        }
        for index, operation in enumerate(plan["operations"]):
            tool = operation["tool"]
            mutation_mark = None
            mutation_snapshot = None
            if tool in MODEL_MUTATIONS:
                mutation_snapshot = {"refs": _snapshot_refs(state["refs"])}
                mutation_mark = session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Visible,
                    "NX high-level: " + tool,
                )
            output = _execute_operation(session, state, operation)
            if mutation_mark is not None:
                state["undo_stack"].append(
                    {
                        "mark": mutation_mark,
                        "snapshot": mutation_snapshot,
                        "tool": tool,
                    }
                )
            result["steps"].append(
                {"index": index, "tool": tool, "ok": True, "output": output}
            )
            if tool in {"nx_create_part", "nx_open_part"}:
                # Changing the display part invalidates an undo mark created in
                # the previous part. The atomic model mark therefore begins
                # immediately after the unique run-local part/copy is active.
                plan_mark = session.SetUndoMark(
                    NXOpen.Session.MarkVisibility.Visible, "NX high-level plan"
                )
            elif tool == "nx_close_part":
                # Closing the active run copy also invalidates its model marks.
                # A following status remains valid, but rollback must not try to
                # use a mark that belongs to the now-closed part.
                plan_mark = None
        result["ok"] = True
        result["active_part"] = _part_summary(session.Parts.Work)
    except Exception as error:
        rollback = {
            "scope": "model operations after run-local part creation/open",
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
