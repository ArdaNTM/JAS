"""Fail-closed evolution Goal Tree and quarantined mutation proposal regressions."""
from __future__ import annotations

import asyncio
import hashlib
import time

import pytest

from aura_core.application.self_tool_synthesis import ToolCandidate
from aura_core.evolution.autonomous_analyzer import GoalProposal, AutonomousAnalyzer
from aura_core.evolution.goal_tree import GoalTreeBuilder
from aura_core.evolution.evolution_planner import EvolutionPlanner
from aura_core.evolution.mutation_engine import MutationReviewQueue
from aura_core.evolution.sandbox_review import SandboxSmokeReport


def _finding(line: int, category: str = "silent_failure") -> GoalProposal:
    return GoalProposal(
        proposal_id=hashlib.sha256(str(line).encode()).hexdigest()[:24],
        category=category, summary="Exception silently ignored",
        evidence_path="core/src/aura_core/example.py", evidence_line=line,
        evidence_sha256=hashlib.sha256(b"source").hexdigest(),
    )


def _tool(source: str = "def run(data):\n    return data\n") -> ToolCandidate:
    return ToolCandidate(
        tool_name="safe_example", description="Local pure data transform",
        source_code=source, input_schema={"type": "object"},
        output_schema={"type": "object"},
    )


def test_goal_tree_is_deterministic_and_contains_no_code_or_authority():
    proposals = [_finding(2, "maintenance_marker"), _finding(3)]
    builder = GoalTreeBuilder()
    a = builder.build(proposals).to_dict()
    b = builder.build(proposals[::-1]).to_dict()
    assert a == b
    assert a["proposal_count"] == 2
    assert [g["category"] for g in a["groups"]] == ["maintenance", "runtime_reliability"]
    assert not a["authorization_granted"]
    assert a["mode"] == "read_only_proposals"
    assert "Exception silently ignored" not in str(a)
    assert builder.build([]).proposal_count == 0
    with pytest.raises(ValueError):
        builder.build([_finding(2)] * 101)


def test_mutation_queue_stages_no_code_execution_or_live_registration():
    queue = MutationReviewQueue(max_drafts=2)
    finding_id = _finding(1).proposal_id
    cases = [{"input": {"a": 1}, "expected": {"a": 1}}]
    receipt = queue.stage(finding_id=finding_id, candidate=_tool(), test_cases=cases)
    assert receipt["status"] == "awaiting_local_owner_review"
    assert receipt["source_sha256"] == _tool().digest
    assert not receipt["runtime_imported"]
    assert not receipt["tool_registered"]
    assert not receipt["independent_attestation"]
    assert "source_code" not in str(queue.list_pending())
    assert queue.list_pending() == (receipt,)
    with pytest.raises(ValueError):
        queue.stage(finding_id=finding_id, candidate=_tool("import os\ndef run(data):\n    return data\n"), test_cases=cases)
    with pytest.raises(ValueError):
        queue.stage(finding_id=finding_id, candidate=_tool(), test_cases=[{"input": {}}])
    with pytest.raises(ValueError):
        queue.stage(finding_id="not-a-finding", candidate=_tool(), test_cases=cases)


def test_mutation_queue_bounded_revision_and_owner_approval():
    queue = MutationReviewQueue(max_revisions=2)
    record = queue.stage(finding_id=_finding(1).proposal_id, candidate=_tool(),
                         test_cases=[{"input": {}, "expected": {}}])
    revised = queue.revise(record["draft_id"], candidate=_tool("def run(data):\n    return dict(data)\n"),
                           test_cases=[{"input": {}, "expected": {}}])
    assert revised["revision"] == 2
    with pytest.raises(ValueError):
        queue.revise(revised["draft_id"], candidate=_tool(),
                     test_cases=[{"input": {}, "expected": {}}])

    class GuardedSandbox:
        def __init__(self):
            self.calls = 0

        async def smoke_test(self, *, candidate, cases, principal_id, approval_id):
            self.calls += 1
            assert principal_id == "local_owner"
            assert approval_id == "fresh-human-approval"
            assert candidate.digest == _tool().digest
            return SandboxSmokeReport(candidate.digest, True, 1, "provisional_pass")

    async def run():
        sandbox = GuardedSandbox()
        with pytest.raises(PermissionError):
            await queue.request_smoke_test(
                record["draft_id"], principal_id="agent", approval_id="fresh-human-approval",
                sandbox=sandbox,
            )
        with pytest.raises(PermissionError):
            await queue.request_smoke_test(
                record["draft_id"], principal_id="local_owner", approval_id="",
                sandbox=sandbox,
            )
        assert sandbox.calls == 0
        result = await queue.request_smoke_test(
            record["draft_id"], principal_id="local_owner",
            approval_id="fresh-human-approval", sandbox=sandbox,
        )
        assert result.passed
        assert not result.independent_attestation
        assert not result.deployment_allowed
        assert sandbox.calls == 1

    asyncio.run(run())


def test_idle_planner_exposes_goal_tree_only_after_idle_scan(tmp_path):
    source = tmp_path / "core" / "src" / "aura_core"
    source.mkdir(parents=True)
    (source / "example.py").write_text(
        "try:\n    x = 1\nexcept Exception:\n    pass\n", encoding="utf-8",
    )
    now = [time.monotonic()]
    planner = EvolutionPlanner(
        AutonomousAnalyzer(tmp_path), last_activity=lambda: now[0],
        idle_seconds=60, interval_seconds=60, max_cycles=1,
    )
    assert planner.goal_tree()["proposal_count"] == 0
    assert asyncio.run(planner.run_once()) == ()
    now[0] -= 120
    proposals = asyncio.run(planner.run_once())
    assert proposals
    tree = planner.goal_tree()
    assert tree["proposal_count"] == len(proposals)
    assert tree["groups"][0]["category"] == "runtime_reliability"
    assert not tree["authorization_granted"]
    assert asyncio.run(planner.run_once()) == ()
