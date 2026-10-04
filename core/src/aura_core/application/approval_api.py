from __future__ import annotations

from fastapi import APIRouter, Request

from aura_core.kernel.permissions import AuthorizationDecision

router = APIRouter(tags=["approvals"])


@router.get("/api/approvals")
async def pending_approvals(
    request: Request,
) -> list[dict[str, object]]:
    """
    Read-only projection of recent approval-required decisions.

    The authorization engine remains authoritative.

    Approval resolution is intentionally not implemented as a fake
    client-side permission bypass.
    """

    permission_engine = getattr(
        request.app.state,
        "permission_engine",
        None,
    )

    if permission_engine is None:
        return []

    records = permission_engine.audit_records()

    result: list[dict[str, object]] = []

    for record in reversed(records):
        if (
            record.decision.decision
            is not AuthorizationDecision.REQUIRE_APPROVAL
        ):
            continue

        result.append(
            {
                "id": record.request.request_id,
                "task_id": record.request.task_id,
                "principal_id": record.request.principal_id,
                "capability": record.request.capability_id,
                "operation": record.request.operation_id,
                "resource_scope": record.request.resource_scope,
                "risk_level": record.request.risk_level,
                "reason": record.decision.reason,
                "status": "pending",
                "timestamp": record.decision.timestamp.isoformat(),
            }
        )

    return result[:100]