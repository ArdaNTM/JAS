from __future__ import annotations

import inspect
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_core.security.http_auth import authenticated_principal
from aura_core.enterprise.approval_store import (
    ApprovalConflict, ApprovalExpired, ApprovalStatus, InvalidApprovalTransition,
)

router = APIRouter(tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "denied"]
    expected_version: int = Field(ge=1)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


@router.get("/api/approvals")
async def pending_approvals(
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> list[dict[str, object]]:
    store = getattr(request.app.state, "approval_store", None)
    if store is None:
        return []
    records = await _resolve(store.list_pending(limit=100))
    return [
        {
            "approval_id": record.approval_id,
            "principal_id": record.principal_id,
            "capability_id": record.capability_id,
            "operation_id": record.operation_id,
            "resource_scope": record.resource_scope,
            "status": record.status.value,
            "version": record.version,
            "requested_at": record.requested_at,
            "expires_at": record.expires_at,
        }
        for record in records
    ]


@router.post("/api/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> dict[str, object]:
    store = getattr(request.app.state, "approval_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Approval store is not configured")
    try:
        record = await _resolve(store.get(approval_id))
        if record is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        if record.principal_id == principal_id:
            raise HTTPException(status_code=403, detail="A requester cannot approve their own request")
        decision = ApprovalStatus.APPROVED if body.decision == "approved" else ApprovalStatus.DENIED
        updated = await _resolve(store.decide(
            approval_id,
            expected_version=body.expected_version,
            approver_id=principal_id,
            decision=decision,
        ))
    except HTTPException:
        raise
    except (ApprovalConflict, ApprovalExpired, InvalidApprovalTransition, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Approval decision conflicts with the current record") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Approval store unavailable") from exc
    return {
        "approval_id": updated.approval_id,
        "status": updated.status.value,
        "version": updated.version,
        "approver_id": updated.approver_id,
    }
