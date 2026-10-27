from dataclasses import FrozenInstanceError, fields
import asyncio
from unittest.mock import AsyncMock

import pytest

from aura_core.enterprise.runtime_controls import AuditEvent, HashChainAuditLedger
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.gateway import MCPGateway

from test_mcp_gateway import make_gateway, make_policy, make_request


SECRET = "SYNTHETIC_SECRET_7f2c9a"


def test_audit_event_is_frozen_and_has_only_allowlisted_fields() -> None:
    event = AuditEvent(
        principal_id="agent:planner",
        capability_id="filesystem.read",
        operation_id="filesystem.read_file",
        outcome="allowed",
        reason_code="provider_call_completed",
    )
    assert {item.name for item in fields(event)} == {
        "principal_id", "capability_id", "operation_id", "outcome", "reason_code"
    }
    with pytest.raises(FrozenInstanceError):
        event.outcome = "error"  # type: ignore[misc]
    with pytest.raises(TypeError, match="only AuditEvent"):
        HashChainAuditLedger().append({  # type: ignore[arg-type]
            "principal_id": "agent:planner", "arguments": {"token": SECRET}
        })


@pytest.mark.parametrize("field,value", [
    ("principal_id", "agent:planner\\nFORGED outcome=allowed"),
    ("capability_id", "filesystem.read\\r\\nFORGED"),
    ("operation_id", "filesystem.read_file\\tFORGED"),
])
def test_audit_event_rejects_secret_like_or_injection_metadata(field: str, value: str) -> None:
    values = {
        "principal_id": "agent:planner",
        "capability_id": "filesystem.read",
        "operation_id": "filesystem.read_file",
        "outcome": "allowed",
        "reason_code": "provider_call_completed",
    }
    values[field] = value
    with pytest.raises(ValueError):
        AuditEvent(**values)


def test_gateway_nested_secret_arguments_never_enter_audit_event() -> None:
    base, permissions, provider = make_gateway()
    ledger = HashChainAuditLedger()
    gateway = MCPGateway(
        base._capability_registry, base._provider_registry, permissions, audit_ledger=ledger
    )
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    provider.connection.call_tool.return_value = {
        "content": [{"type": "text", "text": f"result contains {SECRET}"}]
    }
    arguments = {
        "config": {"credentials": {"api_key": SECRET}},
        "items": [{"authorization": SECRET}, {"password": SECRET}],
    }

    response = asyncio.run(gateway.invoke(make_request(arguments=arguments)))

    assert response.decision is AuthorizationDecision.ALLOW
    records = ledger.snapshot()
    assert len(records) == 1
    serialized = repr(records) + repr(records[0].record_hash)
    assert SECRET not in serialized
    assert "[omitted]" == records[0].resource_scope
    assert ledger.verify()


def test_gateway_exception_text_is_not_copied_into_audit() -> None:
    base, permissions, provider = make_gateway()
    ledger = HashChainAuditLedger()
    gateway = MCPGateway(
        base._capability_registry, base._provider_registry, permissions, audit_ledger=ledger
    )
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    provider.connection.call_tool.side_effect = RuntimeError(f"provider failed: {SECRET}")

    with pytest.raises(RuntimeError, match=SECRET):
        asyncio.run(gateway.invoke(make_request(arguments={"token": SECRET})))

    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].reason_code == "provider_call_failed"
    assert SECRET not in repr(records)
    assert ledger.verify()


def test_gateway_log_injection_in_audited_identifier_is_rejected_before_dispatch() -> None:
    base, permissions, provider = make_gateway()
    ledger = HashChainAuditLedger()
    gateway = MCPGateway(
        base._capability_registry, base._provider_registry, permissions, audit_ledger=ledger
    )
    permissions.add_policy(make_policy(AuthorizationDecision.ALLOW))
    request = make_request()
    from dataclasses import replace

    with pytest.raises(ValueError, match="safe audit identifier"):
        malicious = replace(request, principal_id="agent:planner\\nFORGED outcome=allowed")
        asyncio.run(gateway.invoke(malicious))

    provider.connection.call_tool.assert_not_awaited()
    assert ledger.snapshot() == ()


def test_ledger_rejects_unknown_outcome_and_reason_code() -> None:
    with pytest.raises(ValueError, match="outcome"):
        AuditEvent("agent:planner", "filesystem.read", "filesystem.read_file", "success", "provider_call_completed")
    with pytest.raises(ValueError, match="reason_code"):
        AuditEvent("agent:planner", "filesystem.read", "filesystem.read_file", "allowed", SECRET)
