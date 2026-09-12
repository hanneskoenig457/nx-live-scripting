from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "01_host"))

import nx_plan  # noqa: E402
import nx_mcp_server  # noqa: E402


def box_plan() -> dict:
    return {
        "operations": [
            {
                "tool": "nx_create_part",
                "id": "part",
                "args": {"path": "high-level-box.prt", "units": "mm"},
            },
            {
                "tool": "nx_create_sketch",
                "id": "profile",
                "args": {"plane": "XZ", "name": "BOX_PROFILE"},
            },
            {
                "tool": "nx_sketch_rectangle",
                "args": {
                    "sketch": "profile",
                    "corner1": {"x": 0, "y": 0},
                    "corner2": {"x": 30, "y": 20},
                },
            },
            {"tool": "nx_finish_sketch", "args": {"sketch": "profile"}},
            {
                "tool": "nx_extrude",
                "id": "solid",
                "args": {"sketch": "profile", "distance": 10},
            },
            {"tool": "nx_list_bodies"},
            {"tool": "nx_fit_view"},
            {"tool": "nx_save_part"},
        ]
    }


class PlanValidationTests(unittest.TestCase):
    def test_normalizes_certified_box_plan(self):
        normalized = nx_plan.validate_plan(box_plan())
        self.assertEqual(normalized["contract_version"], nx_plan.PLAN_CONTRACT_VERSION)
        extrusion = normalized["operations"][4]
        self.assertEqual(extrusion["args"]["distance"], 10.0)
        self.assertIs(extrusion["args"]["reverse"], False)

    def test_rejects_path_escape_before_upload(self):
        plan = box_plan()
        plan["operations"][0]["args"]["path"] = "../outside.prt"
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "run directory"):
            nx_plan.validate_plan(plan)

    def test_rejects_unknown_tool_and_arguments(self):
        plan = box_plan()
        plan["operations"][1]["tool"] = "nx_run_journal"
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "unsupported tool"):
            nx_plan.validate_plan(plan)

        plan = box_plan()
        plan["operations"][4]["args"]["python"] = "arbitrary code"
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "unknown arguments"):
            nx_plan.validate_plan(plan)

    def test_requires_finished_known_sketch(self):
        plan = box_plan()
        del plan["operations"][3]
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "must be finished"):
            nx_plan.validate_plan(plan)

        plan = box_plan()
        plan["operations"][2]["args"]["sketch"] = "missing"
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "unknown id"):
            nx_plan.validate_plan(plan)

    def test_rejects_non_certified_plane(self):
        plan = box_plan()
        plan["operations"][1]["args"]["plane"] = "XY"
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "only.*XZ"):
            nx_plan.validate_plan(plan)

    def test_requires_save_to_be_last(self):
        plan = box_plan()
        plan["operations"].append({"tool": "nx_list_features"})
        with self.assertRaisesRegex(nx_plan.PlanValidationError, "final operation"):
            nx_plan.validate_plan(plan)


class PlanExecutionTests(unittest.TestCase):
    def test_orchestrates_status_prepare_single_submit_and_reads_both_evidence_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            run_id = "20260912T120000Z-test"
            remote = project / "runs" / "nx" / run_id / "remote"
            remote.mkdir(parents=True)
            (remote / "result.json").write_text(
                json.dumps({"ok": True, "steps": [{"tool": "nx_create_part", "ok": True}]}),
                encoding="utf-8",
            )
            (remote / "bridge-execution.json").write_text(
                json.dumps({"execution_ok": True, "sha256_ok": True}), encoding="utf-8"
            )
            commands: list[list[str]] = []

            def fake_run(command: list[str]) -> subprocess.CompletedProcess[str]:
                commands.append(command)
                if command[-1] == "status":
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        json.dumps(
                            {
                                "state": "ready",
                                "session_id": 1,
                                "heartbeat": time.time(),
                            }
                        ),
                        "",
                    )
                if "nx_remote.py" in command[1]:
                    return subprocess.CompletedProcess(
                        command, 0, f"Run: {project / 'runs' / 'nx' / run_id}\n", ""
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(nx_plan, "ROOT", project), patch.object(
                nx_plan, "_run", side_effect=fake_run
            ):
                result = nx_plan.execute_plan(box_plan(), 15)

            self.assertTrue(result["ok"])
            self.assertEqual(result["run_id"], run_id)
            submits = [command for command in commands if "submit" in command]
            self.assertEqual(len(submits), 1)
            prepares = [command for command in commands if "nx_remote.py" in command[1]]
            self.assertEqual(len(prepares), 1)
            self.assertIn("--toolkit-job", prepares[0])
            self.assertEqual(result["result"]["steps"][0]["tool"], "nx_create_part")
            self.assertTrue(result["bridge_execution"]["sha256_ok"])

    def test_stops_before_prepare_when_visible_bridge_is_not_ready(self):
        status = subprocess.CompletedProcess(
            ["status"],
            0,
            json.dumps({"state": "ready", "session_id": 0, "heartbeat": time.time()}),
            "",
        )
        with patch.object(nx_plan, "_run", return_value=status) as runner:
            result = nx_plan.execute_plan(box_plan())
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["layer"], "transport")
        runner.assert_called_once()


class MCPServerTests(unittest.TestCase):
    def test_exposes_one_high_level_tool(self):
        tools = asyncio.run(nx_mcp_server.mcp.list_tools())
        self.assertEqual([tool.name for tool in tools], ["nx_run_plan"])
        self.assertEqual(
            set(tools[0].inputSchema["properties"]), {"operations", "wait_seconds"}
        )
        operation_schema = tools[0].inputSchema["$defs"]["PlanOperation"]
        self.assertEqual(
            set(
                tools[0].inputSchema["$defs"]["CertifiedToolName"]["enum"]
            ),
            set(nx_plan.TOOL_ARGUMENTS),
        )
        self.assertEqual(
            operation_schema["properties"]["tool"]["$ref"],
            "#/$defs/CertifiedToolName",
        )
        self.assertFalse(tools[0].annotations.readOnlyHint)
        self.assertTrue(tools[0].annotations.destructiveHint)


if __name__ == "__main__":
    unittest.main()
