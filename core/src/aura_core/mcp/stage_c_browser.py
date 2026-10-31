"""Stage C Playwright browser adapter. Only Gateway-approved calls can reach it.

Network policy deliberately supports ONLY an explicitly allowlisted single HTTPS
origin. It blocks popups, downloads, WebSockets, Service Workers and mixed-origin
requests. DNS checks are defense in depth, NOT IP pinning: deploy a network-level
egress firewall for untrusted websites before production.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool

_ORIGIN = re.compile(r"^https://[a-z0-9][a-z0-9.-]{1,251}$")


def safe_origin(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Browser URL is invalid")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.username or parts.password or
            parts.port not in (None, 443) or not parts.hostname or
            not _ORIGIN.fullmatch(f"https://{parts.hostname}") or
            (parts.hostname in {"localhost", "localhost.localdomain"} or
             parts.hostname.endswith((".local", ".internal", ".test", ".localhost"))) or
            ".." in parts.hostname):
        raise ValueError("Browser requires a public HTTPS origin")
    try:
        ipaddress.ip_address(parts.hostname)
    except ValueError:
        pass
    else:
        raise ValueError("IP literal destinations are forbidden")
    return f"https://{parts.hostname}"


class OriginGuard:
    def __init__(self, origins: tuple[str, ...]):
        if not origins or len(origins) > 8:
            raise ValueError("Explicit bounded browser origin allowlist required")
        if any(safe_origin(o) != o for o in origins):
            raise ValueError("Origin allowlist must contain canonical HTTPS origins")
        self.origins = frozenset(origins)

    async def check(self, url: str) -> None:
        origin = safe_origin(url)
        if origin not in self.origins:
            raise PermissionError("Browser origin not allowlisted")
        host = urlsplit(url).hostname
        try:
            records = await asyncio.wait_for(
                asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM),
                timeout=3,
            )
            addresses = {item[4][0] for item in records}
            if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                raise PermissionError("Non-public DNS address")
        except (OSError, asyncio.TimeoutError) as exc:
            raise PermissionError("Browser DNS policy could not be verified") from exc


class PlaywrightSessions:
    """An ephemeral Chromium context per run; no ambient browser profile."""

    def __init__(self, guard: OriginGuard):
        self._guard = guard
        self._sessions: dict[str, tuple[object, object, object, object]] = {}

    async def _page(self, run_id: str):
        if run_id in self._sessions:
            return self._sessions[run_id][-1]
        from playwright.async_api import async_playwright
        engine = await async_playwright().start()
        try:
            browser = await engine.chromium.launch(headless=True)
            context = await browser.new_context(
                accept_downloads=False, service_workers="block",
                permissions=[], ignore_https_errors=False,
            )
            async def route_handler(route):
                # Every external request, including redirects, is constrained.
                if route.request.method not in {"GET", "HEAD"} or route.request.resource_type in {"websocket", "eventsource"}:
                    await route.abort()
                    return
                try:
                    await self._guard.check(route.request.url)
                except (PermissionError, ValueError):
                    await route.abort()
                    return
                await route.continue_()
            # HTTP routing does NOT cover WebSockets. Block them independently
            # before creating pages, preventing same-origin background sockets.
            await context.route_web_socket("**/*", lambda ws: ws.close())
            await context.route("**/*", route_handler)
            page = await context.new_page()
            page.on("popup", lambda p: asyncio.create_task(p.close()))
            page.on("download", lambda d: asyncio.create_task(d.cancel()))
            self._sessions[run_id] = (engine, browser, context, page)
            return page
        except BaseException:
            await engine.stop()
            raise

    async def perform(self, run_id: str, action: str, args: dict):
        if action == "close":
            await self.close(run_id)
            return {"closed": True}
        page = await self._page(run_id)
        if action == "navigate":
            url = args.get("url")
            await self._guard.check(url)
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            await self._guard.check(page.url)
            return {"url": page.url, "untrusted": True}
        if action in ("click", "type"):
            selector = args.get("selector")
            if not isinstance(selector, str) or not 1 <= len(selector) <= 256:
                raise ValueError("Bounded CSS selector required")
            locator = page.locator(selector)
            if await locator.count() != 1:
                raise ValueError("Selector must match exactly one element")
            if action == "click":
                await locator.click(timeout=5000)
            else:
                text = args.get("text")
                if not isinstance(text, str) or not 1 <= len(text) <= 1000:
                    raise ValueError("Bounded input required")
                await locator.fill(text, timeout=5000)
            await self._guard.check(page.url)
            return {"executed": True, "action": action}
        if action == "read":
            await self._guard.check(page.url)
            return {"untrusted": True, "url": page.url,
                    "text": (await page.locator("body").inner_text(timeout=5000))[:6000]}
        raise ValueError("Unsupported browser action")

    async def close(self, run_id: str) -> None:
        entry = self._sessions.pop(run_id, None)
        if entry:
            engine, browser, context, _ = entry
            try:
                await context.close()
                await browser.close()
            finally:
                await engine.stop()

    async def close_all(self) -> None:
        for run_id in tuple(self._sessions):
            await self.close(run_id)


class BrowserControlMCPProvider:
    provider_id = "aura.stage-c.browser-control"
    requires_approval = True

    def __init__(self, sessions: PlaywrightSessions):
        self.sessions = sessions

    async def list_tools(self):
        return (MCPTool("browser_action", "One approved, bounded browser action", {
            "type": "object", "additionalProperties": False,
            "properties": {
                "run_id": {"type": "string", "minLength": 1, "maxLength": 64},
                "action": {"type": "string", "enum": ["navigate", "read", "click", "type", "close"]},
                "url": {"type": "string", "maxLength": 2048},
                "selector": {"type": "string", "maxLength": 256},
                "text": {"type": "string", "maxLength": 1000},
            }, "required": ["run_id", "action"],
        }),)

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        if (grant is None or name != "browser_action" or
                grant.tool_name != name or grant.capability_id != "BrowserControl" or
                not grant.approval_consumed or grant.risk_level not in {"high", "critical"}):
            raise PermissionError("BrowserControl requires consumed Gateway approval")
        args = arguments or {}
        if set(args) - {"run_id", "action", "url", "selector", "text"}:
            raise ValueError("Unexpected browser arguments")
        run_id, action = args.get("run_id"), args.get("action")
        if not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9-]{36}", run_id):
            raise ValueError("Run identity invalid")
        if action not in {"navigate", "read", "click", "type", "close"}:
            raise ValueError("Browser action invalid")
        return await self.sessions.perform(run_id, action, args)
