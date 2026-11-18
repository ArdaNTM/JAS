"""Regression suite for trust boundaries in proactive self-improvement."""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

import pytest

from aura_core.application.self_tool_synthesis import ToolCandidate
from aura_core.evolution.autonomous_analyzer import GoalProposal
from aura_core.evolution.evolution_gateway import (
    DraftRejected, EvolutionReviewGateway,
)
from aura_core.evolution.evolution_planner import (
    EvolutionSuggestion, EvolutionTask, ProactiveEvolutionCoordinator,
)
from aura_core.evolution.mutation_engine import GovernedMutationDebugLoop
from aura_core.evolution.sandbox_review import SandboxSmokeReport
from aura_core.kernel.events import EventBus


def candidate(name: str = "safe_example") -> ToolCandidate:
    return ToolCandidate(
        tool_name=name, description="Pure data identity test",
        source_code="def run(data):\n    return data\n",
        input_schema={"type": "object"}, output_schema={"type": "object"},
    )


@pytest.mark.parametrize("principal", ["untrusted_agent", "local_default", ""])
def test_owner_guard_is_installed_as_digested_source(principal: str) -> None:
    wrapped = EvolutionReviewGateway.protected_candidate(candidate())
    code = compile(wrapped.source_code, "<test-only-pure-candidate>", "exec")
    # This test executes only a test-authored identity candidate, never a model
    # draft or any bytes loaded from a real quarantine.
    env: dict = {}
    exec(code, env)
    with pytest.raises(PermissionError, match="restricted to Local Owner"):
        env["invoke"]({"x": 1}, principal)
    assert env["invoke"]({"x": 1}, "local_owner") == {"x": 1}


def test_quarantine_requires_outside_private_directory(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    draft_dir = checkout / "core" / "src" / "aura_core" / "mcp" / "drafts"
    draft_dir.mkdir(parents=True)
    draft_dir.chmod(0o700)
    with pytest.raises(DraftRejected, match="checkout"):
        EvolutionReviewGateway(
            directory=draft_dir, checkout_root=checkout, event_bus=EventBus(),
        )


def test_review_metadata_event_and_no_generated_code_execution(
    tmp_path: Path, owner_private_dir: Path,
) -> None:
    async def run() -> None:
        checkout = tmp_path / "checkout"
        (checkout / "core/src/aura_core").mkdir(parents=True)
        events = EventBus()
        received = []
        events.subscribe("EvolutionReviewRequest", lambda event: received.append(event))
        gate = EvolutionReviewGateway(
            directory=owner_private_dir, checkout_root=checkout, event_bus=events,
        )
        draft = gate.stage(candidate(), test_count=2)
        assert len(draft.source_sha256) == 64
        manifest = gate.pending()[0]
        assert manifest["approval_granted"] is False
        assert manifest["tool_registered"] is False
        assert manifest["independent_attestation"] is False
        assert "source_code" not in manifest
        assert await events.dispatch_once()
        assert received[0].event_type == "EvolutionReviewRequest"
        assert "source_code" not in received[0].payload
        review_path = owner_private_dir / (draft.draft_id + ".review.py.txt")
        content = review_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == draft.source_sha256
        assert b"if principal != \"local_owner\"" in content
        assert not any(checkout.rglob("*.py"))
        assert gate.release_handoff()["may_run_generate_final_lock"] is False
        with pytest.raises(FileExistsError):
            gate.stage(candidate(), test_count=2)
        with pytest.raises(DraftRejected):
            gate.activate_pre_registered(
                draft_id=draft.draft_id, binding=None,
                sandbox_receipt="forged", owner_receipt="forged",
                registrar=None, owner_receipts=None, attestations=None,
                principal_id="untrusted_agent",
            )
    asyncio.run(run())


class FakeMemory:
    def __init__(self) -> None:
        self.records = []
        self.store = self

    def append(self, **kwargs):
        self.records.append(kwargs)


class FakeModel:
    def __init__(self) -> None:
        self.prompts = []

    async def complete_json(self, *, system_prompt, user_prompt):
        self.prompts.append((system_prompt, user_prompt))
        return {"category": "data_analysis", "summary": "Add a bounded parser for CSV"}


class FakeDelegate:
    def __init__(self, proposal):
        self.last_activity = lambda: -10000.0
        self.idle_seconds = 300
        self.interval_seconds = 900
        self.max_cycles = 10
        self._cycles = 0
        self._findings = {proposal.proposal_id: proposal}

    async def run_once(self):
        self._cycles += 1
        return (
            EvolutionSuggestion(
                suggestion_id="a" * 24, proposal_id=next(iter(self._findings)),
                title="CSV parser",
                evidence=(),
            ),
        )

    def status(self):
        return {"mode": "review_only", "cycles": self._cycles}

    def list_proposals(self, *, limit=20):
        return []

    def goal_tree(self):
        return {"mode": "review_only"}


def test_introspection_stores_untrusted_metadata_not_owner_authorization(tmp_path: Path):
    root = tmp_path
    permitted = root / "core/src/aura_core/application/parser.py"
    permitted.parent.mkdir(parents=True)
    permitted.write_text(
        "# TODO: add CSV parsing\n"
        "password = 'should-never-be-sent'\n"
        "def run_csv(data): return data\n",
        encoding="utf-8",
    )
    evidence = GoalProposal(
        proposal_id="e" * 24, category="maintenance_marker",
        summary="Source has a TODO", evidence_path="core/src/aura_core/application/parser.py",
        evidence_line=1, evidence_sha256="f" * 64,
    )
    model, memory = FakeModel(), FakeMemory()
    coordinator = ProactiveEvolutionCoordinator(
        FakeDelegate(evidence), model=model, memory=memory, checkout_root=root,
    )
    result = asyncio.run(coordinator.run_once())
    assert len(result) == 1 and isinstance(result[0], EvolutionTask)
    assert result[0].state == "needs_owner_review"
    assert result[0].authorization_granted is False
    assert memory.records[0]["principal_id"] == "evolution_worker"
    assert memory.records[0]["metadata"]["authorization_granted"] is False
    assert "should-never-be-sent" not in model.prompts[0][1]
    assert "redacted" in model.prompts[0][1]
    assert coordinator.status()["can_execute"] is False


def test_introspection_never_reads_kernel_or_security_files(tmp_path: Path):
    root = tmp_path
    (root / "core/src/aura_core").mkdir(parents=True)
    worker = ProactiveEvolutionCoordinator(
        FakeDelegate(GoalProposal(
            proposal_id="e" * 24, category="other",
            summary="anything", evidence_path="core/src/aura_core/kernel/permissions.py",
            evidence_line=1, evidence_sha256="f" * 64,
        )), model=FakeModel(), memory=FakeMemory(), checkout_root=root,
    )
    assert worker._excerpt("core/src/aura_core/kernel/permissions.py", 1).startswith(
        "[source excluded"
    )
    assert worker._excerpt("core/src/aura_core/security/auth.py", 1).startswith(
        "[source excluded"
    )


class FakeSandbox:
    def __init__(self, *, pass_on: int):
        self.pass_on = pass_on
        self.requests: list[tuple[str, str]] = []

    async def smoke_test(self, *, candidate, cases, principal_id, approval_id):
        self.requests.append((candidate.digest, approval_id))
        success = len(self.requests) >= self.pass_on
        return SandboxSmokeReport(
            source_sha256=candidate.digest, passed=success,
            submitted_cases=len(cases),
            status="provisional_pass" if success else "failed",
        )


class FakeReviser:
    def __init__(self):
        self.feedback = []

    async def revise(self, *, candidate, bounded_feedback, attempt):
        self.feedback.append(bounded_feedback)
        return ToolCandidate(
            tool_name=candidate.tool_name, description=candidate.description,
            source_code="def run(data):\n    return dict(data)\n",
            input_schema=candidate.input_schema, output_schema=candidate.output_schema,
        )


def test_debug_never_executes_without_each_external_owner_approval():
    async def run():
        sandbox, reviser = FakeSandbox(pass_on=2), FakeReviser()
        loop = GovernedMutationDebugLoop(sandbox=sandbox, reviser=reviser)
        test_cases = [{"input": {"a": 1}, "expected": {"a": 1}}]
        pending = await loop.debug(
            candidate=candidate(), test_cases=test_cases,
            principal_id="local_owner", owner_approvals=[],
        )
        assert pending.needs_new_approval and sandbox.requests == []
        paused = await loop.debug(
            candidate=candidate(), test_cases=test_cases,
            principal_id="local_owner", owner_approvals=["owner-consent-1"],
        )
        assert paused.status == "awaiting_owner_approval"
        assert len(sandbox.requests) == 1
        passed = await loop.debug(
            candidate=candidate(), test_cases=test_cases,
            principal_id="local_owner",
            owner_approvals=["owner-consent-2", "owner-consent-3"],
        )
        assert passed.status == "provisional_pass"
        assert not passed.deployment_allowed
        assert not passed.independent_attestation
        assert "stdout" not in reviser.feedback[0]
        with pytest.raises(PermissionError):
            await loop.debug(
                candidate=candidate(), test_cases=test_cases,
                principal_id="agent", owner_approvals=["forge"],
            )
    asyncio.run(run())
