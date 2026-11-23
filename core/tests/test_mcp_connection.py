import asyncio
from unittest.mock import AsyncMock, patch

from aura_core.mcp.connection import MCPConnection


def test_stdio_transport_is_initialized() -> None:
    connection = MCPConnection()

    async def run() -> None:
        with patch(
            "aura_core.mcp.connection.stdio_client"
        ) as stdio_client:
            transport = AsyncMock()
            transport.__aenter__.return_value = (
                object(),
                object(),
            )
            stdio_client.return_value = transport

            session = AsyncMock()
            session.__aenter__.return_value = session
            session.initialize.return_value = object()

            with patch(
                "aura_core.mcp.connection.ClientSession",
                return_value=session,
            ):
                from mcp.client.stdio import StdioServerParameters

                server = StdioServerParameters(
                    command="test-server",
                )

                await connection.connect_stdio(server)

                stdio_client.assert_called_once_with(server)
                session.initialize.assert_awaited_once()
                assert connection.is_connected is True

        await connection.close()

    asyncio.run(run())


def test_http_transport_is_initialized() -> None:
    connection = MCPConnection()

    async def run() -> None:
        with patch(
            "aura_core.mcp.connection.streamable_http_client"
        ) as http_client:
            transport = AsyncMock()
            transport.__aenter__.return_value = (
                object(),
                object(),
            )
            http_client.return_value = transport

            session = AsyncMock()
            session.__aenter__.return_value = session
            session.initialize.return_value = object()

            with patch(
                "aura_core.mcp.connection.ClientSession",
                return_value=session,
            ):
                url = "http://127.0.0.1:8000/mcp"

                await connection.connect_http(url)

                http_client.assert_called_once_with(url)
                session.initialize.assert_awaited_once()
                assert connection.is_connected is True

        await connection.close()

    asyncio.run(run())


def test_cross_task_close_exits_anyio_cancel_scope_on_its_owner_task() -> None:
    """Quarantine from a different Task must not corrupt AnyIO's scope stack."""
    import anyio
    from types import SimpleNamespace

    connection = MCPConnection()
    scopes = []

    class TaskBoundTransport:
        async def __aenter__(self):
            self.owner = asyncio.current_task()
            self.scope = anyio.CancelScope()
            self.scope.__enter__()
            scopes.append(self)
            return object(), object()

        async def __aexit__(self, typ, exc, tb):
            # This reproduces the real anyio error if teardown is invoked
            # by an async quarantine callback instead of the owning Task.
            assert asyncio.current_task() is self.owner
            self.scope.__exit__(typ, exc, tb)

    async def scenario():
        transport = TaskBoundTransport()
        with patch("aura_core.mcp.connection.stdio_client", return_value=transport):
            session = AsyncMock()
            session.__aenter__.return_value = session
            session.call_tool.return_value = SimpleNamespace(
                structured_content={"ok": True},
            )
            with patch("aura_core.mcp.connection.ClientSession", return_value=session):
                await connection.connect_stdio(SimpleNamespace(command="fake"))
                assert await connection.call_tool("start_session", {}) == {"ok": True}
                # A different task closes the connection, just like
                # asyncio.create_task(manager.quarantine(...)).
                await asyncio.create_task(connection.close())
                await connection.close()
                assert not connection.is_connected
                assert connection._owner is None
                session.call_tool.assert_awaited_once()
        assert transport.owner is not asyncio.current_task()
        assert len(scopes) == 1

    asyncio.run(scenario())


def test_failing_stdio_initialize_still_closes_on_owner_task() -> None:
    import anyio
    from types import SimpleNamespace

    connection = MCPConnection()
    exited = []

    class ScopedTransport:
        async def __aenter__(self):
            self.owner = asyncio.current_task()
            self.scope = anyio.CancelScope()
            self.scope.__enter__()
            return object(), object()

        async def __aexit__(self, typ, exc, tb):
            assert asyncio.current_task() is self.owner
            self.scope.__exit__(typ, exc, tb)
            exited.append(True)

    async def scenario():
        with patch("aura_core.mcp.connection.stdio_client",
                   return_value=ScopedTransport()):
            session = AsyncMock()
            session.__aenter__.return_value = session
            session.initialize.side_effect = RuntimeError("initialize rejected")
            with patch("aura_core.mcp.connection.ClientSession", return_value=session):
                try:
                    await connection.connect_stdio(SimpleNamespace(command="fake"))
                except RuntimeError as exc:
                    assert "initialize rejected" in str(exc)
                else:
                    raise AssertionError("Bad handshake must fail")
                await connection.close()
        assert exited == [True]
        assert not connection.is_connected

    asyncio.run(scenario())
