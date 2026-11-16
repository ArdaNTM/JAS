from __future__ import annotations

import inspect
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_core.security.http_auth import authenticated_principal
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationRequest, RiskLevel
from aura_core.enterprise.approval_store import (
    ApprovalConflict, ApprovalExpired, ApprovalStatus, InvalidApprovalTransition,
)

router = APIRouter(tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "denied"]
    expected_version: int = Field(ge=1)


async def _resolve(value):
    return await value if inspect.isawaitable(value) else value


async def _review_allowed(request: Request, principal_id: str, record, operation: str) -> bool:
    """Require an *existing* PermissionEngine allow policy for cross-principal review.

    Approval records are not themselves authority. No implicit reviewer role,
    header-supplied principal, or new capability registration is granted here.
    The composition root must explicitly register the review capability and
    install its narrow policy to enable any cross-principal review.
    """
    engine = getattr(request.app.state, "permission_engine", None)
    if engine is None:
        return False
    try:
        # Escape slashes so identity components cannot widen policy scopes.
        target = "approval/" + quote(record.principal_id, safe="") + "/" + quote(record.approval_id, safe="")
        auth = AuthorizationRequest(
            request_id=f"approval-review:{uuid4()}",
            principal_id=principal_id,
            capability_id="approval.review",
            operation_id=operation,
            resource_scope=target,
            risk_level=RiskLevel.HIGH,
        )
        decision = await _resolve(engine.authorize(auth))
        return decision.decision is AuthorizationDecision.ALLOW
    except Exception:
        # Missing, malfunctioning, revoked or deferred policy fails closed.
        return False


@router.get("/api/approvals")
async def pending_approvals(
    request: Request,
    principal_id: str = Depends(authenticated_principal),
) -> list[dict[str, object]]:
    store = getattr(request.app.state, "approval_store", None)
    if store is None:
        return []
    records = await _resolve(store.list_pending(limit=100))
    visible = []
    for record in records:
        if record.principal_id == principal_id or await _review_allowed(request, principal_id, record, "approval.list"):
            visible.append(record)
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
        for record in visible
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
        if not await _review_allowed(request, principal_id, record, "approval.decide"):
            raise HTTPException(status_code=403, detail="Explicit reviewer authorization required")
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
