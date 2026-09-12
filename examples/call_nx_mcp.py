"""Call nx_run_plan through a real MCP stdio client/server round trip."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[1]


async def call(plan_path: Path, wait_seconds: int):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "01_host" / "nx_mcp_server.py")],
        cwd=ROOT,
    )
    timeout = timedelta(seconds=wait_seconds + 30)
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, write_stream, read_timeout_seconds=timeout
        ) as session:
            await session.initialize()
            tools = await session.list_tools()
            if [tool.name for tool in tools.tools] != ["nx_run_plan"]:
                raise RuntimeError("MCP server did not expose exactly nx_run_plan")
            return await session.call_tool(
                "nx_run_plan",
                {"operations": plan["operations"], "wait_seconds": wait_seconds},
                read_timeout_seconds=timeout,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--wait", type=int, default=90)
    args = parser.parse_args()
    result = asyncio.run(call(args.plan, args.wait))
    print(result.model_dump_json(indent=2, exclude_none=True))
    structured = result.structuredContent or {}
    return 0 if not result.isError and structured.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
