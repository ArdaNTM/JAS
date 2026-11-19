"""Connection-pinned HTTPS CONNECT proxy for AURA browser evaluation.

Defense layers:
* Exact canonical public DNS hostname allowlist (no wildcard or IP literals).
* DNS lookup once and connect to that specific *public* IP, never to hostname.
* Actual socket peer must equal the selected pinned address (IPv4 or IPv6).
* Strict CONNECT-only, port 443, loopback bind, authenticated browser client.
* No TLS interception or CA override: Chromium verifies certificate/SNI for
  the original hostname through this tunnel.
* Bounded header, sessions, bytes and wall time; fail closed on uncertainty.

IMPORTANT: An application-level proxy is NOT a network isolation boundary.
The browser must run under a disposable, non-admin OS principal/VM with firewall
rules blocking ALL direct egress (DNS, UDP/QUIC, IPv4, IPv6, WebRTC, localhost
bypasses) except its authenticated loopback proxy. The proxy itself must be
isolated from private networks. This module cannot attest firewall state.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SECRET = re.compile(r"^[a-f0-9]{64}$")
_BLOCKED_SUFFIXES = (".local", ".localhost", ".localdomain", ".internal", ".test", ".invalid", ".home", ".lan")


class EgressDenied(PermissionError):
    """A network destination or socket violates the network trust policy."""


def canonical_hostname(value: str) -> str:
    """Accept only a complete, lower-case ASCII FQDN with bounded labels."""
    if (not isinstance(value, str) or not 4 <= len(value) <= 253
            or value.lower() != value or value.endswith(".")
            or any(char in value for char in "/\\:@?#% \t\r\n")
            or value.endswith(_BLOCKED_SUFFIXES)):
        raise EgressDenied("Noncanonical or reserved hostname")
    labels = value.split(".")
    if len(labels) < 2 or any(not _LABEL.fullmatch(part) for part in labels):
        raise EgressDenied("Invalid DNS hostname")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise EgressDenied("IP literal destinations are forbidden")


@dataclass(frozen=True, slots=True)
class ApprovedDestination:
    """DNS answers validated as a set, not a credential to open arbitrary URLs."""
    hostname: str
    port: int
    addresses: tuple[str, ...]


class EgressPolicy:
    """Pure deterministic policy invoked at socket connection time."""

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        if not 1 <= len(allowed_hosts) <= 16:
            raise ValueError("One to sixteen allowed destinations required")
        if any(canonical_hostname(host) != host for host in allowed_hosts):
            raise ValueError("Allowlist must contain exact public canonical DNS names")
        self._allowed = allowed_hosts

    def authorize(
        self, *, hostname: str, port: int,
        resolved_addresses: Sequence[str],
    ) -> ApprovedDestination:
        hostname = canonical_hostname(hostname)
        if hostname not in self._allowed or type(port) is not int or port != 443:
            raise EgressDenied("Destination was not allowlisted")
        if not 1 <= len(resolved_addresses) <= 32:
            raise EgressDenied("Empty or unbounded DNS response")
        addresses: set[str] = set()
        for raw in resolved_addresses:
            try:
                address = ipaddress.ip_address(raw)
            except (ValueError, TypeError) as exc:
                raise EgressDenied("Invalid DNS record") from exc
            if not address.is_global:
                raise EgressDenied("Private, local, reserved or non-global DNS record")
            addresses.add(address.compressed)
        return ApprovedDestination(hostname, 443, tuple(sorted(addresses)))

    @staticmethod
    def require_pinned_peer(destination: ApprovedDestination, peer_ip: str) -> None:
        try:
            peer = ipaddress.ip_address(peer_ip).compressed
        except (ValueError, TypeError) as exc:
            raise EgressDenied("Invalid connected peer") from exc
        if peer not in destination.addresses:
            raise EgressDenied("Connected peer differs from DNS-pinned destination")


class DNSResolver(Protocol):
    """Injected resolver for testability, never authorization by itself."""

    async def resolve(self, hostname: str) -> tuple[str, ...]: ...


class SystemDNSResolver:
    """Resolve A/AAAA; filtering and IP pinning remain in the EgressPolicy."""

    async def resolve(self, hostname: str) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        records = await asyncio.wait_for(
            loop.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM),
            timeout=3.0,
        )
        return tuple(sorted({record[4][0] for record in records}))


class PinnedConnectProxy:
    """Bounded authenticated HTTP CONNECT proxy, no uninspected direct URLs.

    A 64-hex-character pre-shared credential is required. Playwright must use
    username='aura', password=<token>. Proxy has no credentials for the target
    and no authority to change AURA permissions.
    """

    def __init__(
        self, *, policy: EgressPolicy, token: str,
        resolver: DNSResolver | None = None,
        max_connections: int = 16,
        max_bytes_per_direction: int = 32 * 1024 * 1024,
        max_tunnel_seconds: float = 60.0,
    ) -> None:
        if not isinstance(token, str) or not _SECRET.fullmatch(token):
            raise ValueError("A random 256-bit proxy credential is mandatory")
        if not 1 <= max_connections <= 64:
            raise ValueError("Connection budget must be bounded")
        if not 4096 <= max_bytes_per_direction <= 128 * 1024 * 1024:
            raise ValueError("Transfer budget must be bounded")
        if not 1 <= max_tunnel_seconds <= 180:
            raise ValueError("Tunnel deadline is required")
        self._policy = policy
        self._token = token
        self._resolver = resolver or SystemDNSResolver()
        self._limit = asyncio.Semaphore(max_connections)
        self._max_bytes = max_bytes_per_direction
        self._deadline = max_tunnel_seconds
        self._server: asyncio.AbstractServer | None = None
        self._active: set[asyncio.Task[None]] = set()

    async def start(self, *, port: int = 0) -> int:
        """Start loopback-only; caller MUST separately enforce host firewall."""
        if self._server is not None:
            raise RuntimeError("Pinned proxy already started")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("Invalid loopback proxy port")
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=port, limit=8192,
        )
        return self._server.sockets[0].getsockname()[1]

    async def serve_forever(self) -> None:
        """Run the authenticated proxy until operator cancellation."""
        if self._server is None:
            raise RuntimeError("Proxy must be started before serving")
        await self._server.serve_forever()

    async def close(self) -> None:
        """Stop accepting connections and cancel existing tunnels."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
            await server.wait_closed()
        active = tuple(self._active)
        for task in active:
            task.cancel()
        await asyncio.gather(*active, return_exceptions=True)
        self._active.clear()

    def _authenticated(self, header: str) -> bool:
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:], validate=True)
        except (binascii.Error, ValueError):
            return False
        if len(raw) > 128:
            return False
        return hmac.compare_digest(raw, ("aura:" + self._token).encode("ascii"))

    def _parse(self, raw: bytes) -> str:
        """Parse one strict HTTP/1.1 CONNECT header, never follow URL content."""
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EgressDenied("Invalid CONNECT header encoding") from exc
        lines = text[:-4].split("\r\n")
        if len(lines) > 24:
            raise EgressDenied("Too many proxy headers")
        parts = lines[0].split(" ")
        if len(parts) != 3 or parts[0] != "CONNECT" or parts[2] != "HTTP/1.1":
            raise EgressDenied("Only HTTP/1.1 CONNECT is supported")
        target = parts[1]
        if target.count(":") != 1:
            raise EgressDenied("CONNECT requires canonical host:443")
        host, port_text = target.split(":")
        if port_text != "443":
            raise EgressDenied("CONNECT port must be 443")
        host = canonical_hostname(host)
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                raise EgressDenied("Malformed proxy header")
            name, value = line.split(":", 1)
            name = name.casefold()
            if (name in headers or not re.fullmatch(r"[a-z-]{1,32}", name)
                    or "\r" in value or "\n" in value):
                raise EgressDenied("Duplicate or invalid proxy header")
            headers[name] = value.strip()
        if headers.get("host") not in (None, target):
            raise EgressDenied("CONNECT Host header mismatch")
        if not self._authenticated(headers.get("proxy-authorization", "")):
            raise EgressDenied("Proxy authentication required")
        if "transfer-encoding" in headers or "content-length" in headers:
            raise EgressDenied("CONNECT request body forbidden")
        return host

    async def _copy(
        self, source: asyncio.StreamReader, target: asyncio.StreamWriter,
    ) -> None:
        count = 0
        while True:
            chunk = await source.read(16384)
            if not chunk:
                return
            count += len(chunk)
            if count > self._max_bytes:
                raise EgressDenied("Tunnel byte budget exceeded")
            target.write(chunk)
            await target.drain()

    async def _tunnel(
        self, client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        destination: ApprovedDestination,
    ) -> None:
        # DNS is NOT looked up again: the socket connects to the exact IP
        # checked by EgressPolicy, closing the classic check/use rebinding gap.
        remote_reader: asyncio.StreamReader | None = None
        remote_writer: asyncio.StreamWriter | None = None
        try:
            for ip in destination.addresses:
                try:
                    remote_reader, remote_writer = await asyncio.wait_for(
                        asyncio.open_connection(host=ip, port=443), timeout=5,
                    )
                    peer = remote_writer.get_extra_info("peername")
                    if not isinstance(peer, tuple) or not peer:
                        raise EgressDenied("Missing connected-peer identity")
                    self._policy.require_pinned_peer(destination, str(peer[0]))
                    break
                except (OSError, asyncio.TimeoutError):
                    # A rejected/mismatched peer must never retain an open socket.
                    if remote_writer is not None:
                        remote_writer.close()
                        try:
                            await remote_writer.wait_closed()
                        except OSError:
                            pass
                    remote_reader = None
                    remote_writer = None
                    continue
            if remote_reader is None or remote_writer is None:
                raise EgressDenied("No permitted pinned destination reachable")
            # Browser performs HTTPS/TLS verification through the tunnel using
            # the original hostname; the proxy never disables certificate checks.
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
            upstream = asyncio.create_task(self._copy(client_reader, remote_writer))
            downstream = asyncio.create_task(self._copy(remote_reader, client_writer))
            try:
                done, pending = await asyncio.wait(
                    {upstream, downstream}, timeout=self._deadline,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    raise EgressDenied("Tunnel wall-time budget exceeded")
                for task in done:
                    task.result()
            finally:
                for task in (upstream, downstream):
                    task.cancel()
                await asyncio.gather(upstream, downstream, return_exceptions=True)
        finally:
            if remote_writer is not None:
                remote_writer.close()
                try:
                    await remote_writer.wait_closed()
                except OSError:
                    pass

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._active.add(task)
        try:
            async with self._limit:
                peer = writer.get_extra_info("peername")
                if not isinstance(peer, tuple) or not ipaddress.ip_address(peer[0]).is_loopback:
                    raise EgressDenied("Proxy accepts only loopback clients")
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
                host = self._parse(raw)
                answers = await self._resolver.resolve(host)
                destination = self._policy.authorize(
                    hostname=host, port=443, resolved_addresses=answers,
                )
                await self._tunnel(reader, writer, destination)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, EgressDenied, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            try:
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                await writer.drain()
            except (OSError, ConnectionError):
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            if task is not None:
                self._active.discard(task)
