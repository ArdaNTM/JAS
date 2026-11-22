"""Bounded per-package Windows MCP Python environment installer.

Called *only* by a separately running attestor after verifying signed Owner
allow_local_windows_process consent. No source package, setup.py, backend or
editable project is installed. Registry index fetches only wheel distributions;
no process inherits the Owner's tokens or API keys. A Job Object does not
isolate the user's files/network/DPAPI and is not asserted to do so.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

from aura_core.evolution.sandbox_preflight import SandboxUntrusted
from aura_core.evolution.external_staging import _checked_path

_MAX_REQUIREMENTS = 64
_MAX_INSTALL_SECONDS = 180
_MAX_OUTPUT = 1800
_MARKER = ".aura-isolated-env.json"


def installation_enabled() -> bool:
    """Production Windows default is true; tests can force false, never auto-grant."""
    flag = os.getenv("AURA_EVOLUTION_ISOLATED_VENV_INSTALL", "1").strip().lower()
    return os.name == "nt" and flag in {"1", "true", "yes", "on"}


class PythonVersionIncompatible(SandboxUntrusted):
    """Candidate requires a newer/incompatible Python than the host runtime."""


def _project_prefix(files: dict[str, bytes], entry: str | None) -> str:
    projects = sorted(
        (path for path in files if path == "pyproject.toml"
         or path.endswith("/pyproject.toml")),
        key=lambda path: (path.count("/"), path),
    )
    if len(projects) > 16:
        raise SandboxUntrusted("Too many project metadata files")
    if not projects:
        return ""
    if entry is None:
        return projects[0].removesuffix("pyproject.toml")
    matching = [
        path.removesuffix("pyproject.toml") for path in projects
        if entry.startswith(path.removesuffix("pyproject.toml"))
    ]
    if not matching:
        return ""
    return max(matching, key=len)


def declared_dependencies(
    files: dict[str, bytes], *, entry: str | None = None,
) -> tuple[str, ...]:
    """Parse the selected project's PEP-508 requirements, never installer flags."""
    dependencies: list[str] = []
    prefix = _project_prefix(files, entry)
    pyproject = files.get(prefix + "pyproject.toml")
    if pyproject is not None:
        if len(pyproject) > 128_000:
            raise SandboxUntrusted("Oversized pyproject metadata")
        try:
            project = tomllib.loads(pyproject.decode("utf-8-sig"))
            project_metadata = project.get("project", {})
            if not isinstance(project_metadata, dict):
                raise SandboxUntrusted("Invalid project metadata")
            requires = project_metadata.get("requires-python")
            if requires is not None:
                if not isinstance(requires, str) or len(requires) > 80:
                    raise SandboxUntrusted("Invalid requires-python declaration")
                from packaging.specifiers import SpecifierSet
                from packaging.version import Version
                if Version(".".join(map(str, sys.version_info[:3]))) not in SpecifierSet(requires):
                    host = f"{sys.version_info.major}.{sys.version_info.minor}"
                    raise PythonVersionIncompatible(
                        f"PythonVersionIncompatible: requires {requires}, host is {host}"
                    )
            declared = project_metadata.get("dependencies", [])
            if not isinstance(declared, list):
                raise SandboxUntrusted("Invalid project dependency list")
            dependencies.extend(declared)
        except (UnicodeError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, SandboxUntrusted):
                raise
            raise SandboxUntrusted("Invalid project dependency metadata") from exc
    requirements = files.get(prefix + "requirements.txt")
    if requirements is None and prefix:
        requirements = files.get("requirements.txt")
    if requirements is not None:
        if len(requirements) > 32_000:
            raise SandboxUntrusted("Oversized requirements text")
        try:
            for line in requirements.decode("utf-8-sig").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    dependencies.append(line)
        except UnicodeError as exc:
            raise SandboxUntrusted("Non-UTF8 dependency requirements") from exc
    if len(dependencies) > _MAX_REQUIREMENTS:
        raise SandboxUntrusted("Too many project dependencies")
    if not dependencies and pyproject is None and requirements is None:
        return ()
    try:
        from packaging.requirements import Requirement
        parsed = []
        for raw in dependencies:
            if not isinstance(raw, str) or not 1 <= len(raw) <= 180:
                raise SandboxUntrusted("Invalid requirement length")
            # Explicitly reject VCS, local/editable paths, config/index switches,
            # find-links and includes; only index-resolved wheel packages are allowed.
            if (raw.startswith("-") or
                any(ch in raw for ch in ("\\", "/", "@", "\\n", "\\r"))):
                raise SandboxUntrusted("Requirement may not supply a URL, path or pip flag")
            req = Requirement(raw)
            if req.url is not None:
                raise SandboxUntrusted("Direct URL dependency not permitted")
            parsed.append(str(req))
    except (ValueError, TypeError) as exc:
        if isinstance(exc, SandboxUntrusted):
            raise
        raise SandboxUntrusted("Invalid PEP-508 requirement") from exc
    # Do not override a package's declared MCP SDK constraints. FastMCP is
    # also a distinct SDK distribution and must resolve its own dependencies;
    # forcing the Core's MCP 2.x pin here can make older FastMCP releases
    # unsatisfiable even though MCP 2.x itself exists on PyPI.
    from packaging.utils import canonicalize_name
    names = {canonicalize_name(Requirement(item).name) for item in parsed}
    if "mcp" not in names and "fastmcp" not in names:
        try:
            installed_version = metadata.version("mcp")
            from packaging.version import Version
            installed_version = str(Version(installed_version))
        except (metadata.PackageNotFoundError, ValueError):
            parsed.append("mcp>=1.0.0,<2.0.0")
        else:
            parsed.append(f"mcp=={installed_version}")
    return tuple(sorted(set(parsed)))


def isolated_python(runtime: Path) -> Path | None:
    if not runtime.is_absolute() or runtime.is_symlink():
        raise SandboxUntrusted("Invalid external runtime for Python environment")
    venv = runtime / ".venv"
    if not venv.exists():
        return None
    _checked_path(venv)
    if not venv.is_dir() or venv.is_symlink():
        raise SandboxUntrusted("Unsafe package virtual environment")
    interpreter = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not interpreter.is_file() or interpreter.is_symlink():
        raise SandboxUntrusted("Invalid isolated package Python interpreter")
    return interpreter


def _installer_environment(workspace_root: Path, scratch: Path) -> dict[str, str]:
    root = os.getenv("SystemRoot") or r"C:\Windows"
    scratch.mkdir(parents=True, exist_ok=True)
    cache = workspace_root / ".uv-cache"
    cache.mkdir(parents=True, exist_ok=True)
    _checked_path(cache)
    return {
        "SystemRoot": root, "WINDIR": root,
        "PATH": os.pathsep.join((
            str(Path(sys.executable).parent), str(Path(sys.base_prefix)),
            str(Path(root) / "System32"),
        )),
        "HOME": str(scratch), "USERPROFILE": str(scratch),
        "APPDATA": str(scratch), "LOCALAPPDATA": str(scratch),
        "TEMP": str(scratch), "TMP": str(scratch),
        "UV_CACHE_DIR": str(cache), "UV_NO_CONFIG": "1",
        "UV_NO_SOURCES": "1", "UV_NO_ENV_FILE": "1",
        "UV_NO_MANAGED_PYTHON": "1", "UV_INDEX_URL": "https://pypi.org/simple",
        "PIP_CONFIG_FILE": os.devnull, "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _record_safe_install_failure(workspace_root: Path, runtime: Path, stderr: str) -> None:
    """Bounded diagnostic categories only; never persist untrusted pip text."""
    candidates = (
        ("no solution found", "Dependency resolution found no suitable wheel"),
        ("no matching distribution", "No compatible wheel on package index"),
        ("requires-python", "Dependency Python version constraint incompatible"),
        ("requires python", "Dependency Python version constraint incompatible"),
        ("failed to download", "Dependency wheel download failed"),
        ("certificate verify failed", "Package index TLS certificate verification failed"),
        ("unexpected argument", "Installed uv does not support a requested option"),
        ("no module named pip", "Fallback pip not available in the isolated environment"),
    )
    low = stderr[-4096:].lower()
    message = next((label for needle, label in candidates if needle in low),
                   "Wheel installation failed; untrusted stderr redacted")
    logs = workspace_root / "logs"
    try:
        _checked_path(logs)
        destination = logs / (runtime.name + "-local-mcp-stderr.json")
        if not destination.is_symlink():
            destination.write_text(json.dumps({
                "reason_code": "ISOLATED_DEPENDENCY_INSTALL_FAILED",
                "stderr_tail": message,
            }, sort_keys=True), encoding="utf-8")
    except (OSError, ValueError, PermissionError):
        pass


def prepare_isolated_venv(
    runtime: Path, files: dict[str, bytes], workspace_root: Path, *,
    install: bool | None = None, entry: str | None = None,
) -> Path | None:
    """Build a dependency-only virtualenv without executing source/build hooks.

    No installer is invoked when disabled. Never fall back to the Core
    interpreter after a declared dependency fails to install.
    """
    deps = declared_dependencies(files, entry=entry)
    if not deps:
        return None
    allow = installation_enabled() if install is None else install
    if not allow:
        raise SandboxUntrusted("Isolated dependency install disabled by operator")
    runtime = Path(runtime)
    workspace_root = Path(workspace_root)
    _checked_path(runtime)
    _checked_path(workspace_root)
    if (not runtime.is_dir() or not runtime.is_absolute() or
        not runtime.resolve().is_relative_to((workspace_root / "runtime").resolve())):
        raise SandboxUntrusted("Package install must stay inside external runtime")
    venv = runtime / ".venv"
    marker = runtime / _MARKER
    signature = hashlib.sha256(json.dumps({
        "dependencies": deps, "python": sys.version_info[:3],
        "source_policy": "wheels-only-no-source-build",
    }, sort_keys=True).encode()).hexdigest()
    if venv.exists() or marker.exists():
        if marker.is_symlink() or not marker.is_file():
            raise SandboxUntrusted("Existing isolated environment lacks integrity marker")
        if marker.stat().st_size > 1024:
            raise SandboxUntrusted("Oversized isolated environment marker")
        data = json.loads(marker.read_text("utf-8"))
        if data.get("dependency_sha256") != signature:
            raise SandboxUntrusted("Existing isolated environment dependencies changed")
        return isolated_python(runtime)

    with tempfile.TemporaryDirectory(prefix=".aura-install-", dir=workspace_root) as temp:
        scratch = Path(temp)
        safe_env = _installer_environment(workspace_root, scratch)
        uv = shutil.which("uv")
        interpreter = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        try:
            if uv:
                commands = [
                    [uv, "venv", str(venv), "--python", sys.executable, "--no-project"],
                    [uv, "pip", "install", "--python", str(interpreter),
                     "--no-build", "--only-binary", ":all:", *deps],
                ]
            else:
                commands = [
                    [sys.executable, "-I", "-m", "venv", str(venv)],
                    [str(interpreter), "-I", "-m", "pip", "--isolated",
                     "install", "--no-input", "--only-binary=:all:", *deps],
                ]
            for command in commands:
                result = subprocess.run(
                    command, cwd=runtime, env=safe_env, capture_output=True,
                    text=True, errors="replace", timeout=_MAX_INSTALL_SECONDS,
                    check=False,
                )
                if result.returncode != 0:
                    _record_safe_install_failure(workspace_root, runtime, result.stderr)
                    raise SandboxUntrusted(
                        "Isolated wheel install failed (exit " + str(result.returncode) + ")"
                    )
            if isolated_python(runtime) is None:
                raise SandboxUntrusted("Isolated Python environment did not materialize")
            marker.write_text(json.dumps({
                "schema": "aura.windows-isolated-venv.v1",
                "dependency_sha256": signature,
                "python_version": ".".join(map(str, sys.version_info[:3])),
            }, sort_keys=True), encoding="utf-8")
            return interpreter
        except (OSError, ValueError, subprocess.TimeoutExpired, SandboxUntrusted) as exc:
            # Never reuse a partially populated dependency tree.
            shutil.rmtree(venv, ignore_errors=True)
            marker.unlink(missing_ok=True)
            if isinstance(exc, SandboxUntrusted):
                raise
            raise SandboxUntrusted("Isolated wheel dependency installation failed") from exc
