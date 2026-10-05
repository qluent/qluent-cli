"""Exercise MCP over real stdio, without credentials or live API access.

Usage: python scripts/mcp_smoke_test.py /path/to/qluent
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def smoke(command: str, args: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="qluent-mcp-") as home:
        # Explicit empty overrides prevent the stdio client's inherited Qluent
        # credentials from being used. A fresh home excludes the real config.
        env = {key: "" for key in os.environ if key.startswith("QLUENT_")}
        env.update(HOME=home, USERPROFILE=home)
        params = StdioServerParameters(command=command, args=args, env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=30)) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "qluent"
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert len(names) == 11, names
                assert {"qluent_compose_catalog", "qluent_compose_query", "qluent_query"} <= names
                invalid = await session.call_tool("qluent_get_tree", {})
                assert invalid.isError, invalid
                missing_config = await session.call_tool("qluent_list_trees", {})
                assert missing_config.isError, missing_config
                assert "No API key configured" in missing_config.content[0].text
                await session.send_ping()
                print(f"MCP smoke passed: {len(names)} tools, validation, setup errors, ping")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        binary = str(Path(sys.argv[1]).absolute())
        args = sys.argv[2:] or ["mcp", "serve"]
    else:
        candidates = [p for p in Path("dist/binaries").glob("qluent-*")
                      if p.suffix in ("", ".exe")]
        if len(candidates) != 1:
            raise SystemExit("Pass the binary path when dist/binaries has other than one binary")
        binary = str(candidates[0].resolve())
        args = ["mcp", "serve"]
    asyncio.run(smoke(binary, args))
