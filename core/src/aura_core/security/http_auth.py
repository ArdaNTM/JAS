"""Bearer authentication for protected local AURA HTTP operations.

The token is supplied by deployment configuration and is never accepted from
query parameters or request bodies. A configured principal is server-owned;
clients cannot choose the principal used by the Permission Engine.
"""
from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request, status


def load_http_auth_config() -> tuple[str | None, str]:
    """Load optional HTTP credentials; protected endpoints fail closed if absent."""
    token = os.getenv("AURA_API_BEARER_TOKEN", "").strip()
    principal_id = os.getenv("AURA_API_PRINCIPAL_ID", "local_owner").strip()

    if token and len(token) < 32:
        raise RuntimeError("AURA_API_BEARER_TOKEN must contain at least 32 characters")
    if not principal_id:
        raise RuntimeError("AURA_API_PRINCIPAL_ID must not be blank")

    return token or None, principal_id


def authenticated_principal(request: Request) -> str:
    """Return the server-configured principal only after valid bearer authentication."""
    expected_token = getattr(request.app.state, "http_bearer_token", None)
    principal_id = getattr(request.app.state, "http_principal_id", None)

    if not isinstance(expected_token, str) or not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HTTP authentication is not configured",
        )
    if not isinstance(principal_id, str) or not principal_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HTTP principal is not configured",
        )

    authorization = request.headers.get("Authorization", "")
    scheme, separator, supplied_token = authorization.partition(" ")
    if (
        not separator
        or scheme.casefold() != "bearer"
        or not supplied_token
        or supplied_token.strip() != supplied_token
        or any(ch.isspace() for ch in supplied_token)
        or not hmac.compare_digest(supplied_token, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return principal_id
