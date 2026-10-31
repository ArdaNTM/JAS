"""Gateway-governed, opt-in search for licensed Wikimedia Commons image assets.

Queries are sent to Wikimedia *only when a local user explicitly requests
an image*. No ScreenRead input, screenshots, secret or memory is forwarded.
"""
from __future__ import annotations

from html import unescape
import re
from urllib.parse import urlsplit

import httpx

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool


def _plain(value: object, maximum: int = 140) -> str:
    raw = value.get("value", "") if isinstance(value, dict) else value
    return unescape(re.sub(r"<[^>]+>", "", raw if isinstance(raw, str) else ""))[:maximum]


def _trusted_image(url: object, domain: str) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != domain or parsed.username or parsed.password:
        return None
    return url if len(url) <= 1800 else None


class WikimediaMediaMCPProvider:
    provider_id = "aura.hud-media"

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool("hud_media_search",
            "Search Commons file metadata for a voluntarily requested image",
            {"type": "object",
             "properties": {"query": {"type": "string", "minLength": 2, "maxLength": 100}},
             "required": ["query"], "additionalProperties": False}),)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        grant = current_dispatch()
        if name != "hud_media_search" or grant is None or grant.capability_id != "HUDMediaSearch" or grant.tool_name != name:
            raise PermissionError("Image search requires MCP Gateway authorization")
        query = (arguments or {}).get("query")
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
            raise ValueError("Invalid media query")
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "generator": "search", "gsrnamespace": "6", "gsrlimit": "5",
            "gsrsearch": query.strip(),
            "prop": "imageinfo", "iiprop": "url|mediatype|extmetadata",
            "iiurlwidth": "850",
            "iiextmetadatafilter": "LicenseShortName|Artist|Credit",
        }
        async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False,
                                     headers={"User-Agent": "AURA-HUD/0.2 (local user-initiated Commons media search)"}) as client:
            response = await client.get("https://commons.wikimedia.org/w/api.php", params=params)
            response.raise_for_status()
            data = response.json()
        results = []
        for page in data.get("query", {}).get("pages", [])[:5]:
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mediatype") != "BITMAP":
                continue
            media_url = _trusted_image(info.get("thumburl"), "upload.wikimedia.org")
            page_url = _trusted_image(info.get("descriptionurl"), "commons.wikimedia.org")
            if not media_url or not page_url:
                continue
            meta = info.get("extmetadata") or {}
            license_name = _plain(meta.get("LicenseShortName"), 80)
            # Fail closed on licensing: unknown license is not a usable source.
            if not license_name or license_name.casefold() in {"copyrighted free use", "unknown"}:
                continue
            results.append({
                "url": media_url, "page": page_url,
                "artist": _plain(meta.get("Artist"), 120),
                "license": license_name,
                "title": _plain(page.get("title"), 120),
                "source": "Wikimedia Commons",
            })
        return {"results": results[:3], "external_query": True}
