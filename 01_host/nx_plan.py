"""Validate and execute declarative high-level plans in the visible NX session.

The public operation names intentionally follow the certified surface of
DreamEnding/NX_MCP.  Execution does not use that project's socket or batch
bridge: the plan is shipped as data to this toolkit's verified visible-session
dispatcher, and the NX-side implementation uses locally verified recipes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
import time
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from nx_remote import CODE, ROOT


MAX_OPERATIONS = 100
MAX_ABS_COORDINATE = 1_000_000.0
MAX_WAIT_SECONDS = 600
PLAN_CONTRACT_VERSION = 2
REFERENCE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")

TOOL_ARGUMENTS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "nx_status": (frozenset(), frozenset()),
    "nx_create_part": (frozenset({"path"}), frozenset({"units"})),
    "nx_open_part": (frozenset({"path"}), frozenset()),
    "nx_save_part": (frozenset(), frozenset()),
    "nx_close_part": (frozenset(), frozenset({"save"})),
    "nx_export_step": (frozenset({"path"}), frozenset()),
    "nx_list_sketches": (frozenset(), frozenset()),
    "nx_list_bodies": (frozenset(), frozenset()),
    "nx_list_features": (frozenset(), frozenset()),
    "nx_create_sketch": (frozenset(), frozenset({"plane", "name"})),
    "nx_sketch_line": (frozenset({"sketch", "start", "end"}), frozenset()),
    "nx_sketch_rectangle": (
        frozenset({"sketch", "corner1", "corner2"}),
        frozenset(),
    ),
    "nx_finish_sketch": (frozenset({"sketch"}), frozenset()),
    "nx_extrude": (frozenset({"sketch", "distance"}), frozenset({"reverse"})),
    "nx_undo": (frozenset(), frozenset()),
    "nx_fit_view": (frozenset(), frozenset()),
}

# One runtime enum feeds the MCP JSON schema from the same registry that the
# host validator enforces.  Adding an operation cannot silently update one
# surface while leaving the other stale.
CertifiedToolName = StrEnum(
    "CertifiedToolName", {name.upper(): name for name in TOOL_ARGUMENTS}
)

TOOLS_REQUIRING_ID = frozenset({"nx_create_sketch"})
TOOLS_ALLOWING_ID = frozenset({"nx_create_part", "nx_create_sketch", "nx_extrude"})
MODEL_MUTATIONS = frozenset(
    {
        "nx_create_sketch",
        "nx_sketch_line",
        "nx_sketch_rectangle",
        "nx_finish_sketch",
        "nx_extrude",
    }
)
TERMINAL_OPERATIONS = frozenset(
    {"nx_save_part", "nx_close_part", "nx_export_step"}
)


class PlanValidationError(ValueError):
    """The declarative plan is invalid and must not be uploaded."""


def _fail(index: int, message: str) -> None:
    raise PlanValidationError(f"operations[{index}]: {message}")


def _number(value: Any, index: int, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(index, f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        _fail(index, f"{field} must be finite")
    if positive and result <= 0:
        _fail(index, f"{field} must be greater than zero")
    if abs(result) > MAX_ABS_COORDINATE:
        _fail(index, f"{field} exceeds the {MAX_ABS_COORDINATE:g} safety limit")
    return result


def _point(value: Any, index: int, field: str) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        _fail(index, f"{field} must contain exactly numeric x and y fields")
    return {
        "x": _number(value["x"], index, f"{field}.x"),
        "y": _number(value["y"], index, f"{field}.y"),
    }


def _reference(value: Any, index: int, field: str, known: set[str]) -> str:
    if not isinstance(value, str) or not REFERENCE_RE.fullmatch(value):
        _fail(index, f"{field} must be a previously declared operation id")
    if value not in known:
        _fail(index, f"{field} references unknown id {value!r}")
    return value


def _safe_relative_path(
    value: Any, index: int, *, suffixes: frozenset[str], purpose: str
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 240
        or "\\" in value
        or ":" in value
    ):
        _fail(index, f"{purpose} path must be a non-empty relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() not in suffixes:
        endings = "/".join(sorted(suffixes))
        _fail(index, f"{purpose} path must stay inside its workspace and end in {endings}")
    if any(part in {"", "."} for part in path.parts):
        _fail(index, f"{purpose} path contains an empty or dot component")
    return str(path)


def _safe_part_path(value: Any, index: int, *, purpose: str) -> str:
    return _safe_relative_path(
        value, index, suffixes=frozenset({".prt"}), purpose=purpose
    )


def _safe_step_path(value: Any, index: int) -> str:
    return _safe_relative_path(
        value, index, suffixes=frozenset({".step", ".stp"}), purpose="STEP output"
    )


def validate_plan(plan: Any) -> dict[str, Any]:
    """Return a normalized plan or raise before any remote side effect."""
    if not isinstance(plan, dict) or set(plan) != {"operations"}:
        raise PlanValidationError("plan must contain exactly one field: operations")
    operations = plan["operations"]
    if not isinstance(operations, list) or not 1 <= len(operations) <= MAX_OPERATIONS:
        raise PlanValidationError(f"operations must contain 1..{MAX_OPERATIONS} entries")

    normalized: list[dict[str, Any]] = []
    known_ids: set[str] = set()
    sketch_ids: set[str] = set()
    finished_sketches: set[str] = set()
    part_root: str | None = None
    terminal_operation: str | None = None
    mutation_history: list[tuple[set[str], set[str], set[str]]] = []

    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            _fail(index, "operation must be an object")
        extra_fields = set(operation) - {"tool", "id", "args"}
        if extra_fields:
            _fail(index, f"unknown operation fields: {sorted(extra_fields)}")
        tool = operation.get("tool")
        if tool not in TOOL_ARGUMENTS:
            _fail(index, f"unsupported tool {tool!r}")
        if terminal_operation is not None and tool != "nx_status":
            _fail(
                index,
                f"only nx_status may follow terminal operation {terminal_operation}",
            )
        args = operation.get("args", {})
        if not isinstance(args, dict):
            _fail(index, "args must be an object")
        required, optional = TOOL_ARGUMENTS[tool]
        missing = required - set(args)
        extra = set(args) - required - optional
        if missing:
            _fail(index, f"missing arguments: {sorted(missing)}")
        if extra:
            _fail(index, f"unknown arguments for {tool}: {sorted(extra)}")

        operation_id = operation.get("id")
        if tool in TOOLS_REQUIRING_ID and operation_id is None:
            _fail(index, f"{tool} requires an id for later references")
        if operation_id is not None:
            if tool not in TOOLS_ALLOWING_ID:
                _fail(index, f"{tool} does not produce a referenceable object")
            if not isinstance(operation_id, str) or not REFERENCE_RE.fullmatch(operation_id):
                _fail(index, "id must match [A-Za-z][A-Za-z0-9_-]{0,63}")
            if operation_id in known_ids:
                _fail(index, f"duplicate id {operation_id!r}")

        values: dict[str, Any] = dict(args)
        if tool in {"nx_create_part", "nx_open_part"}:
            if part_root is not None:
                _fail(index, "only one nx_create_part or nx_open_part is allowed per plan")
            if any(item["tool"] != "nx_status" for item in normalized):
                _fail(index, f"{tool} must be the first non-status operation")
            purpose = "new part" if tool == "nx_create_part" else "input part"
            path = _safe_part_path(args["path"], index, purpose=purpose)
            values = {"path": path}
            units = args.get("units", "mm")
            if tool == "nx_create_part":
                if units not in {"mm", "inch"}:
                    _fail(index, "units must be 'mm' or 'inch'")
                values["units"] = units
            part_root = tool
        elif tool != "nx_status" and part_root is None:
            _fail(index, "operation requires nx_create_part or nx_open_part first")

        if tool in MODEL_MUTATIONS:
            mutation_history.append(
                (known_ids.copy(), sketch_ids.copy(), finished_sketches.copy())
            )

        if tool == "nx_create_sketch":
            plane = args.get("plane", "XZ")
            if plane != "XZ":
                _fail(index, "only the locally verified XZ plane is certified")
            name = args.get("name", operation_id)
            if not isinstance(name, str) or not name or len(name) > 80:
                _fail(index, "name must be a non-empty string of at most 80 characters")
            values = {"plane": plane, "name": name}
        elif tool in {"nx_sketch_line", "nx_sketch_rectangle"}:
            sketch = _reference(args["sketch"], index, "sketch", sketch_ids)
            if sketch in finished_sketches:
                _fail(index, f"sketch {sketch!r} was already finished")
            if tool == "nx_sketch_line":
                values = {
                    "sketch": sketch,
                    "start": _point(args["start"], index, "start"),
                    "end": _point(args["end"], index, "end"),
                }
                if values["start"] == values["end"]:
                    _fail(index, "line start and end must differ")
            else:
                values = {
                    "sketch": sketch,
                    "corner1": _point(args["corner1"], index, "corner1"),
                    "corner2": _point(args["corner2"], index, "corner2"),
                }
                if (
                    values["corner1"]["x"] == values["corner2"]["x"]
                    or values["corner1"]["y"] == values["corner2"]["y"]
                ):
                    _fail(index, "rectangle width and height must be non-zero")
        elif tool == "nx_finish_sketch":
            sketch = _reference(args["sketch"], index, "sketch", sketch_ids)
            if sketch in finished_sketches:
                _fail(index, f"sketch {sketch!r} was already finished")
            values = {"sketch": sketch}
            finished_sketches.add(sketch)
        elif tool == "nx_extrude":
            sketch = _reference(args["sketch"], index, "sketch", sketch_ids)
            if sketch not in finished_sketches:
                _fail(index, f"sketch {sketch!r} must be finished before extrusion")
            reverse = args.get("reverse", False)
            if not isinstance(reverse, bool):
                _fail(index, "reverse must be a boolean")
            values = {
                "sketch": sketch,
                "distance": _number(args["distance"], index, "distance", positive=True),
                "reverse": reverse,
            }
        elif tool == "nx_close_part":
            save = args.get("save", True)
            if not isinstance(save, bool):
                _fail(index, "save must be a boolean")
            values = {"save": save}
        elif tool == "nx_export_step":
            values = {"path": _safe_step_path(args["path"], index)}
        elif tool == "nx_undo":
            if not mutation_history:
                _fail(index, "no preceding model mutation is available to undo")
            known_ids, sketch_ids, finished_sketches = mutation_history.pop()
            values = {}

        if tool in TERMINAL_OPERATIONS:
            terminal_operation = tool

        item: dict[str, Any] = {"tool": tool, "args": values}
        if operation_id is not None:
            item["id"] = operation_id
            known_ids.add(operation_id)
            if tool == "nx_create_sketch":
                sketch_ids.add(operation_id)
        normalized.append(item)

    return {"contract_version": PLAN_CONTRACT_VERSION, "operations": normalized}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=CODE,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return json.loads(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Could not decode {path}")


def _transport_failure(message: str, *, run_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "error": {"layer": "transport", "message": message},
    }
    if run_id is not None:
        result["run_id"] = run_id
        result["evidence_dir"] = str(ROOT / "runs" / "nx" / run_id)
    return result


def execute_plan(plan: Any, wait_seconds: int = 90) -> dict[str, Any]:
    """Execute one validated plan exactly once and return structured evidence."""
    normalized = validate_plan(plan)
    if (
        not isinstance(wait_seconds, int)
        or isinstance(wait_seconds, bool)
        or not 1 <= wait_seconds <= MAX_WAIT_SECONDS
    ):
        raise PlanValidationError(
            f"wait_seconds must be an integer from 1 through {MAX_WAIT_SECONDS}"
        )

    input_paths: list[Path] = []
    root = ROOT.resolve()
    for operation in normalized["operations"]:
        if operation["tool"] != "nx_open_part":
            continue
        relative = PurePosixPath(operation["args"]["path"])
        source = root.joinpath(*relative.parts).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise PlanValidationError(
                f"input part does not exist below NX_PROJECT_ROOT: {relative}"
            )
        operation["args"]["requested_path"] = operation["args"]["path"]
        operation["args"]["path"] = source.relative_to(root).as_posix()
        operation["args"]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        input_paths.append(source)

    status_process = _run([sys.executable, str(CODE / "01_host" / "nx_dispatch.py"), "status"])
    if status_process.returncode != 0:
        return _transport_failure(status_process.stderr.strip() or "Bridge status failed")
    try:
        bridge = json.loads(status_process.stdout)
    except json.JSONDecodeError:
        return _transport_failure("Bridge status returned invalid JSON")
    try:
        heartbeat_fresh = abs(time.time() - float(bridge.get("heartbeat", 0))) <= 60
    except (TypeError, ValueError):
        heartbeat_fresh = False
    if bridge.get("state") != "ready" or bridge.get("session_id") == 0 or not heartbeat_fresh:
        return _transport_failure("Visible NX bridge is not ready with a fresh heartbeat")

    parameters_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="nx-plan-", encoding="utf-8", delete=False
        ) as parameters:
            json.dump(normalized, parameters, ensure_ascii=False, indent=2)
            parameters_path = Path(parameters.name)
        prepare_command = [
            sys.executable,
            str(CODE / "01_host" / "nx_remote.py"),
            "nx_high_level_plan.py",
            "--toolkit-job",
            "--parameters",
            str(parameters_path),
            "--prepare-only",
        ]
        for source in input_paths:
            prepare_command.extend(["--input", str(source.relative_to(root))])
        prepare = _run(prepare_command)
    finally:
        if parameters_path is not None:
            parameters_path.unlink(missing_ok=True)
    if prepare.returncode != 0:
        return _transport_failure(prepare.stderr.strip() or prepare.stdout.strip())

    run_line = next((line for line in prepare.stdout.splitlines() if line.startswith("Run:")), "")
    if not run_line:
        return _transport_failure("Prepare completed without a run id")
    run_id = Path(run_line.removeprefix("Run:").strip()).name
    run_dir = ROOT / "runs" / "nx" / run_id

    submit = _run(
        [
            sys.executable,
            str(CODE / "01_host" / "nx_dispatch.py"),
            "submit",
            "--run",
            run_id,
            "--wait",
            str(wait_seconds),
        ]
    )
    report_path = run_dir / "remote" / "result.json"
    if not report_path.exists():
        _run(
            [
                sys.executable,
                str(CODE / "01_host" / "nx_visible.py"),
                "collect",
                "--run",
                run_id,
            ]
        )
    if not report_path.exists():
        message = submit.stderr.strip() or submit.stdout.strip() or "Plan produced no result.json"
        return _transport_failure(message, run_id=run_id)

    result = _read_json(report_path)
    execution_path = run_dir / "remote" / "bridge-execution.json"
    execution = _read_json(execution_path) if execution_path.exists() else None
    execution_ok = execution is not None and execution.get("execution_ok") is True
    return {
        "ok": result.get("ok") is True and execution_ok,
        "run_id": run_id,
        "evidence_dir": str(run_dir),
        "bridge_execution": execution,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="JSON file containing an operations list")
    parser.add_argument("--wait", type=int, default=90)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        if args.validate_only:
            result: dict[str, Any] = {"ok": True, "plan": validate_plan(plan)}
        else:
            result = execute_plan(plan, args.wait)
    except (OSError, json.JSONDecodeError, PlanValidationError) as error:
        result = {"ok": False, "error": {"layer": "validation", "message": str(error)}}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
