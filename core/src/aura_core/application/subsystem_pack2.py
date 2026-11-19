"""Subsystem pack 2: bounded parallel local coding proposals, independent
sandbox verification, and existing safe-expression lab integration.

Model outputs never create or authorize tools. Only the existing MCPGateway
may dispatch isolated verification execution. No physical device authority.
"""
from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
_ROLES = frozenset({"architect", "implementer", "tester", "reviewer"})


def _id(value: str, label: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"invalid {label}")
    return value


@dataclass(frozen=True, slots=True)
class CodingAssignment:
    job_id: str
    role: str
    requirement: str

    def validate(self) -> None:
        _id(self.job_id, "job_id")
        if self.role not in _ROLES or not isinstance(self.requirement, str) or not 1 <= len(self.requirement) <= 6000:
            raise ValueError("invalid coding assignment")


@dataclass(frozen=True, slots=True)
class CodingProposal:
    job_id: str
    role: str
    source: str
    tests: str
    digest: str

    def validate(self) -> None:
        _id(self.job_id, "job_id")
        if self.role not in _ROLES or not isinstance(self.source, str) or not isinstance(self.tests, str):
            raise ValueError("invalid proposal")
        if not self.source.strip() or not self.tests.strip() or len(self.source.encode()) > 32000 or len(self.tests.encode()) > 12000:
            raise ValueError("invalid proposal size")
        ast.parse(self.source)
        ast.parse(self.tests)
        if hashlib.sha256((self.source + "\0" + self.tests).encode()).hexdigest() != self.digest:
            raise ValueError("proposal digest mismatch")


class LocalCodingSpecialist:
    """Real Ollama-compatible inference, with per-role prompts and JSON checks."""

    def __init__(self, provider: Any | None = None) -> None:
        if provider is None:
            from aura_core.application.ollama_completion import OllamaJSONCompletionProvider
            provider = OllamaJSONCompletionProvider()
        self.provider = provider

    async def propose(self, assignment: CodingAssignment) -> CodingProposal:
        assignment.validate()
        data = await self.provider.complete_json(
            system_prompt=(f"Act as a local {assignment.role} specialist. "
                           "Return JSON strings source and tests for a Python solution. "
                           "Do not call tools, claim tests passed, or grant privileges."),
            user_prompt=assignment.requirement,
        )
        source, tests = data.get("source"), data.get("tests")
        if not isinstance(source, str) or not isinstance(tests, str):
            raise ValueError("specialist did not return code and tests")
        proposal = CodingProposal(assignment.job_id, assignment.role, source, tests,
                                  hashlib.sha256((source + "\0" + tests).encode()).hexdigest())
        proposal.validate()
        return proposal


class ParallelCodingCoordinator:
    """Concurrently obtains untrusted proposals; does not dispatch tools."""

    def __init__(self, specialist: LocalCodingSpecialist, *, max_concurrency: int = 3) -> None:
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 4:
            raise ValueError("invalid concurrency")
        self.specialist = specialist
        self.max_concurrency = max_concurrency

    async def propose_many(self, assignments: Sequence[CodingAssignment]) -> tuple[CodingProposal, ...]:
        if not 1 <= len(assignments) <= 8:
            raise ValueError("batch must contain 1..8 agents")
        for assignment in assignments:
            assignment.validate()
        if len({assignment.job_id for assignment in assignments}) != len(assignments):
            raise ValueError("duplicate job id")
        throttle = asyncio.Semaphore(self.max_concurrency)
        outcomes: list[CodingProposal | None] = [None] * len(assignments)

        async def single(i: int, assignment: CodingAssignment) -> None:
            async with throttle:
                outcomes[i] = await self.specialist.propose(assignment)

        async with asyncio.TaskGroup() as group:
            for i, assignment in enumerate(assignments):
                group.create_task(single(i, assignment))
        return tuple(value for value in outcomes if value is not None)


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    proposal_digest: str
    tests_digest: str
    verified: bool
    execution_status: str
    return_code: int | None


class IndependentSandboxVerifier:
    """Executes separately supplied tests through approval-only CodeAct.

    Caller must authenticate verifier principal separately; a model-produced
    approval claim is not accepted. A non-ALLOW Gateway result fails closed.
    """

    def __init__(self, gateway: Any, *, verifier_principal_id: str,
                 producer_principal_id: str, resource_scope: str = "local_default") -> None:
        self.gateway = gateway
        self.verifier = _id(verifier_principal_id, "verifier principal")
        self.producer = _id(producer_principal_id, "producer principal")
        self.resource_scope = _id(resource_scope, "scope")
        if self.verifier == self.producer:
            raise ValueError("independent verification requires a separate principal")

    async def verify(self, proposal: CodingProposal, *, independent_tests: str,
                     approval_id: str, verification_id: str) -> VerificationReceipt:
        from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
        from aura_core.mcp.gateway import MCPGatewayRequest

        proposal.validate()
        _id(approval_id, "approval_id")
        _id(verification_id, "verification_id")
        if not isinstance(independent_tests, str) or not independent_tests.strip() or len(independent_tests.encode()) > 14000:
            raise ValueError("invalid verifier tests")
        ast.parse(independent_tests)
        # No host evaluation; both source and INDEPENDENT tests remain inside Docker.
        source = ("namespace = {}\n" +
                  "exec(compile(" + repr(proposal.source) + ", '<candidate>', 'exec'), namespace)\n" +
                  "exec(compile(" + repr(independent_tests) + ", '<independent_tests>', 'exec'), namespace)\n")
        if len(source.encode()) > 63_000:
            raise ValueError("verification sandbox payload too large")
        result = await self.gateway.invoke(MCPGatewayRequest(
            request_id=f"verify-{verification_id}", principal_id=self.verifier,
            capability_id="sandbox.codeact.execute", operation_id="sandbox.codeact.execute",
            resource_scope=self.resource_scope, risk_level=RiskLevel.HIGH,
            tool_name="codeact_execute", approval_id=approval_id,
            arguments={"job_id": f"verify-{verification_id}", "source": source, "input": {}},
        ))
        if result.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError("independent verification lacked Gateway approval")
        details = result.result
        if not isinstance(details, dict):
            raise ValueError("missing real sandbox evidence")
        status, code = details.get("status"), details.get("return_code")
        verified = status == "completed" and type(code) is int and code == 0
        return VerificationReceipt(proposal.digest, hashlib.sha256(independent_tests.encode()).hexdigest(),
                                   verified, str(status), code if type(code) is int else None)


@dataclass(frozen=True, slots=True)
class LabBatch:
    expression: str
    results: tuple[Any, ...]
    evidence_digest: str


class LocalLaboratory:
    """Offline, no-I/O, bounded experiment batches using JAS's existing evaluator.

    Does not actuate physical hardware, publish network data or grant authority.
    Physical lab integration remains a separate acceptance gate.
    """

    def evaluate(self, expression: str, cases: Sequence[Mapping[str, Any]]) -> LabBatch:
        from aura_core.application.autonomy_lab import evaluate_safe_expression

        if not isinstance(expression, str) or not 1 <= len(expression) <= 2000:
            raise ValueError("invalid laboratory expression")
        if not 1 <= len(cases) <= 16:
            raise ValueError("laboratory batch must contain 1..16 cases")
        outputs = []
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError("laboratory inputs must be mappings")
            outputs.append(evaluate_safe_expression(expression, dict(case)))
        serialized = json.dumps({"expression": expression, "cases": cases, "results": outputs},
                                sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(serialized.encode("utf-8")) > 60_000:
            raise ValueError("laboratory evidence too large")
        return LabBatch(expression, tuple(outputs), hashlib.sha256(serialized.encode()).hexdigest())
