"""Safe JSON-line subprocess bridge between AURA Python 3.13 and OSWorld 3.12.

The OSWorld official 3.12 dependency tree is NEVER imported in the 3.13 AURA
process. One pinned 3.12 worker receives bounded structured operations over
anonymous stdio pipes, never HTTP or TCP. No token, DB path, Owner private
key, Hugging Face OAuth token or unconstrained Python source is forwarded.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, TextIO

from .isolation import BootIdentity, IsolationDenied

COMMIT = "3d778a3c9a34a079316f70df023b166700445792"
ALLOWED_ENV = frozenset({
    "PATH", "SystemRoot", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG",
})
MAX_MESSAGE = 16384


class VMBridgeError(RuntimeError):
    """Isolated worker failed, timed out or violated its response schema."""


def pinned_python(upstream: Path) -> Path:
    upstream = upstream.resolve(strict=True)
    if os.name == "nt":
        path = upstream / ".venv" / "Scripts" / "python.exe"
    else:
        path = upstream / ".venv" / "bin" / "python"
    if not path.is_file():
        raise VMBridgeError("OSWorld's separate Python 3.12 venv was not installed")
    result = subprocess.run(
        [str(path), "-I", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, timeout=10, shell=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "3.12":
        raise VMBridgeError("Pinned OSWorld venv must use Python 3.12, not AURA 3.13")
    return path


def checked_git(upstream: Path) -> None:
    def result(*args: str) -> str:
        p = subprocess.run(
            ["git", "-C", str(upstream), *args], capture_output=True,
            text=True, timeout=15, shell=False,
        )
        if p.returncode:
            raise VMBridgeError("Cannot verify upstream Git state")
        return p.stdout.strip()
    if (result("rev-parse", "HEAD") != COMMIT
            or result("describe", "--tags", "--exact-match", "HEAD") != "osworld-v2.1"):
        raise VMBridgeError("OSWorld official source must match pinned v2.1 commit and tag")


class OSWorldSubprocessVM:
    """Owner-gated operations are dispatched by the MCP provider, not here."""

    def __init__(
        self, *, upstream: Path, worker: Path, boot_timeout: int = 900,
        assets: Path | None = None, force_no_kvm: bool = False,
        website_suffix: str | None = None,
    ) -> None:
        self._upstream = upstream.resolve(strict=True)
        self._worker = worker.resolve(strict=True)
        if not self._worker.is_file() or not 300 <= boot_timeout <= 1200:
            raise VMBridgeError("Invalid pinned 3.12 worker or boot timeout")
        if not self._worker.is_relative_to(Path(__file__).resolve().parents[3] / "scripts"):
            raise VMBridgeError("Worker must be sealed in the AURA scripts directory")
        checked_git(self._upstream)
        self._python = pinned_python(self._upstream)
        self._image = self._upstream / "docker_vm_data" / "osworld-v2-ubuntu-x86.qcow2"
        if not self._image.is_file() or self._image.is_symlink():
            raise VMBridgeError(
                "Official Ubuntu QCOW2 missing; download and verify the pinned archive first"
            )
        env = {k: v for k, v in os.environ.items() if k in ALLOWED_ENV}
        self._run_id = secrets.token_hex(16)
        command = [
            str(self._python), "-I", "-u", str(self._worker),
            "--upstream", str(self._upstream),
            "--vm-image", str(self._image),
            "--boot-timeout", str(boot_timeout),
            "--run-id", self._run_id,
        ]
        if force_no_kvm:
            command.append("--no-kvm")
        if website_suffix is not None:
            if not website_suffix or len(website_suffix) > 128 or not re.fullmatch(r"[A-Za-z0-9.-]+", website_suffix):
                raise VMBridgeError("Invalid mock-site domain suffix")
            command.extend(("--website-suffix", website_suffix))
        if assets is not None:
            protected_assets = assets.resolve(strict=True)
            if not protected_assets.is_dir():
                raise VMBridgeError("Official gated assets directory unavailable")
            command.extend(("--assets", str(protected_assets)))
        self._proc = subprocess.Popen(
            command,
            cwd=self._upstream, env=env, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
            bufsize=1, close_fds=True,
        )
        self._lock = threading.RLock()
        self.boot: BootIdentity | None = None
        self.kvm_mode: str | None = None
        try:
            boot = self._read(boot_timeout + 180)
            if set(boot) != {"ok", "boot", "kvm_mode"} or boot["ok"] is not True:
                raise VMBridgeError("OSWorld worker refused boot")
            obj = boot["boot"]
            if not isinstance(obj, dict) or set(obj) != {
                "container_id", "network_id", "vm_sha256", "image",
            }:
                raise VMBridgeError("Worker did not report an exact VM identity")
            self.boot = BootIdentity(**obj)
            self.kvm_mode = boot["kvm_mode"]
            if self.kvm_mode not in ("N", "Y") or (force_no_kvm and self.kvm_mode != "N"):
                raise VMBridgeError("Unexpected KVM mode in isolated VM boot")
        except BaseException:
            self.close()
            raise

    @property
    def image(self) -> Path:
        return self._image

    def _read(self, timeout: float) -> dict[str, Any]:
        if self._proc.stdout is None:
            raise VMBridgeError("No worker stdout")
        result: list[str] = []
        error: list[BaseException] = []

        def read_line() -> None:
            try:
                result.append(self._proc.stdout.readline(MAX_MESSAGE + 1))
            except BaseException as exc:
                error.append(exc)

        reader = threading.Thread(target=read_line, daemon=True)
        reader.start()
        reader.join(timeout)
        if reader.is_alive():
            self._proc.kill()  # Unblocks pipe reader on timeout.
            reader.join(3)
            raise VMBridgeError("OSWorld worker exceeded bounded RPC timeout")
        if error or not result or not result[0] or len(result[0]) > MAX_MESSAGE:
            raise VMBridgeError("Worker disconnected or exceeded JSON response limit")
        try:
            obj = json.loads(result[0])
        except json.JSONDecodeError as exc:
            raise VMBridgeError("Worker returned malformed JSON") from exc
        if not isinstance(obj, dict) or obj.get("ok") is not True:
            reason = obj.get("error_type", "unknown") if isinstance(obj, dict) else "unknown"
            raise VMBridgeError(f"OSWorld worker rejected operation ({reason})")
        return obj

    def _call(self, data: dict[str, object], *, timeout: float = 180) -> dict[str, Any]:
        with self._lock:
            if self._proc.poll() is not None or self._proc.stdin is None:
                raise VMBridgeError("Isolated OSWorld worker is no longer alive")
            blob = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
            if len(blob) > MAX_MESSAGE - 1:
                raise VMBridgeError("Oversized OSWorld operation")
            try:
                self._proc.stdin.write(blob + "\n")
                self._proc.stdin.flush()
            except (OSError, BrokenPipeError) as exc:
                raise VMBridgeError("Worker transport closed") from exc
            return self._read(timeout)

    def reset(self, task_config: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task_config, dict):
            raise VMBridgeError("Task metadata required")
        obj = self._call({
            "op": "reset",
            "task_id": task_config.get("id"),
            "task_sha256": task_config.get("task_sha256"),
        }, timeout=300)
        if not isinstance(obj.get("instruction"), str) or not isinstance(obj.get("observation"), dict):
            raise VMBridgeError("Worker returned no official task instruction")
        task_config["instruction"] = obj["instruction"]
        return obj["observation"]

    def step_action(self, action: dict[str, Any]) -> tuple[dict[str, Any], int, bool, dict]:
        obj = self._call({"op": "step", "action": action}, timeout=30)
        if not isinstance(obj.get("observation"), dict) or type(obj.get("done")) is not bool:
            raise VMBridgeError("Worker returned invalid guest observation")
        return obj["observation"], 0, obj["done"], {}

    def evaluate(self) -> float:
        obj = self._call({"op": "evaluate"}, timeout=180)
        score = obj.get("score")
        if type(score) not in (int, float) or not 0 <= score <= 1:
            raise VMBridgeError("Official worker returned no numeric score")
        return float(score)

    def close(self) -> None:
        with self._lock:
            try:
                if self._proc.poll() is None:
                    try:
                        self._call({"op": "close"}, timeout=10)
                    except (VMBridgeError, OSError):
                        pass
                    try:
                        self._proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
            finally:
                for handle in (self._proc.stdin, self._proc.stdout):
                    if handle:
                        handle.close()
                if self._proc.poll() is None:
                    self._proc.kill()
                    self._proc.wait(timeout=5)
                # If a hard timeout killed the Python 3.12 worker, its
                # finally: block may not run. Only remove containers with
                # THIS bridge's unpredictable run label, never any others.
                self._cleanup_run_containers()

    def _cleanup_run_containers(self) -> None:
        try:
            proc = subprocess.run(
                ["docker", "ps", "-aq", "--filter",
                 f"label=aura.osworld.run_id={self._run_id}"],
                capture_output=True, text=True, timeout=15, shell=False,
            )
            if proc.returncode != 0:
                return
            for cid in proc.stdout.splitlines():
                if not re.fullmatch(r"[0-9a-f]{12,64}", cid):
                    continue
                subprocess.run(
                    ["docker", "rm", "-f", cid],
                    capture_output=True, text=True, timeout=20,
                    shell=False, check=False,
                )
            # A SIGKILL skips the 3.12 worker's volume cleanup. Only remove
            # this run's random, locally created storage, never any other
            # Docker volume. Refuse to delete a volume with wrong ownership
            # labels, and never force-detach a volume still in use.
            name = "aura-osworld-v21-storage-" + self._run_id
            inspected = subprocess.run(
                ["docker", "volume", "inspect", name],
                capture_output=True, text=True, timeout=10, shell=False,
            )
            if inspected.returncode == 0:
                value = json.loads(inspected.stdout)
                if (isinstance(value, list) and len(value) == 1
                        and value[0].get("Name") == name
                        and value[0].get("Driver") == "local"
                        and value[0].get("Labels") == {
                            "aura.osworld.run_id": self._run_id,
                            "aura.osworld.purpose": "vm-storage",
                        }):
                    subprocess.run(
                        ["docker", "volume", "rm", name],
                        capture_output=True, text=True, timeout=20,
                        shell=False, check=False,
                    )
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            pass
