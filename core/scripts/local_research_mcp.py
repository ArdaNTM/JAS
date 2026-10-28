import asyncio
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse
import urllib.request


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

    url = "https://lite.duckduckgo.com/lite/"
    searxng_url = (
        os.getenv("AURA_SEARXNG_URL", "http://127.0.0.1:8080")
        .rstrip("/")
        + "/search"
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
        try:
            response = await client.get(
                searxng_url,
                params={"q": query, "format": "json", "language": "auto"},
            )
            response.raise_for_status()
            payload = response.json()
            candidates = [
                {
                    "title": str(item.get("title", "")),
                    "url": str(item.get("url", "")),
                    "snippet": str(item.get("content", "")),
                    "source": "searxng",
                }
                for item in payload.get("results", [])
            ]
            return rank_results(query, candidates, limit, "searxng")
        except (httpx.HTTPError, ValueError) as exc:
            debug(f"SEARXNG unavailable; using DuckDuckGo fallback: {exc}")

        try:
            response = await client.get(url, params={"q": query})
            response.raise_for_status()
            html = response.text
        except httpx.HTTPError as exc:
            debug(f"DuckDuckGo fallback failed: {exc}")
            return rank_results(query, [], limit, "unavailable")

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
                and classes.intersection({"result__a", "result-link"})
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
                tag in {"a", "div", "td"}
                and classes.intersection({"result__snippet", "result-snippet"})
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
                and tag in {"a", "div", "td"}
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

    return rank_results(
        query,
        [{**item, "source": "duckduckgo_fallback"} for item in parser.results],
        limit,
        "duckduckgo_fallback",
    )


def rank_results(
    query: str,
    candidates: list[dict[str, str]],
    limit: int,
    backend: str,
) -> dict[str, Any]:
    """Stable URL de-duplication, deterministic scoring, then lexical tie-break."""
    unique: dict[str, dict[str, str]] = {}
    for item in candidates:
        url = normalize_result_url(item.get("url", ""))
        if url and url not in unique:
            unique[url] = {**item, "url": url}
    terms = {term.lower() for term in query.split() if len(term) > 2}

    def ranking(item: dict[str, str]) -> tuple[int, str, str]:
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        return (-sum(term in haystack for term in terms), item["url"], item.get("title", ""))

    results = []
    for rank, item in enumerate(sorted(unique.values(), key=ranking)[:limit], start=1):
        item["rank"] = rank
        item["content_hash"] = hashlib.sha256(item["url"].encode("utf-8")).hexdigest()[:16]
        results.append(item)
    debug(f"SEARCH backend={backend} results={len(results)}")
    return {"query": query, "results": results, "count": len(results), "backend": backend}


# ============================================================
# FETCH
# ============================================================

def _fetch_with_urllib(
    url: str,
    headers: dict[str, str],
) -> tuple[str, int, str, str]:
    """Fallback for servers whose HTTP framing httpx/httpcore rejects.

    Keep the fallback narrowly scoped to RemoteProtocolError; ordinary HTTP
    status errors and other transport failures should retain their normal
    error behavior.
    """
    request = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(request, timeout=30.0) as response:
        raw_content = response.read()
        response_headers = response.headers
        content_type = response_headers.get("content-type", "")
        get_charset = getattr(response_headers, "get_content_charset", None)
        charset = get_charset() if callable(get_charset) else None
        text = raw_content.decode(charset or "utf-8", errors="replace")
        return (
            str(response.geturl()),
            int(response.status),
            content_type,
            text,
        )


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

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            text = response.text
            final_url = str(response.url)
            status_code = response.status_code
    except httpx.RemoteProtocolError as exc:
        debug(
            "FETCH httpx protocol error; retrying with urllib fallback: "
            f"{exc}"
        )
        final_url, status_code, content_type, text = await asyncio.to_thread(
            _fetch_with_urllib,
            url,
            headers,
        )

    max_chars = 50000

    if len(text) > max_chars:
        text = text[:max_chars]

    debug(
        f"FETCH status={status_code} "
        f"content_type={content_type!r} "
        f"chars={len(text)}"
    )

    return {
        "url": final_url,
        "status_code": status_code,
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
