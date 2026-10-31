"""Smoke test is permission-bound and never treated as signed attestation."""
import asyncio

import pytest

from aura_core.application.self_tool_synthesis import ToolCandidate
from aura_core.evolution.sandbox_review import GovernedSandboxReview
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.gateway import MCPGatewayResponse


def _candidate():
    return ToolCandidate(
        tool_name="safe_example",
        description="Data identity test",
        source_code="def run(data):\n    return data\n",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


def test_sandbox_requires_owner_and_explicit_high_risk_approval():
    class NeverGateway:
        async def invoke(self, request):
            raise AssertionError("Gateway must not be reached")

    async def run():
        review = GovernedSandboxReview(NeverGateway())
        for principal, approval in [("another_user", "approved"), ("local_owner", "")]:
            with pytest.raises(PermissionError):
                await review.smoke_test(
                    candidate=_candidate(),
                    cases=[{"input": {}, "expected": {}}],
                    principal_id=principal, approval_id=approval,
                )
    asyncio.run(run())


def test_sandbox_gateway_dispatch_never_mints_attestation():
    class FakeGateway:
        async def invoke(self, request):
            assert request.approval_id == "human-grant"
            assert request.capability_id == "sandbox.codeact.execute"
            assert request.tool_name == "codeact_execute"
            assert request.arguments["source"].endswith("print('AURA_REVIEW_SMOKE_PASS')\n")
            return MCPGatewayResponse(
                decision=AuthorizationDecision.ALLOW,
                result={"status": "completed", "return_code": 0,
                        "stdout": "AURA_REVIEW_SMOKE_PASS\n", "stderr": ""},
                provider_id="aura.codeact-sandbox", tool_name="codeact_execute",
                reason="approved",
            )

    async def run():
        report = await GovernedSandboxReview(FakeGateway()).smoke_test(
            candidate=_candidate(),
            cases=[{"input": {"a": 3}, "expected": {"a": 3}}],
            principal_id="local_owner", approval_id="human-grant",
        )
        assert report.passed and report.status == "provisional_pass"
        assert report.source_sha256 == _candidate().digest
        assert not report.independent_attestation and not report.deployment_allowed
    asyncio.run(run())


def test_sandbox_gateway_denial_and_invalid_cases_fail_closed():
    class Denied:
        async def invoke(self, request):
            return MCPGatewayResponse(
                decision=AuthorizationDecision.DENY, result=None,
                provider_id=None, tool_name="codeact_execute", reason="denied",
            )

    async def run():
        review = GovernedSandboxReview(Denied())
        with pytest.raises(ValueError):
            await review.smoke_test(
                candidate=_candidate(), cases=[{"input": {}}],
                principal_id="local_owner", approval_id="grant",
            )
        with pytest.raises(PermissionError):
            await review.smoke_test(
                candidate=_candidate(), cases=[{"input": {}, "expected": {}}],
                principal_id="local_owner", approval_id="grant",
            )
    asyncio.run(run())
