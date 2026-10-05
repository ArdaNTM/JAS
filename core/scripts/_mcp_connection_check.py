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

        result = await connection.call_tool(
            "search",
            {"query": "Model Context Protocol"},
        )

        print("=== CONNECTION RESULT TYPE ===")
        print(type(result).__name__)

        print("=== CONNECTION RESULT ===")
        print(repr(result))

        assert isinstance(result, dict), type(result)

        results = result.get("results")
        print("=== RESULT COUNT ===")
        print(len(results) if isinstance(results, list) else "INVALID")

        assert isinstance(results, list)
        assert results

        first_url = results[0].get("url")
        print("=== FIRST URL ===")
        print(first_url)

        print("=== URL STARTS HTTP(S) ===")
        print(
            isinstance(first_url, str)
            and first_url.startswith(("http://", "https://"))
        )

    finally:
        await connection.close()

asyncio.run(main())
