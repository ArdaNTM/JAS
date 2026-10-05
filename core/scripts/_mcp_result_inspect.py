import asyncio
from mcp.client.stdio import StdioServerParameters
from aura_core.mcp.connection import MCPConnection

async def main():
    server = StdioServerParameters(
        command="uv",
        args=[
            "run",
            "python",
            r"D:\AURA\JAS\core\scripts\local_research_mcp.py",
        ],
    )

    connection = MCPConnection()

    try:
        await connection.connect_stdio(server)

        result = await connection.session.call_tool(
            "search",
            {"query": "Model Context Protocol"},
        )

        print("=== RESULT TYPE ===")
        print(type(result))

        print("=== RESULT REPR ===")
        print(repr(result))

        print("=== RESULT ATTRIBUTES ===")
        print(sorted(a for a in dir(result) if not a.startswith("_")))

        print("=== STRUCTURED CONTENT ===")
        print(repr(getattr(result, "structured_content", None)))

        print("=== CONTENT ===")
        print(repr(getattr(result, "content", None)))

        print("=== IS ERROR ===")
        print(repr(getattr(result, "is_error", None)))

    finally:
        await connection.close()

asyncio.run(main())
