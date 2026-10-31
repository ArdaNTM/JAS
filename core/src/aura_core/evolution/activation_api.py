"""Opt-in versioned MCP skill activation API with independently composed trust.

This is NOT automatically mounted in AURA Core. Construct only in a trusted
control plane with a GovernedSkillRegistry whose owner callback is a durable
Ed25519 verifier and whose signed-attestation callback is mandatory.
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.evolution.owner_receipt import DurableOwnerReceiptConsumer
from aura_core.evolution.skill_registry import GovernedSkillRegistry

_NAME = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")


class VersionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=3, max_length=64)
    owner_receipt: str = Field(min_length=1, max_length=4096)
    action: Literal["activate", "rollback", "revoke"]


def create_governed_activation_app(
    *, registry: GovernedSkillRegistry,
    owner_receipts: DurableOwnerReceiptConsumer,
    trusted_host: str = "localhost:8767",
    trusted_origin: str = "http://localhost:8766",
) -> FastAPI:
    if not isinstance(registry, GovernedSkillRegistry):
        raise ValueError("A governed registry is mandatory")
    if not isinstance(owner_receipts, DurableOwnerReceiptConsumer):
        raise ValueError("Pinned signed Local Owner receipts are mandatory")
    if registry._owner is not owner_receipts or registry._signed is None:
        raise PermissionError("Registry must be composed with this owner verifier and signed attestation")
    if trusted_host != "localhost:8767" or trusted_origin != "http://localhost:8766":
        raise ValueError("Only pinned local control-plane endpoints are supported")

    app = FastAPI(title="AURA Governed Activation", docs_url=None,
                  redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if (request.headers.get("host", "").lower() != trusted_host
            or request.client is None
            or request.client.host not in {"127.0.0.1", "::1", "testclient"}):
            return JSONResponse({"detail": "Local activation boundary required"}, status_code=403)
        if request.method != "GET":
            if request.headers.get("origin") != trusted_origin:
                return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return JSONResponse({"detail": "JSON request required"}, status_code=415)
            if request.headers.get("sec-fetch-site", "same-site") not in {"same-site", "same-origin"}:
                return JSONResponse({"detail": "Cross-site requests denied"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/activation/status")
    def status():
        return {"mode": "opt_in", "tool_execution": False,
                "owner_signature_required": True,
                "sandbox_attestation_required": True}

    @app.post("/api/activation/version")
    def change(body: VersionChange):
        if not _NAME.fullmatch(body.name):
            raise HTTPException(status_code=422, detail="Invalid skill name")
        # No raw code or arguments accepted. Registry confirms that the MCP
        # provider is already registered/healthy, signed sandbox evidence is
        # still valid, and the owner receipt is valid and single-use.
        try:
            if body.action == "activate":
                revision = registry.activate(
                    body.name, principal_id="local_owner", owner_receipt=body.owner_receipt,
                )
            elif body.action == "rollback":
                revision = registry.rollback(
                    body.name, principal_id="local_owner", owner_receipt=body.owner_receipt,
                )
            else:
                registry.revoke(body.name, principal_id="local_owner", owner_receipt=body.owner_receipt)
                revision = None
        except (PermissionError, ValueError, KeyError):
            raise HTTPException(status_code=403, detail="Governed version change rejected") from None
        return {"name": body.name, "action": body.action, "revision": revision,
                "tool_executed": False, "generated_python_loaded": False}

    return app
