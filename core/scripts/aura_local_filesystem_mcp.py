"""AURA local read-only filesystem MCP server, limited to repository test-data."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import mcp.types as types
from mcp.server import Server
import mcp.server.stdio

# The server script lives in <repo>/core/scripts; the allowed root is <repo>/test-data.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TEST_DATA_ROOT = REPOSITORY_ROOT / "test-data"
if not TEST_DATA_ROOT.is_dir():
    print("aura-local-filesystem: required test-data directory is missing", file=sys.stderr)
    raise SystemExit(2)

# Make the source package importable when launched as a standalone stdio process.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from aura_core.filesystem.safe_reader import SafeReadError, read_test_data_file  # noqa: E402

server = Server("aura-local-filesystem")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="read_file",
            description=(
                "Read a UTF-8 text file under the repository test-data directory. "
                "Provide a relative path using forward slashes. Read-only; max 1 MiB."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Relative path under test-data, e.g. governor-read-test.txt",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "read_file":
        raise ValueError("Unknown tool")
    try:
        text = read_test_data_file(arguments.get("path"), root=TEST_DATA_ROOT)
        return [types.TextContent(type="text", text=text)]
    except SafeReadError as exc:
        return [types.TextContent(type="text", text=f"Read rejected: {exc}")]


async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
