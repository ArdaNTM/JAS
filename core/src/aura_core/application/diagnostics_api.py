"""Safe, provider-agnostic deployment diagnostics.

This API intentionally reports configuration and registry state only.  It
never returns credential values or invokes a provider as a side effect.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Request


router = APIRouter(tags=["diagnostics"])


def _configured(name: str) -> str:
    return "configured" if os.getenv(name) else "not_configured"


@router.get("/api/diagnostics/providers")
async def provider_diagnostics(request: Request) -> dict[str, object]:
    """Return non-secret provider and capability registration information."""
    kernel = getattr(request.app.state, "kernel", None)
    capability_registry = getattr(kernel, "capability_registry", None)
    provider_registry = getattr(kernel, "provider_registry", None)

    capabilities: list[dict[str, object]] = []
    if capability_registry is not None:
        for record in capability_registry.records():
            definition = record.definition
            capabilities.append(
                {
                    "capability_id": definition.capability_id,
                    "provider_id": definition.provider_id,
                    "provider_type": definition.provider_type,
                    "state": record.state,
                    "available": record.available,
                    "healthy": record.healthy,
                }
            )

    providers: list[dict[str, object]] = []
    if provider_registry is not None:
        for record in provider_registry.records():
            providers.append(
                {
                    "provider_id": record.definition.provider_id,
                    "state": record.state,
                    "available": record.available,
                    "healthy": record.healthy,
                }
            )

    return {
        "status": "ok",
        "providers": {
            "ollama": {
                "status": "configured",
                "url": os.getenv("AURA_OLLAMA_URL", "http://127.0.0.1:11434"),
                "model": os.getenv("AURA_OLLAMA_MODEL", "qwen3:4b-instruct-2507-q4_K_M"),
            },
            "openai": {"status": _configured("OPENAI_API_KEY")},
            "postgres": {"status": _configured("AURA_POSTGRES_DSN")},
            "qdrant": {"status": _configured("AURA_QDRANT_URL")},
            "external_capabilities": {
                "status": _configured("AURA_MCP_PROVIDER_ENDPOINT"),
            },
        },
        "registered_providers": providers,
        "registered_capabilities": capabilities,
    }
