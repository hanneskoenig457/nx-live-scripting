"""One-tool MCP facade for safe high-level plans in the visible NX session."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from nx_plan import CertifiedToolName, PLAN_CONTRACT_VERSION, TOOL_ARGUMENTS, execute_plan


mcp = FastMCP(
    "nx-live-scripting",
    instructions=(
        "Run short declarative NX plans through the visible main-thread dispatcher. "
        "Use only the certified operation names returned by nx_run_plan."
    ),
)


class PlanOperation(BaseModel):
    """A code-free operation in one atomic high-level plan."""

    model_config = ConfigDict(extra="forbid")

    tool: CertifiedToolName
    id: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)


@mcp.tool(
    title="Run an atomic Siemens NX plan",
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def nx_run_plan(
    operations: list[PlanOperation], wait_seconds: int = 90
) -> dict[str, Any]:
    """Execute an atomic high-level NX plan.

    Every operation has ``tool``, optional ``id``, and optional ``args``.
    The 16 certified operation names are nx_status, nx_create_part,
    nx_open_part, nx_save_part, nx_close_part, nx_export_step,
    nx_list_sketches, nx_list_bodies, nx_list_features, nx_create_sketch,
    nx_sketch_line, nx_sketch_rectangle, nx_finish_sketch, nx_extrude,
    nx_undo, and nx_fit_view. A stateful plan starts with nx_create_part or
    nx_open_part; status-only plans are allowed. An opened input is copied from
    the project into immutable run evidence before NX touches it. Paths are
    relative to the project/run workspace. nx_create_sketch needs an id; later
    sketch operations refer to it through args.sketch. nx_undo reverses the
    last model mutation in the same plan. Save, close, and STEP export are
    terminal except for a following nx_status. Currently only the locally
    verified XZ sketch plane is accepted. Unknown fields and arbitrary code are
    rejected before upload. A failed NX step rolls model operations after the
    run-local part was created or opened back when the NX undo boundary remains
    valid.
    """
    raw_operations = [
        operation.model_dump(mode="json", exclude_none=True) for operation in operations
    ]
    result = await asyncio.to_thread(
        execute_plan, {"operations": raw_operations}, wait_seconds
    )
    result["contract_version"] = PLAN_CONTRACT_VERSION
    result["certified_tools"] = sorted(TOOL_ARGUMENTS)
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
