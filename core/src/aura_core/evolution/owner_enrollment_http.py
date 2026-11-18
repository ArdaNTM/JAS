"""Ephemeral owner-only bootstrap WebAuthn enrollment server.

Run this standalone on the owner-controlled Windows login before ordinary
owner_control_plane. It does not mount into Core or accept AURA bearer tokens.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from aura_core.evolution.owner_enrollment import ProtectedEnrollment

HOST = "localhost:8766"
ORIGIN = "http://localhost:8766"


class RegistrationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: dict = Field(description="WebAuthn RegistrationResponse JSON")


def create_enrollment_app(*, ceremony: ProtectedEnrollment) -> FastAPI:
    if not isinstance(ceremony, ProtectedEnrollment):
        raise ValueError("Only a provisioned owner enrollment ceremony may be exposed")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    root = Path(__file__).resolve().parent

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.headers.get("host", "").lower() != HOST:
            return JSONResponse({"detail": "Host denied"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") != ORIGIN:
                return JSONResponse({"detail": "Origin denied"}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                return JSONResponse({"detail": "JSON required"}, status_code=415)
            if request.headers.get("sec-fetch-site", "same-origin") != "same-origin":
                return JSONResponse({"detail": "Cross-site request denied"}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'self'; style-src 'self';"
                " connect-src 'self'; form-action 'none'; base-uri 'none';"
                " frame-ancestors 'none'"
            ),
        })
        return response

    @app.get("/", response_class=HTMLResponse)
    def page():
        return (root / "owner_enroll.html").read_text(encoding="utf-8")

    @app.get("/enroll.js")
    def script():
        return PlainTextResponse(
            (root / "owner_enroll.js").read_text(encoding="utf-8"),
            media_type="text/javascript",
        )

    @app.post("/api/enrollment/begin")
    def begin(request: Request):
        try:
            return ceremony.begin(request.headers.get("x-aura-bootstrap", ""))
        except (ValueError, PermissionError):
            raise HTTPException(403, "Owner bootstrap unavailable") from None

    @app.post("/api/enrollment/complete")
    def finish(body: RegistrationBody, request: Request):
        try:
            return ceremony.complete(
                request.headers.get("x-aura-bootstrap", ""),
                body.response,
            )
        except (ValueError, PermissionError):
            raise HTTPException(403, "Passkey registration rejected") from None

    return app
