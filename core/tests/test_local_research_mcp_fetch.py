import asyncio
import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "local_research_mcp.py"
SPEC = importlib.util.spec_from_file_location("local_research_mcp_under_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
research_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research_mcp)


class BrokenHttpxClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url):
        raise research_mcp.httpx.RemoteProtocolError(
            "multiple Transfer-Encoding headers"
        )


class ResponseHeaders(dict):
    def get_content_charset(self):
        return "utf-8"


class FallbackResponse:
    status = 200
    headers = ResponseHeaders({"content-type": "text/html; charset=utf-8"})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b"<html>fallback body</html>"

    def geturl(self):
        return "https://example.test/article"


def test_fetch_falls_back_when_httpx_rejects_transfer_encoding(monkeypatch):
    requested = {}

    def fake_urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        requested["user_agent"] = request.get_header("User-agent")
        return FallbackResponse()

    monkeypatch.setattr(
        research_mcp.httpx,
        "AsyncClient",
        lambda **kwargs: BrokenHttpxClient(),
    )
    monkeypatch.setattr(research_mcp.urllib.request, "urlopen", fake_urlopen)

    result = asyncio.run(research_mcp.perform_fetch("https://example.test/article"))

    assert result == {
        "url": "https://example.test/article",
        "status_code": 200,
        "content_type": "text/html; charset=utf-8",
        "content": "<html>fallback body</html>",
    }
    assert requested["url"] == "https://example.test/article"
    assert requested["timeout"] == 30.0
    assert requested["user_agent"]
