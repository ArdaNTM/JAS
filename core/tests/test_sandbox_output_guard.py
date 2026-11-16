"""Fake-process regression tests for sandbox output and argv boundaries.

These tests never launch Docker or execute untrusted source code.
"""
from __future__ import annotations

import io

import pytest

from aura_core.application.sandbox_contract import SandboxJob, SandboxPolicy
from aura_core.application.sandbox_runner import (
    DockerPythonRunner, SandboxAuthorizationError, SandboxUnavailable,
)

_SAFE_IMAGE = "python:3.12-alpine@sha256:" + "a" * 64


def _job() -> SandboxJob:
    return SandboxJob(
        job_id="safety-test",
        principal_id="authenticated-owner",
        runner="docker",
        source="print(1)",
        input_json='{"mode":"test"}',
        authorization_id="explicit-gateway-policy",
    )


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, return_code: int = 0):
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = return_code
        self.killed = False

    def wait(self, timeout=None):
        # Deliberately return before the reader threads finish.
        return self.returncode

    def kill(self):
        self.killed = True


def _runner(*, output_bytes=128, image=_SAFE_IMAGE, authorizer=None):
    return DockerPythonRunner(
        image=image, docker_executable="docker",
        policy=SandboxPolicy(max_output_bytes=output_bytes),
        authorizer=authorizer or (lambda _job: True),
    )


def test_combined_stdout_stderr_is_bounded_and_not_misclassified(monkeypatch):
    seen = []
    process = FakeProcess(b"x" * 4000, b"y" * 4000)
    monkeypatch.setattr(
        "aura_core.application.sandbox_runner.subprocess.Popen",
        lambda command, **kwargs: (seen.append((command, kwargs)) or process),
    )
    result = _runner(output_bytes=128).run(_job())
    assert result.status == "output_limit_exceeded"
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= 128
    assert result.return_code == 0
    assert len(seen) == 1
    command, kwargs = seen[0]
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--security-opt") + 1] == "no-new-privileges:true"
    assert kwargs["shell"] is False
    assert _job().source not in command


def test_small_outputs_are_preserved_and_successful(monkeypatch):
    process = FakeProcess(b"ok\n", b"safe\n")
    monkeypatch.setattr("aura_core.application.sandbox_runner.subprocess.Popen", lambda *_a, **_k: process)
    result = _runner(output_bytes=128).run(_job())
    assert result.status == "completed"
    assert result.stdout == "ok\n"
    assert result.stderr == "safe\n"


def test_nonzero_exit_is_failure_not_success(monkeypatch):
    process = FakeProcess(b"", b"rejected", return_code=1)
    monkeypatch.setattr("aura_core.application.sandbox_runner.subprocess.Popen", lambda *_a, **_k: process)
    result = _runner().run(_job())
    assert result.status == "failed"
    assert result.return_code == 1


@pytest.mark.parametrize("image", [
    "--privileged@sha256:" + "a" * 64,
    "--volume=/host@sha256:" + "a" * 64,
    "python:latest",
    "python:3.12@sha256:" + "a" * 63,
    "python:3.12@sha256:" + "g" * 64,
    "python:3.12\n--privileged@sha256:" + "a" * 64,
    "python:3.12 @sha256:" + "a" * 64,
    "a" * 250 + "@sha256:" + "a" * 64,
])
def test_invalid_or_option_like_images_fail_before_docker(monkeypatch, image):
    called = []
    monkeypatch.setattr(
        "aura_core.application.sandbox_runner.subprocess.Popen",
        lambda *_a, **_kw: called.append(True),
    )
    with pytest.raises(SandboxUnavailable):
        _runner(image=image).run(_job())
    assert not called


def test_missing_authorization_denies_before_subprocess(monkeypatch):
    called = []
    monkeypatch.setattr(
        "aura_core.application.sandbox_runner.subprocess.Popen",
        lambda *_a, **_kw: called.append(True),
    )
    runner = DockerPythonRunner(
        image=_SAFE_IMAGE, docker_executable="docker",
        authorizer=None,
    )
    with pytest.raises(SandboxAuthorizationError):
        runner.run(_job())
    assert not called


def test_explicit_denial_prevents_subprocess_even_with_safe_digest(monkeypatch):
    called = []
    monkeypatch.setattr(
        "aura_core.application.sandbox_runner.subprocess.Popen",
        lambda *_a, **_kw: called.append(True),
    )
    with pytest.raises(SandboxAuthorizationError):
        _runner(authorizer=lambda _job: False).run(_job())
    assert not called
