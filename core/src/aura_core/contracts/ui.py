from __future__ import annotations

"""Stable, provider-neutral contract exposed to the AURA UI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OperationState = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
]


class UIErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    request_id: str | None = None
    details: object | None = None


class UIErrorEnvelope(BaseModel):
    """Versioned error body; legacy top-level detail remains for compatibility."""

    model_config = ConfigDict(extra="forbid")

    error: UIErrorDetail
    detail: object | None = None


class OperationStatus(BaseModel):
    """UI-facing operation snapshot, independent of provider implementation."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=128)
    state: OperationState
    request_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    message: str | None = Field(default=None, max_length=500)
    result: object | None = None
    error: UIErrorDetail | None = None
    requires_approval: bool = False


class UIContractResponse(BaseModel):
    """Small discovery document for the frontend to negotiate supported contract."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"]
    request_id_header: Literal["X-Request-ID"]
    operation_states: list[OperationState]
    error_fields: list[str]
    security: dict[str, str]
    endpoints: dict[str, str]
