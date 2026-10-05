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

        listed = await connection.list_tools()
        names = sorted(tool.name for tool in listed.tools)

        print("TOOLS:", names)
        assert names == ["fetch", "search"], names

        result = await connection.call_tool(
            "search",
            {"query": "Model Context Protocol"},
        )

        structured = getattr(result, "structured_content", None)
        print("SEARCH STRUCTURED TYPE:", type(structured).__name__)
        assert isinstance(structured, dict), structured

        results = structured.get("results")
        print(
            "SEARCH RESULT COUNT:",
            len(results) if isinstance(results, list) else "INVALID",
        )
        assert isinstance(results, list), structured
        assert results, "search returned no results"

        first_url = results[0].get("url")
        print("FIRST URL:", first_url)

        assert isinstance(first_url, str)
        assert first_url.startswith(("http://", "https://"))

        fetched = await connection.call_tool(
            "fetch",
            {"url": first_url},
        )

        fetched_structured = getattr(
            fetched,
            "structured_content",
            None,
        )

        print(
            "FETCH STRUCTURED TYPE:",
            type(fetched_structured).__name__,
        )

        assert isinstance(fetched_structured, dict), fetched
        assert str(
            fetched_structured.get("content", "")
        ).strip()

        print("LOCAL MCP STDIO SMOKE: PASS")

    finally:
        await connection.close()


asyncio.run(main())
