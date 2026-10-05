import asyncio
import json
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse


SERVER_PATH = Path(__file__).resolve()
LOG_PATH = SERVER_PATH.with_name("local_research_mcp.stderr.log")


def debug(message: str) -> None:

    try:
        with LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(message.rstrip() + "\n")
    except Exception:
        pass

    try:
        print(message, file=sys.stderr, flush=True)
    except Exception:
        pass


def debug_exception(prefix: str, exc: BaseException) -> None:

    debug(prefix)

    debug(
        "".join(
            traceback.format_exception(
                type(exc),
                exc,
                exc.__traceback__,
            )
        )
    )


debug("")
debug("=" * 60)
debug("AURA LOCAL RESEARCH MCP START")
debug("=" * 60)
debug(f"Python executable: {sys.executable}")
debug(f"Python version: {sys.version}")
debug(f"Server path: {SERVER_PATH}")
debug(f"Log path: {LOG_PATH}")


# ============================================================
# IMPORTS
# ============================================================

try:

    debug("Importing MCP low-level API...")

    import httpx
    import mcp
    import mcp.types as types
    import mcp.server.stdio

    from mcp.server import (
        Server,
        ServerRequestContext,
    )

    debug("MCP low-level imports: OK")
    debug(f"mcp module: {mcp.__file__}")
    debug(
        "mcp version: "
        f"{getattr(mcp, '__version__', 'unknown')}"
    )
    debug(f"httpx version: {httpx.__version__}")

except BaseException as exc:

    debug_exception(
        "FATAL: MCP import failed",
        exc,
    )

    raise


# ============================================================
# SEARCH
# ============================================================
def normalize_result_url(href: str) -> str:

    href = str(href or "").strip()

    if not href:
        return ""

    parsed = urlparse(href)

    query = parse_qs(
        parsed.query,
        keep_blank_values=True,
    )

    uddg = query.get("uddg")

    if uddg and uddg[0]:
        return uddg[0].strip()

    if href.startswith("//"):
        return urljoin(
            "https://duckduckgo.com",
            href,
        )

    return href



async def perform_search(
    query: str,
    limit: int = 5,
) -> dict[str, Any]:

    query = str(query or "").strip()

    if not query:
        raise ValueError("query is required")

    limit = max(
        1,
        min(int(limit), 10),
    )

    debug(
        f"SEARCH query={query!r} "
        f"limit={limit}"
    )

    url = (
        "https://html.duckduckgo.com/html/"
        f"?q={quote_plus(query)}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/154.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        headers=headers,
    ) as client:

        response = await client.get(url)
        response.raise_for_status()

        html = response.text

    from html.parser import HTMLParser

    class SearchParser(HTMLParser):

        def __init__(self) -> None:

            super().__init__()

            self.results: list[
                dict[str, str]
            ] = []

            self._current: (
                dict[str, str] | None
            ) = None

            self._capture_title = False
            self._capture_snippet = False

        def handle_starttag(
            self,
            tag: str,
            attrs: list[
                tuple[str, str | None]
            ],
        ) -> None:

            attr = dict(attrs)

            classes = set(
                (attr.get("class") or "").split()
            )

            if (
                tag == "a"
                and "result__a" in classes
            ):

                self._current = {
                    "title": "",
                    "url": normalize_result_url(
                        attr.get("href") or ""
                    ),
                    "snippet": "",
                }

                self._capture_title = True

            elif (
                tag in {"a", "div"}
                and "result__snippet" in classes
                and self._current is not None
            ):

                self._capture_snippet = True

        def handle_endtag(
            self,
            tag: str,
        ) -> None:

            if (
                self._capture_title
                and tag == "a"
            ):

                self._capture_title = False

            if (
                self._capture_snippet
                and tag in {"a", "div"}
            ):

                self._capture_snippet = False

                if self._current is not None:

                    self.results.append(
                        self._current
                    )

                    self._current = None

        def handle_data(
            self,
            data: str,
        ) -> None:

            if self._current is None:
                return

            value = " ".join(
                data.split()
            )

            if not value:
                return

            if self._capture_title:

                self._current["title"] += value

            elif self._capture_snippet:

                self._current[
                    "snippet"
                ] += value

    parser = SearchParser()

    parser.feed(html)

    results = parser.results[:limit]

    debug(
        f"SEARCH results={len(results)}"
    )

    return {
        "query": query,
        "results": results,
        "count": len(results),
    }


# ============================================================
# FETCH
# ============================================================

async def perform_fetch(
    url: str,
) -> dict[str, Any]:

    url = str(url or "").strip()

    if not url:
        raise ValueError(
            "url is required"
        )

    debug(
        f"FETCH url={url!r}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/154.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers=headers,
    ) as client:

        response = await client.get(url)

        response.raise_for_status()

        content_type = (
            response.headers.get(
                "content-type",
                "",
            )
        )

        text = response.text

    max_chars = 50000

    if len(text) > max_chars:
        text = text[:max_chars]

    debug(
        f"FETCH status={response.status_code} "
        f"content_type={content_type!r} "
        f"chars={len(text)}"
    )

    return {
        "url": str(response.url),
        "status_code": response.status_code,
        "content_type": content_type,
        "content": text,
    }


# ============================================================
# TOOL LIST
# ============================================================

async def handle_list_tools(
    ctx: ServerRequestContext,
    params: Any,
) -> types.ListToolsResult:

    return types.ListToolsResult(
        tools=[
            types.Tool(
                name="search",
                description=(
                    "Search the public web "
                    "using the local AURA "
                    "research provider."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search query"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": (
                                "Maximum results "
                                "(1-10)"
                            ),
                            "minimum": 1,
                            "maximum": 10,
                            "default": 5,
                        },
                    },
                    "required": [
                        "query"
                    ],
                },
            ),
            types.Tool(
                name="fetch",
                description=(
                    "Fetch a public "
                    "HTTP/HTTPS URL."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": (
                                "HTTP or HTTPS URL"
                            ),
                        },
                    },
                    "required": [
                        "url"
                    ],
                },
            ),
        ]
    )


# ============================================================
# TOOL CALL
# ============================================================

async def handle_call_tool(
    ctx: ServerRequestContext,
    params: types.CallToolRequestParams,
) -> types.CallToolResult:

    name = params.name

    arguments = (
        params.arguments or {}
    )

    debug(
        "CALL "
        f"name={name!r} "
        f"arguments="
        f"{json.dumps(arguments, ensure_ascii=False)}"
    )

    try:

        if name == "search":

            result = await perform_search(
                query=str(
                    arguments.get(
                        "query",
                        "",
                    )
                ),
                limit=int(
                    arguments.get(
                        "limit",
                        5,
                    )
                ),
            )

        elif name == "fetch":

            result = await perform_fetch(
                url=str(
                    arguments.get(
                        "url",
                        "",
                    )
                ),
            )

        else:

            raise ValueError(
                f"Unknown tool: {name}"
            )

        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        result,
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
            ],
            structuredContent=result,
            isError=False,
        )

    except Exception as exc:

        debug_exception(
            f"TOOL ERROR name={name!r}",
            exc,
        )

        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=(
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                )
            ],
            isError=True,
        )


# ============================================================
# SERVER
# ============================================================

server = Server(
    "aura-local-research",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
)


# ============================================================
# STDIO
# ============================================================

async def main() -> None:

    debug(
        "Starting MCP stdio transport..."
    )

    async with (
        mcp.server.stdio.stdio_server()
    ) as (
        read_stream,
        write_stream,
    ):

        debug(
            "MCP stdio streams established"
        )

        initialization_options = (
            server.create_initialization_options()
        )

        debug(
            "Starting low-level MCP server..."
        )

        await server.run(
            read_stream,
            write_stream,
            initialization_options,
        )

    debug(
        "MCP stdio transport closed"
    )


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except BaseException as exc:

        debug_exception(
            "FATAL: local_research_mcp.py crashed",
            exc,
        )

        raise
