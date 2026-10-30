from __future__ import annotations

import hashlib
import hmac
import json
import inspect
from dataclasses import dataclass
from typing import Any, Protocol

from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationRequest,
    PermissionEngine,
    RiskLevel,
)
from aura_core.mcp.mcp_provider import MCPProvider
from aura_core.mcp.provider import ProviderRegistry
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.telemetry.runtime_profiler import RuntimeProfiler
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.enterprise.runtime_controls import CircuitBreaker, HashChainAuditLedger
from aura_core.enterprise.approval_store import (
    ApprovalConflict,
    ApprovalExpired,
    ApprovalStatus,
    InvalidApprovalTransition,
    SQLiteApprovalStore,
)


class ApprovalStoreProtocol(Protocol):
    def create(self, **kwargs): ...
    def get(self, approval_id: str): ...
    def consume(self, approval_id: str, **kwargs): ...


def _schema_type_matches(value: Any, expected: str) -> bool:
    predicates = {
        "object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None,
    }
    return predicates.get(expected, lambda _v: False)(value)


def _validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate the safety-relevant JSON Schema subset used for MCP tool inputs."""
    if not isinstance(schema, dict) or any(k in schema for k in ("$ref", "allOf", "anyOf", "oneOf")):
        raise ValueError(f"Unsupported or invalid input schema at {path}")
    expected = schema.get("type")
    if isinstance(expected, str) and not _schema_type_matches(value, expected):
        raise ValueError(f"Invalid argument type at {path}; expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"Argument is outside the allowed enum at {path}")
    if isinstance(value, dict):
        required, properties = schema.get("required", []), schema.get("properties", {})
        if not isinstance(required, list) or any(key not in value for key in required):
            raise ValueError(f"Missing required argument at {path}")
        if not isinstance(properties, dict):
            raise ValueError(f"Invalid object schema at {path}")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError(f"Unexpected argument at {path}")
        for key, item in value.items():
            if key in properties:
                _validate_json_schema(item, properties[key], f"{path}.{key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                _validate_json_schema(item, schema["additionalProperties"], f"{path}.{key}")
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValueError(f"Array length is invalid at {path}")
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(value):
                _validate_json_schema(item, schema["items"], f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise ValueError(f"String length is invalid at {path}")


@dataclass(frozen=True, slots=True)
class MCPGatewayRequest:
    request_id: str
    principal_id: str
    capability_id: str
    operation_id: str
    resource_scope: str
    risk_level: RiskLevel
    tool_name: str
    arguments: dict[str, Any] | None = None
    session_id: str | None = None
    task_id: str | None = None
    approval_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "request_id",
            "principal_id",
            "capability_id",
            "operation_id",
            "resource_scope",
            "tool_name",
        ):
            if not getattr(self, field_name):
                raise ValueError(
                    f"MCP gateway {field_name} is required"
                )
        if self.approval_id is not None and not self.approval_id.strip():
            raise ValueError("MCP gateway approval_id cannot be blank")


@dataclass(frozen=True, slots=True)
class MCPGatewayResponse:
    decision: AuthorizationDecision
    result: Any | None
    provider_id: str | None
    tool_name: str
    reason: str
    approval_id: str | None = None


class MCPGateway:
    """Deterministic authorization and dispatch gateway for MCP tools.

    Approval support is opt-in. When configured, approval-required calls are
    recorded as pending and remain non-dispatching until a matching, approved
    record is presented and atomically consumed. The caller must authenticate
    the human approver before invoking SQLiteApprovalStore.decide().
    """

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        provider_registry: ProviderRegistry,
        permission_engine: PermissionEngine,
        *,
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
        audit_ledger: HashChainAuditLedger | None = None,
        approval_store: ApprovalStoreProtocol | None = None,
        approval_fingerprint_key: bytes | None = None,
        event_bus: EventBus | None = None,
        profiler: RuntimeProfiler | None = None,
    ) -> None:
        if approval_store is not None:
            if not isinstance(approval_fingerprint_key, bytes) or len(approval_fingerprint_key) < 32:
                raise ValueError(
                    "approval_fingerprint_key must be at least 32 bytes when approval_store is configured"
                )
        elif approval_fingerprint_key is not None:
            raise ValueError("approval_fingerprint_key requires approval_store")

        self._capability_registry = capability_registry
        self._provider_registry = provider_registry
        self._permission_engine = permission_engine
        self._circuit_breakers = dict(circuit_breakers or {})
        self._audit_ledger = audit_ledger
        self._approval_store = approval_store
        self._approval_fingerprint_key = approval_fingerprint_key
        self._event_bus = event_bus
        self._profiler = profiler or RuntimeProfiler(publisher=self._publish_telemetry)

    def _audit(self, request: MCPGatewayRequest, *, outcome: str, reason_code: str) -> None:
        if self._audit_ledger is None:
            return
        # Deliberately metadata-only: never persist arguments, prompts, or results.
        self._audit_ledger.append(
            principal_id=request.principal_id,
            action=f"{request.capability_id}.{request.operation_id}",
            resource_scope=request.resource_scope,
            outcome=outcome,
            reason_code=reason_code,
        )

    @staticmethod
    async def _call_store(method, *args, **kwargs):
        result = method(*args, **kwargs)
        return await result if inspect.isawaitable(result) else result

    def _request_fingerprint(self, request: MCPGatewayRequest) -> str:
        # Canonicalization must be deterministic; never persist this payload.
        canonical = json.dumps(
            {
                "principal_id": request.principal_id,
                "capability_id": request.capability_id,
                "operation_id": request.operation_id,
                "resource_scope": request.resource_scope,
                "risk_level": request.risk_level.value,
                "tool_name": request.tool_name,
                "arguments": request.arguments,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        assert self._approval_fingerprint_key is not None
        return hmac.new(
            self._approval_fingerprint_key, canonical, hashlib.sha256
        ).hexdigest()

    @staticmethod
    def _policy_digest(authorization: Any) -> str:
        # Bundle-backed reasons include the immutable bundle digest. For legacy
        # policies, policy ID/version are included and must be version-bumped
        # whenever policy semantics change.
        canonical = json.dumps(
            {
                "decision": authorization.decision.value,
                "policy_id": authorization.policy_id,
                "policy_version": authorization.policy_version,
                "reason": authorization.reason,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _approval_response(
        self,
        request: MCPGatewayRequest,
        *,
        provider_id: str,
        reason: str,
        approval_id: str | None = None,
        outcome: str = "denied",
        reason_code: str = "approval_required",
    ) -> MCPGatewayResponse:
        self._audit(request, outcome=outcome, reason_code=reason_code)
        return MCPGatewayResponse(
            decision=AuthorizationDecision.REQUIRE_APPROVAL,
            result=None,
            provider_id=provider_id,
            tool_name=request.tool_name,
            reason=reason,
            approval_id=approval_id,
        )

    def _publish_telemetry(self, measurement) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(KernelEvent(
            event_type="Telemetry.MCPGatewayExecution",
            source_component="aura.mcp.gateway",
            payload=measurement.to_dict(),
        ))

    def _publish_tool_failure(self, request, provider_id: str, failure_type: str) -> None:
        if self._event_bus is None:
            return
        self._event_bus.publish(KernelEvent(event_type="ToolExecutionFailed", source_component="aura.mcp.gateway", payload={"request_id":request.request_id,"principal_id":request.principal_id,"task_id":request.task_id,"capability_id":request.capability_id,"provider_id":provider_id,"tool_name":request.tool_name,"failure_type":failure_type,"error_summary":"Provider dispatch failed"}, correlation_id=request.task_id or request.request_id))

    async def invoke(self, request: MCPGatewayRequest) -> MCPGatewayResponse:
        # Measure the complete gateway boundary, including denied/deferred calls.
        # No arguments, prompts, tool results, or secrets enter telemetry.
        with self._profiler.measure("mcp_gateway", "invoke"):
            return await self._invoke_authorized(request)

    async def _invoke_authorized(
        self,
        request: MCPGatewayRequest,
    ) -> MCPGatewayResponse:
        capability = self._capability_registry.resolve(
            request.capability_id
        )

        authorization = self._permission_engine.authorize(
            AuthorizationRequest(
                request_id=request.request_id,
                principal_id=request.principal_id,
                capability_id=request.capability_id,
                operation_id=request.operation_id,
                resource_scope=request.resource_scope,
                risk_level=RiskLevel(capability.definition.risk_level),
                tool_name=request.tool_name,
                session_id=request.session_id,
                task_id=request.task_id,
            )
        )

        if authorization.decision not in (
            AuthorizationDecision.ALLOW,
            AuthorizationDecision.REQUIRE_APPROVAL,
        ):
            reason_code = (
                "authorization_denied"
                if authorization.decision is AuthorizationDecision.DENY
                else "authorization_deferred"
            )
            self._audit(request, outcome="denied", reason_code=reason_code)
            return MCPGatewayResponse(
                decision=authorization.decision,
                result=None,
                provider_id=capability.definition.provider_id,
                tool_name=request.tool_name,
                reason=authorization.reason,
            )

        if authorization.decision is AuthorizationDecision.REQUIRE_APPROVAL:
            if self._approval_store is None:
                self._audit(request, outcome="denied", reason_code="approval_required")
                return MCPGatewayResponse(
                    decision=authorization.decision,
                    result=None,
                    provider_id=capability.definition.provider_id,
                    tool_name=request.tool_name,
                    reason=authorization.reason,
                )

            try:
                fingerprint = self._request_fingerprint(request)
                policy_digest = self._policy_digest(authorization)
                if request.approval_id is None:
                    record = await self._call_store(self._approval_store.create,
                        principal_id=request.principal_id,
                        capability_id=request.capability_id,
                        operation_id=request.operation_id,
                        resource_scope=request.resource_scope,
                        request_fingerprint=fingerprint,
                        policy_digest=policy_digest,
                    )
                    return self._approval_response(
                        request,
                        provider_id=capability.definition.provider_id,
                        reason="Approval requested; provider dispatch was not performed",
                        approval_id=record.approval_id,
                        outcome="pending",
                    )

                record = await self._call_store(self._approval_store.get, request.approval_id)
                if record is None:
                    return self._approval_response(
                        request,
                        provider_id=capability.definition.provider_id,
                        reason="Approval record not found; provider dispatch was not performed",
                        reason_code="approval_not_found",
                    )
                consumed = await self._call_store(self._approval_store.consume,
                    request.approval_id,
                    expected_version=record.version,
                    principal_id=request.principal_id,
                    capability_id=request.capability_id,
                    operation_id=request.operation_id,
                    resource_scope=request.resource_scope,
                    request_fingerprint=fingerprint,
                    policy_digest=policy_digest,
                )
                if consumed.status is not ApprovalStatus.CONSUMED:
                    return self._approval_response(
                        request,
                        provider_id=capability.definition.provider_id,
                        reason="Approval was not consumed; provider dispatch was not performed",
                        reason_code="approval_not_consumed",
                    )
            except (ApprovalConflict, ApprovalExpired, InvalidApprovalTransition, KeyError, ValueError, TypeError):
                return self._approval_response(
                    request,
                    provider_id=capability.definition.provider_id,
                    reason="Approval validation failed; provider dispatch was not performed",
                    reason_code="approval_validation_failed",
                )
            except Exception:
                return self._approval_response(
                    request,
                    provider_id=capability.definition.provider_id,
                    reason="Approval store unavailable; provider dispatch was not performed",
                    reason_code="approval_store_unavailable",
                    outcome="error",
                )

        try:
            provider = self._provider_registry.resolve(
                capability.definition.provider_id
            )
            if not callable(getattr(provider, "list_tools", None)) or not callable(getattr(provider, "call_tool", None)):
                raise TypeError("Resolved provider is not an MCPProvider")
        except Exception:
            self._audit(
                request,
                outcome="error",
                reason_code="provider_resolution_failed",
            )
            raise

        breaker = self._circuit_breakers.get(capability.definition.provider_id)
        if capability.definition.tool_name and request.tool_name != capability.definition.tool_name:
            self._audit(request, outcome="denied", reason_code="tool_binding_or_schema_invalid")
            return MCPGatewayResponse(
                decision=AuthorizationDecision.DENY, result=None,
                provider_id=capability.definition.provider_id, tool_name=request.tool_name,
                reason="Tool is not bound to this capability or its arguments failed schema validation",
            )
        # Provider discovery is itself a provider operation and may raise ValueError.
        # Never mistake such an exception for a client-side schema rejection.
        try:
            discovered = await provider.list_tools()
        except Exception as exc:
            self._audit(request, outcome="unknown", reason_code="provider_dispatch_outcome_unknown")
            self._publish_tool_failure(request, capability.definition.provider_id, type(exc).__name__)
            raise
        tool = next((item for item in discovered if item.name == request.tool_name), None)
        if tool is None:
            self._audit(request, outcome="denied", reason_code="tool_binding_or_schema_invalid")
            return MCPGatewayResponse(
                decision=AuthorizationDecision.DENY, result=None,
                provider_id=capability.definition.provider_id, tool_name=request.tool_name,
                reason="Tool is not bound to this capability or its arguments failed schema validation",
            )
        arguments = request.arguments if request.arguments is not None else {}
        try:
            _validate_json_schema(arguments, tool.input_schema)
        except (ValueError, TypeError):
            self._audit(request, outcome="denied", reason_code="tool_binding_or_schema_invalid")
            return MCPGatewayResponse(
                decision=AuthorizationDecision.DENY, result=None,
                provider_id=capability.definition.provider_id, tool_name=request.tool_name,
                reason="Tool is not bound to this capability or its arguments failed schema validation",
            )

        grant = DispatchGrant(
            principal_id=request.principal_id, capability_id=request.capability_id,
            tool_name=request.tool_name,
            approval_consumed=(authorization.decision is AuthorizationDecision.REQUIRE_APPROVAL),
            risk_level=RiskLevel(capability.definition.risk_level).value,
        )
        token = enter_dispatch(grant)
        try:
            if breaker is None:
                result = await provider.call_tool(request.tool_name, arguments)
            else:
                result = await breaker.call(lambda: provider.call_tool(request.tool_name, arguments))
        except Exception as exc:
            self._audit(request, outcome="unknown", reason_code="provider_dispatch_outcome_unknown")
            self._publish_tool_failure(request, capability.definition.provider_id, type(exc).__name__)
            raise
        finally:
            leave_dispatch(token)
        if getattr(result, "isError", False) is True or (
            isinstance(result, dict) and result.get("isError") is True
        ):
            self._publish_tool_failure(request, capability.definition.provider_id, "MCPToolError")
            self._audit(request, outcome="error", reason_code="provider_tool_error")
            return MCPGatewayResponse(
                decision=AuthorizationDecision.ALLOW,
                result={"status": "failed", "error": "MCP tool execution failed"},
                provider_id=capability.definition.provider_id,
                tool_name=request.tool_name,
                reason="MCP tool execution failed; reflection event published",
            )

        self._audit(request, outcome="allowed", reason_code="provider_call_completed")
        return MCPGatewayResponse(
            decision=AuthorizationDecision.ALLOW,
            result=result,
            provider_id=capability.definition.provider_id,
            tool_name=request.tool_name,
            reason="MCP tool invocation completed",
        )
