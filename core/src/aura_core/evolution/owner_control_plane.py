"""Separate, explicitly provisioned Local Owner approval application.

NO dynamic plugin import, permission execution, tool registration, token-based
approval shortcut or AURA Core router. Run as a separate owner OS principal
with private pre-provisioned state and a pinned WebAuthn credential.
"""
from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.evolution.owner_challenge import TrustedOwnerPasskeyDecider
from aura_core.evolution.owner_passkey import WebAuthnOwnerAssertion
from aura_core.evolution.owner_receipt import OwnerReceiptIssuer

OWNER_ORIGIN = "http://localhost:8766"


class ChallengeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(min_length=1, max_length=128)


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(min_length=36, max_length=36)
    credential_id: str = Field(min_length=1, max_length=512)
    client_data_json: str = Field(min_length=1, max_length=8192)
    authenticator_data: str = Field(min_length=1, max_length=4096)
    signature: str = Field(min_length=1, max_length=1024)
    decision: Literal["approved", "denied"]


def create_owner_control_plane(
    *, approvals: SQLiteApprovalStore, decider: TrustedOwnerPasskeyDecider,
    receipt_issuer: OwnerReceiptIssuer | None = None,
    origin: str = OWNER_ORIGIN,
) -> FastAPI:
    if origin != OWNER_ORIGIN:
        raise ValueError("Owner service requires pinned localhost:8766 origin")
    if not isinstance(approvals, SQLiteApprovalStore) or not isinstance(decider, TrustedOwnerPasskeyDecider):
        raise TypeError("A protected approval store and WebAuthn decider are mandatory")

    app = FastAPI(title="AURA Trusted Owner", docs_url=None, redoc_url=None, openapi_url=None)
    package_root = Path(__file__).resolve().parent

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # Prevent browser DNS rebinding, cross-site form posts and accidental
        # requests to the owner control plane via the 127.0.0.1 UI origin.
        host = request.headers.get("host", "").lower()
        if host != "localhost:8766":
            return JSONResponse({"detail": "Owner Host mismatch"}, status_code=403)
        # All state-changing operations require exact browser Origin + JSON,
        # not just a bearer token or the ability to reach loopback.
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") != origin:
                return JSONResponse({"detail": "Owner Origin mismatch"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                return JSONResponse({"detail": "JSON-only owner request"}, status_code=415)
            if request.headers.get("sec-fetch-site", "same-origin") != "same-origin":
                return JSONResponse({"detail": "Cross-site owner request"}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'self'; style-src 'self';"
                " connect-src 'self'; img-src 'none'; form-action 'none';"
                " base-uri 'none'; frame-ancestors 'none'"
            ),
        })
        return response

    @app.get("/", response_class=HTMLResponse)
    def review_page():
        return (package_root / "owner_review.html").read_text(encoding="utf-8")

    @app.get("/app.js")
    def review_script():
        return PlainTextResponse(
            (package_root / "owner_review.js").read_text(encoding="utf-8"),
            media_type="text/javascript",
        )

    @app.get("/app.css")
    def review_style():
        return PlainTextResponse(
            (package_root / "owner_review.css").read_text(encoding="utf-8"),
            media_type="text/css",
        )

    @app.get("/api/owner/health")
    def health():
        return {"status": "review_only", "approval_auth": "webauthn-es256-uv",
                "activation_allowed": False, "origin": origin}

    @app.get("/api/owner/pending")
    def pending():
        return {"items": [
            {
                "approval_id": r.approval_id,
                "capability_id": r.capability_id,
                "operation_id": r.operation_id,
                "resource_scope": r.resource_scope,
                "request_fingerprint": r.request_fingerprint,
                "expires_at": r.expires_at,
                "version": r.version,
                "status": r.status.value,
            }
            for r in approvals.list_pending(limit=100)
            if r.capability_id == "GovernedSkillActivation"
            and r.principal_id == "local_owner"
            and r.operation_id in {"activate", "rollback", "revoke"}
        ], "mode": "read_only_until_owner_auth"}

    @app.post("/api/owner/challenge")
    def challenge(body: ChallengeBody):
        try:
            UUID(body.approval_id)
            return decider.issue(body.approval_id)
        except (PermissionError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=409, detail="Owner approval is unavailable or stale") from exc

    @app.post("/api/owner/decision")
    def decide(body: DecisionBody):
        try:
            UUID(body.challenge_id)
            assertion = WebAuthnOwnerAssertion(
                credential_id=body.credential_id, client_data_json=body.client_data_json,
                authenticator_data=body.authenticator_data, signature=body.signature,
            )
            updated = decider.decide(
                challenge_id=body.challenge_id, assertion=assertion,
                decision=ApprovalStatus(body.decision),
            )
        except (PermissionError, ValueError, KeyError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail="Owner assertion rejected or approval changed") from exc
        # The independent owner service issues an unforgeable, short-lived
        # handoff only after a server-verified passkey decision. The client
        # transports it explicitly; this endpoint NEVER executes an MCP tool.
        receipt = None
        if updated.status is ApprovalStatus.APPROVED and receipt_issuer is not None:
            receipt = receipt_issuer.issue(updated)
        return {
            "approval_id": updated.approval_id, "status": updated.status.value,
            "version": updated.version,
            "signed_owner_receipt": receipt,
            "activation_performed": False, "tool_executed": False,
        }

    return app
