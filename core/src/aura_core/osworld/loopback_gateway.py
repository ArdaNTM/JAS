"""Fixed four-port TCP relay for a disposable, isolated OSWorld VM.

Executed inside a digest-pinned Python image; it accepts exactly one VM IPv4
destination and forwards no unlisted TCP ports. It does not expose an HTTP
proxy, CONNECT endpoint, command runner or configurable destinations.
"""
from __future__ import annotations

import asyncio
import ipaddress
import sys

PORTS = (5000, 8006, 8080, 9222)


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass


async def _forward(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    vm_ip: str,
    port: int,
) -> None:
    upstream = None
    try:
        server_reader, upstream = await asyncio.wait_for(
            asyncio.open_connection(vm_ip, port), timeout=5
        )
        await asyncio.gather(_copy(reader, upstream), _copy(server_reader, writer))
    except (ConnectionError, OSError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()
        if upstream is not None:
            upstream.close()
            await upstream.wait_closed()
        await writer.wait_closed()


async def _main(vm_ip: str) -> None:
    address = ipaddress.ip_address(vm_ip)
    if (not isinstance(address, ipaddress.IPv4Address)
            or not address.is_private or address.is_loopback or address.is_link_local):
        raise ValueError("Invalid pinned internal VM address")
    listeners = []
    for port in PORTS:
        async def handler(reader, writer, *, destination=port):
            await _forward(reader, writer, vm_ip, destination)
        listeners.append(await asyncio.start_server(handler, "0.0.0.0", port))
    await asyncio.gather(*(listener.serve_forever() for listener in listeners))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Exactly one pinned VM IPv4 address required")
    asyncio.run(_main(sys.argv[1]))
