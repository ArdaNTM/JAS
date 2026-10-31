"""Explicitly approved sandbox smoke tests through MCP Gateway.

Smoke-test results are NOT trusted deployment attestations; a separate
review signer must verify provenance before skill registry activation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from aura_core.application.self_tool_synthesis import CandidateToolValidator, ToolCandidate
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.mcp.gateway import MCPGatewayRequest, MCPGatewayResponse


class Gateway(Protocol):
    async def invoke(self, request: MCPGatewayRequest) -> MCPGatewayResponse: ...


@dataclass(frozen=True, slots=True)
class SandboxSmokeReport:
    source_sha256: str
    passed: bool
    submitted_cases: int
    status: str
    independent_attestation: bool = False
    deployment_allowed: bool = False


class GovernedSandboxReview:
    """No unattended sandbox run: each candidate needs a consumed high-risk approval."""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self._validator = CandidateToolValidator()

    async def smoke_test(
        self, *, candidate: ToolCandidate, cases: list[dict[str, Any]],
        principal_id: str, approval_id: str,
    ) -> SandboxSmokeReport:
        if principal_id != "local_owner" or not approval_id:
            raise PermissionError("Local Owner high-risk Gateway approval required")
        validation = self._validator.validate(candidate)
        if not validation["valid"]:
            raise ValueError("Static candidate validation failed")
        if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
            raise ValueError("One to eight explicit test cases required")
        for case in cases:
            if not isinstance(case, dict) or set(case) != {"input", "expected"}:
                raise ValueError("Each case must supply input and expected")
            if not isinstance(case["input"], dict):
                raise ValueError("Test inputs must be JSON objects")
        serialized = json.dumps(cases, ensure_ascii=True, separators=(",", ":"))
        if len(serialized) > 8192:
            raise ValueError("Cases exceed bounded test input")
        # Test code executes only in the already configured, hardened,
        # networkless CodeAct container, never inside the Core interpreter.
        script = (
            candidate.source_code + "\nimport json\n"
            + "cases = json.loads(" + repr(serialized) + ")\n"
            + "for case in cases:\n"
            + "    assert run(case['input']) == case['expected']\n"
            + "print('AURA_REVIEW_SMOKE_PASS')\n"
        )
        request = MCPGatewayRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id="sandbox.codeact.execute",
            operation_id="sandbox.codeact.execute",
            resource_scope="sandbox:review:" + candidate.digest,
            risk_level=RiskLevel.HIGH, tool_name="codeact_execute",
            arguments={"job_id": str(uuid4()), "source": script, "input": {}},
            approval_id=approval_id,
        )
        result = await self._gateway.invoke(request)
        if result.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError("Gateway denied sandbox execution")
        output = result.result if isinstance(result.result, dict) else {}
        success = (
            output.get("status") == "completed"
            and output.get("return_code") == 0
            and output.get("stdout", "").strip() == "AURA_REVIEW_SMOKE_PASS"
        )
        # Never forward stdout, stderr, prompts or arbitrary tool results.
        return SandboxSmokeReport(
            source_sha256=candidate.digest, passed=success,
            submitted_cases=len(cases),
            status="provisional_pass" if success else "failed",
        )
