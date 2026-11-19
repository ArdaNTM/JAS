import asyncio
from types import SimpleNamespace

import pytest

from aura_core.application.subsystem_pack2 import (
    CodingAssignment, CodingProposal, IndependentSandboxVerifier,
    LocalCodingSpecialist, LocalLaboratory, ParallelCodingCoordinator,
)


class Provider:
    def __init__(self):
        self.active = 0
        self.peak = 0

    async def complete_json(self, **kwargs):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.001)
        self.active -= 1
        return {"source": "def double(x): return x*2", "tests": "assert double(3) == 6"}


class Gateway:
    def __init__(self, *, decision="allow", result=None):
        self.calls = []
        self.decision = decision
        self.result = result if result is not None else {"status": "completed", "return_code": 0}

    async def invoke(self, request):
        from aura_core.kernel.permissions import AuthorizationDecision
        self.calls.append(request)
        return SimpleNamespace(decision=AuthorizationDecision(self.decision), result=self.result)


def _proposal():
    return asyncio.run(LocalCodingSpecialist(Provider()).propose(
        CodingAssignment("job1", "implementer", "Make doubling function")))


def test_parallel_specialists_real_async_bounded():
    provider = Provider()
    coordinator = ParallelCodingCoordinator(LocalCodingSpecialist(provider), max_concurrency=2)
    tasks = [CodingAssignment(f"job{i}", "reviewer" if i % 2 else "implementer", "Implement safe function")
             for i in range(6)]
    result = asyncio.run(coordinator.propose_many(tasks))
    assert len(result) == 6
    assert [item.job_id for item in result] == [item.job_id for item in tasks]
    assert provider.peak == 2
    for item in result:
        item.validate()


def test_parallel_denies_duplicates_and_unbounded_work():
    coordinator = ParallelCodingCoordinator(LocalCodingSpecialist(Provider()))
    with pytest.raises(ValueError, match="duplicate"):
        asyncio.run(coordinator.propose_many([CodingAssignment("same", "tester", "x"),
                                              CodingAssignment("same", "tester", "y")]))
    with pytest.raises(ValueError, match="1..8"):
        asyncio.run(coordinator.propose_many([]))
    with pytest.raises(ValueError):
        ParallelCodingCoordinator(LocalCodingSpecialist(Provider()), max_concurrency=100)


def test_role_validation_disallows_impersonated_tools():
    with pytest.raises(ValueError):
        CodingAssignment("job1", "root", "Do anything").validate()
    with pytest.raises(ValueError):
        CodingAssignment("../job", "tester", "valid").validate()


def test_verifier_requires_distinct_principal():
    with pytest.raises(ValueError, match="separate"):
        IndependentSandboxVerifier(Gateway(), verifier_principal_id="owner", producer_principal_id="owner")


def test_verifier_runs_separate_tests_only_through_gateway():
    gateway = Gateway()
    verifier = IndependentSandboxVerifier(gateway, verifier_principal_id="independent_verifier",
                                          producer_principal_id="local_coder")
    receipt = asyncio.run(verifier.verify(_proposal(), independent_tests="assert double(5)==10",
                                          approval_id="approved-1", verification_id="evidence-1"))
    assert receipt.verified
    assert gateway.calls[0].principal_id == "independent_verifier"
    assert gateway.calls[0].capability_id == "sandbox.codeact.execute"
    assert "double(5)" in gateway.calls[0].arguments["source"]


def test_verifier_fails_closed_on_denial(tmp_path):
    gateway = Gateway(decision="require_approval")
    verifier = IndependentSandboxVerifier(gateway, verifier_principal_id="reviewer", producer_principal_id="author")
    with pytest.raises(PermissionError, match="Gateway"):
        asyncio.run(verifier.verify(_proposal(), independent_tests="assert True",
                                    approval_id="approval-1", verification_id="check-1"))
    assert len(gateway.calls) == 1


def test_verifier_rejects_fake_green_claim():
    gateway = Gateway(result={"status": "failed", "return_code": 1})
    verifier = IndependentSandboxVerifier(gateway, verifier_principal_id="reviewer", producer_principal_id="author")
    receipt = asyncio.run(verifier.verify(_proposal(), independent_tests="assert False",
                                          approval_id="approval-2", verification_id="check-2"))
    assert receipt.verified is False


def test_verifier_rejects_missing_approval_and_tampering():
    verifier = IndependentSandboxVerifier(Gateway(), verifier_principal_id="reviewer", producer_principal_id="author")
    proposal = _proposal()
    with pytest.raises(ValueError, match="approval_id"):
        asyncio.run(verifier.verify(proposal, independent_tests="assert True",
                                    approval_id="", verification_id="check"))
    tampered = CodingProposal(proposal.job_id, proposal.role, proposal.source + "\nx=1", proposal.tests, proposal.digest)
    with pytest.raises(ValueError, match="digest"):
        asyncio.run(verifier.verify(tampered, independent_tests="assert True",
                                    approval_id="approval", verification_id="check"))


def test_lab_evaluates_existing_safe_expression_engine():
    lab = LocalLaboratory()
    result = lab.evaluate("x * x + 1", [{"x": 2}, {"x": 3}])
    assert result.results == (5, 10)
    assert len(result.evidence_digest) == 64
    assert lab.evaluate("x * x + 1", [{"x": 2}, {"x": 3}]).evidence_digest == result.evidence_digest


def test_lab_denies_execution_and_unbounded_cases():
    lab = LocalLaboratory()
    with pytest.raises(Exception):
        lab.evaluate("__import__('os').system('id')", [{"x": 2}])
    with pytest.raises(ValueError, match="1..16"):
        lab.evaluate("x", [{"x": i} for i in range(20)])
