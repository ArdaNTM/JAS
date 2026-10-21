"""Fail-closed Docker adapter for untrusted Python drafts.

The host never evaluates draft code. A caller must authorize each job before launch.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from aura_core.application.sandbox_contract import SandboxJob, SandboxPolicy


class SandboxUnavailable(RuntimeError):
    """No verified isolated execution environment is available."""


class SandboxAuthorizationError(PermissionError):
    """The job was not authorized through the caller's policy boundary."""


@dataclass(frozen=True, slots=True)
class SandboxResult:
    job_id: str
    status: str
    return_code: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float
    isolation: str = "docker_no_network_no_host_mounts"


Authorizer = Callable[[SandboxJob], bool]


class DockerPythonRunner:
    """Run a draft only in a digest-pinned, disposable, resource-limited container."""

    def __init__(
        self, *, policy: SandboxPolicy | None = None,
        authorizer: Authorizer | None = None, image: str | None = None,
        docker_executable: str | None = None,
    ) -> None:
        self.policy = policy or SandboxPolicy()
        self.authorizer = authorizer
        self.image = image or os.getenv("AURA_PYTHON_SANDBOX_IMAGE", "")
        self.docker_executable = docker_executable or shutil.which("docker")

    def run(self, job: SandboxJob) -> SandboxResult:
        job.validate(self.policy)
        if self.authorizer is None:
            raise SandboxAuthorizationError("Sandbox authorization callback is required")
        try:
            authorized = self.authorizer(job)
        except Exception as exc:
            raise SandboxAuthorizationError("Sandbox authorization failed closed") from exc
        if authorized is not True:
            raise SandboxAuthorizationError("Sandbox job was not authorized")
        if job.runner != "docker":
            raise SandboxUnavailable("Only the Docker runner is implemented")
        if not self.docker_executable:
            raise SandboxUnavailable("Docker executable is unavailable; no code was executed")
        if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", self.image):
            raise SandboxUnavailable("A digest-pinned AURA_PYTHON_SANDBOX_IMAGE is required")

        command = [
            self.docker_executable, "run", "--rm", "-i",
            "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--pids-limit", "32", "--memory", f"{self.policy.max_memory_mb}m",
            "--cpus", "1", "--user", "65534:65534", "--ipc", "none",
            "--ulimit", "nofile=64:64",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--env", "AURA_JOB_INPUT_JSON",
            self.image, "python", "-I", "-S", "-",
        ]
        env = os.environ.copy()
        env["AURA_JOB_INPUT_JSON"] = job.input_json
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False, close_fds=True, env=env,
            )
        except OSError as exc:
            raise SandboxUnavailable("Docker could not start; no code was executed") from exc

        captured = {"stdout": bytearray(), "stderr": bytearray()}
        overflow = threading.Event()

        def drain(pipe, key: str) -> None:
            try:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        return
                    remaining = self.policy.max_output_bytes - len(captured[key])
                    if remaining > 0:
                        captured[key].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        overflow.set()
            finally:
                pipe.close()

        readers = [
            threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        try:
            assert process.stdin is not None
            process.stdin.write(job.source.encode("utf-8"))
            process.stdin.close()
            process.wait(timeout=self.policy.max_wall_time_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            status = "timed_out"
        except (BrokenPipeError, OSError):
            process.kill()
            process.wait()
            status = "failed"
        else:
            status = "output_limit_exceeded" if overflow.is_set() else (
                "completed" if process.returncode == 0 else "failed"
            )
        finally:
            for reader in readers:
                reader.join(timeout=1)
        return SandboxResult(
            job_id=job.job_id, status=status, return_code=process.returncode,
            stdout=captured["stdout"].decode("utf-8", errors="replace"),
            stderr=captured["stderr"].decode("utf-8", errors="replace"),
            elapsed_seconds=time.monotonic() - started,
        )
