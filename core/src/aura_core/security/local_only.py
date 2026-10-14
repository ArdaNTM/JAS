from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_local_request(
    peer_host: str | None,
    host_header: str | None,
    origin: str | None = None,
) -> bool:
    """Allow only loopback peers and local browser origins."""
    if not peer_host or not host_header:
        return False

    try:
        if not ipaddress.ip_address(peer_host).is_loopback:
            return False
    except ValueError:
        return False

    try:
        parsed_host = urlsplit("//" + host_header)
        hostname = (parsed_host.hostname or "").lower()
        port = parsed_host.port
    except ValueError:
        return False

    if hostname not in _LOCAL_HOSTS:
        return False

    expected_port = int(os.getenv("AURA_CORE_PORT", "8000"))
    if port is not None and port != expected_port:
        return False

    if origin:
        try:
            parsed_origin = urlsplit(origin)
            origin_host = (parsed_origin.hostname or "").lower()
            _ = parsed_origin.port
        except ValueError:
            return False

        if parsed_origin.scheme not in {"http", "https"}:
            return False
        if origin_host not in _LOCAL_HOSTS:
            return False

    return True


def require_local_http_request(request) -> None:
    from fastapi import HTTPException

    peer = request.client.host if request.client else None
    host = request.headers.get("host")
    origin = request.headers.get("origin")

    if not is_local_request(peer, host, origin):
        raise HTTPException(
            status_code=403,
            detail="AURA local-only security policy rejected this request",
        )


def is_local_websocket(websocket) -> bool:
    peer = websocket.client.host if websocket.client else None
    host = websocket.headers.get("host")
    origin = websocket.headers.get("origin")
    return is_local_request(peer, host, origin)
