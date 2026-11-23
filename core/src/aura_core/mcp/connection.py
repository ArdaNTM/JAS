"""Task-owned MCP client connections with deterministic transport teardown.

AnyIO stream/ClientSession cancel scopes MUST be exited by the same asyncio
Task that entered them.  Gateway request handlers and quarantine callbacks
are different tasks, so a connection-local owner processes serialized RPCs
and closes the transport on its own task rather than calling aclose() from
the arbitrary requesting task.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client


@dataclass(frozen=True, slots=True)
class MCPToolResult:
    """Result returned by an MCP tool invocation."""

    result: Any


class MCPConnection:
    """Managed MCP stdio / Streamable HTTP connection owned by one task."""

    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._owner: asyncio.Task | None = None
        self._requests: asyncio.Queue | None = None
        self._ready: asyncio.Future | None = None
        self._close_result: asyncio.Future | None = None

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP connection is not initialized")
        return self._session

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect_stdio(self, server: StdioServerParameters) -> None:
        await self._open("stdio", server)

    async def connect_http(self, url: str) -> None:
        await self._open("http", url)

    async def _open(self, kind: str, target: Any) -> None:
        if self._owner is not None:
            raise RuntimeError("MCP connection is already open")
        loop = asyncio.get_running_loop()
        self._requests = asyncio.Queue()
        self._ready = loop.create_future()
        self._close_result = None
        self._owner = asyncio.create_task(
            self._serve(kind, target), name="aura-mcp-transport-owner",
        )
        # A timed-out initialize cannot cancel the owner task's AnyIO scopes
        # from the caller. The caller's finally/close requests owner cleanup.
        await asyncio.shield(self._ready)

    async def _serve(self, kind: str, target: Any) -> None:
        """Enter, use and EXIT both AnyIO scopes in this same Task."""
        stack = AsyncExitStack()
        self._stack = stack
        failure: BaseException | None = None
        try:
            if kind == "stdio":
                read, write = await stack.enter_async_context(stdio_client(target))
            else:
                read, write = await stack.enter_async_context(
                    streamable_http_client(target),
                )
            self._session = await stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            if not self._ready.done():
                self._ready.set_result(None)

            assert self._requests is not None
            while True:
                operation, arguments, kwargs, answer = await self._requests.get()
                if operation == "__close__":
                    break
                try:
                    result = await getattr(self.session, operation)(*arguments, **kwargs)
                except Exception as exc:
                    if not answer.done():
                        answer.set_exception(exc)
                else:
                    if not answer.done():
                        answer.set_result(result)
        except BaseException as exc:
            failure = exc
        finally:
            try:
                # An ExitStack holds AnyIO cancel scopes from stdio_client and
                # ClientSession. NEVER delegate its aclose() to another task.
                await stack.aclose()
            except BaseException as exc:
                if failure is None:
                    failure = exc
            finally:
                self._session = None
                self._stack = None
                if self._ready is not None and not self._ready.done():
                    self._ready.set_exception(
                        failure or RuntimeError("MCP connection stopped before initialize"),
                    )
                if self._requests is not None:
                    while not self._requests.empty():
                        operation, _, _, answer = self._requests.get_nowait()
                        if answer is not None and not answer.done():
                            answer.set_exception(
                                failure or RuntimeError("MCP connection closed"),
                            )
                if self._close_result is not None and not self._close_result.done():
                    if failure is None or isinstance(failure, asyncio.CancelledError):
                        self._close_result.set_result(None)
                    else:
                        self._close_result.set_exception(failure)

    async def _request(self, operation: str, *arguments: Any, **kwargs: Any) -> Any:
        if (self._session is None or self._owner is None
                or self._owner.done() or self._close_result is not None):
            raise RuntimeError("MCP connection is not initialized")
        answer = asyncio.get_running_loop().create_future()
        assert self._requests is not None
        self._requests.put_nowait((operation, arguments, kwargs, answer))
        return await answer

    async def list_tools(self) -> Any:
        return await self._request("list_tools")

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None,
    ) -> Any:
        result = await self._request("call_tool", name, arguments=arguments)
        structured = getattr(result, "structured_content", None)
        return structured if structured is not None else result

    async def close(self) -> None:
        """Send teardown to the scope-owning task; callers may be other tasks."""
        owner = self._owner
        if owner is None:
            return
        if self._close_result is None:
            self._close_result = asyncio.get_running_loop().create_future()
            if owner.done():
                self._close_result.set_result(None)
            elif self._ready is not None and not self._ready.done():
                # Initialization in progress: cancel the owner itself, which
                # will unwind its own AsyncExitStack without cross-task exit.
                owner.cancel()
            else:
                assert self._requests is not None
                self._requests.put_nowait(("__close__", (), {}, None))
        try:
            await asyncio.shield(self._close_result)
            await asyncio.gather(owner, return_exceptions=True)
        finally:
            if owner.done():
                self._owner = None
                self._requests = None
                self._ready = None
                self._close_result = None
