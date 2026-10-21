from __future__ import annotations

from aura_core.application.reflexion import ExperimentBudget, ProceduralSkillLibrary, ReflexionExperimentLoop
from aura_core.application.sandbox_contract import SandboxJob
from aura_core.application.sandbox_runner import SandboxResult
from aura_core.memory.hierarchical_memory import SQLiteEpisodicMemory


class FakeRunner:
    def __init__(self, *, policy=None, authorizer=None, image=None, docker_executable=None, results=()):
        self.policy = policy
        self.authorizer = authorizer
        self.image = image
        self.docker_executable = docker_executable
        self.results = list(results)
        self.jobs = []

    def run(self, job: SandboxJob):
        self.jobs.append(job)
        if self.authorizer is None or self.authorizer(job) is not True:
            raise PermissionError("denied")
        return self.results.pop(0)


def test_reflexion_stops_after_verified_success_and_proposes_review_only_skill(tmp_path, monkeypatch):
    import aura_core.application.reflexion as module

    results = [
        SandboxResult("exp-1", "failed", 1, "", "NameError", 0.1),
        SandboxResult("exp-2", "completed", 0, "42", "", 0.1),
    ]
    source_runner = FakeRunner(results=results)
    def build_runner(**kwargs):
        source_runner.authorizer = kwargs["authorizer"]
        return source_runner

    monkeypatch.setattr(module, "DockerPythonRunner", build_runner)
    memory = SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3")
    skills = ProceduralSkillLibrary(tmp_path / "skills.sqlite3")
    revisions = []

    def revise(source, feedback, attempt):
        revisions.append((source, feedback, attempt))
        return "print(6 * 7)"

    loop = ReflexionExperimentLoop(
        runner=source_runner, memory=memory, skills=skills, revise=revise,
        verify=lambda result: result.stdout.strip() == "42",
        authorize=lambda job: job.principal_id == "p1" and job.authorization_id.startswith("reflexion:"),
        budget=ExperimentBudget(max_attempts=2, max_total_seconds=10),
    )
    outcome = loop.run(
        experiment_id="exp", principal_id="p1", task_id="t1",
        goal="calculate answer", source="print(missing_name)",
    )
    assert outcome.status == "verified_success"
    assert outcome.attempts == 2
    assert len(revisions) == 1
    pending = skills.list_pending(principal_id="p1")
    assert len(pending) == 1
    assert pending[0]["review_required"] is True
    assert pending[0]["status"] == "pending_review"
    records = memory.recall(principal_id="p1", task_id="t1")
    assert len(records) == 2
    assert all(record.untrusted for record in records)


def test_reflexion_is_bounded_and_never_promotes_unverified_skill(tmp_path, monkeypatch):
    import aura_core.application.reflexion as module

    fake = FakeRunner(results=[
        SandboxResult(f"exp-{i}", "failed", 1, "", "error", 0.1) for i in range(3)
    ])
    def build_runner(**kwargs):
        fake.authorizer = kwargs["authorizer"]
        return fake

    monkeypatch.setattr(module, "DockerPythonRunner", build_runner)
    skills = ProceduralSkillLibrary(tmp_path / "skills.sqlite3")
    loop = ReflexionExperimentLoop(
        runner=fake,
        memory=SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3"),
        skills=skills,
        revise=lambda source, feedback, attempt: source + "\n# revision",
        verify=lambda result: False,
        authorize=lambda job: True,
        budget=ExperimentBudget(max_attempts=3, max_total_seconds=10),
    )
    outcome = loop.run(
        experiment_id="bounded", principal_id="p1", task_id="t1",
        goal="try it", source="print('x')",
    )
    assert outcome.attempts == 3
    assert outcome.status == "attempt_budget_exhausted"
    assert skills.list_pending(principal_id="p1") == []


def test_reflexion_fails_closed_when_authorization_is_denied(tmp_path, monkeypatch):
    import aura_core.application.reflexion as module

    fake = FakeRunner(results=[SandboxResult("x", "completed", 0, "ok", "", 0.1)])
    monkeypatch.setattr(module, "DockerPythonRunner", lambda **kwargs: fake)
    loop = ReflexionExperimentLoop(
        runner=fake,
        memory=SQLiteEpisodicMemory(tmp_path / "episodes.sqlite3"),
        skills=ProceduralSkillLibrary(tmp_path / "skills.sqlite3"),
        revise=lambda source, feedback, attempt: source,
        verify=lambda result: True,
        authorize=lambda job: False,
    )
    outcome = loop.run(
        experiment_id="denied", principal_id="p1", task_id="t1",
        goal="try it", source="print('unsafe')",
    )
    assert outcome.status == "authorization_or_sandbox_error"
    assert outcome.attempts == 0
