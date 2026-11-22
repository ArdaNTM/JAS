"""Explicit Owner-opted-in Windows MCP supervision (NOT an OS security sandbox).

Windows Job Objects bound process lifetime and memory. They DO NOT isolate
network, files, DPAPI or other secrets of the same logged-on user. Only the
Owner-signed allow_local_windows_process grant may select this weaker profile.
F2.7 and the Docker attestation contract are never reused for local proofs.
"""
from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from mcp.client.stdio import StdioServerParameters

from aura_core.evolution.decision_engine import EvolutionDecisionEngine
from aura_core.evolution.external_staging import EvolutionWorkspace, _checked_path, _validated_files
from aura_core.evolution.sandbox_preflight import IsolatedMCPPreflight, SandboxUntrusted, choose_python_entrypoint
from aura_core.mcp.connection import MCPConnection

LOCAL_SCHEMA = "aura.local-windows-job-mcp-attestation.v1"
LOCAL_DOMAIN = b"AURA:LOCAL-WINDOWS-JOB-MCP-ATTESTATION:v1" + bytes([10])
LOCAL_POLICY_SHA256 = hashlib.sha256(
    b"WINDOWS-JOB-MCP:v1|explicit-owner-consent|clean-env|CREATE_SUSPENDED|"
    b"job-kill-on-close|process-memory-256MiB|static-ast|stdio|20s-handshake|"
    b"same-user-files-network-DPAPI-NOT-ISOLATED"
).hexdigest()
LOCAL_TESTS_SHA256 = hashlib.sha256(
    b"WINDOWS-JOB-HEALTH:v1|ast-checked|initialize|tools/list|"
    b"max-tools=16|runtime-tree-sha256|schema-exact"
).hexdigest()
_HEX = re.compile(r"^[0-9a-f]{64}$")


def static_python_entry(files: dict[str, bytes], hint: str) -> str:
    """Bounded package-scoped AST review; no imports or candidate execution.

    Real MCP servers split the FastMCP instance and @mcp.tool() declarations
    across modules. Each required signal must occur *inside the selected
    package*, not be stitched from unrelated neighboring packages. Only an
    independently signed, successful initialize/tools-list can activate tools.
    """
    entry = choose_python_entrypoint(files, hint)
    if (not entry.endswith(".py") or entry not in files
            or len(files[entry]) > 512_000):
        raise SandboxUntrusted("Only bounded Python MCP servers are supported locally")

    parts = entry.split("/")
    if "src" in parts:
        position = parts.index("src")
        if position + 1 >= len(parts) - 0:
            raise SandboxUntrusted("Invalid Python src package entry")
        root = "/".join(parts[:position + 2]) + "/"
    elif len(parts) > 1:
        # Scope to the declared Python package, never neighbor repositories
        # under e.g. packages/{alpha,beta}.
        root = "/".join(parts[:-1]) + "/"
    else:
        root = ""

    def in_package(path: str) -> bool:
        if not path.endswith(".py"):
            return False
        if root:
            return path.startswith(root)
        return "/" not in path or path.startswith("tools/")

    modules = sorted(path for path in files if in_package(path))
    # Larger Python-only MCP packages may split tools across many modules.
    # Retain the existing 2 MiB aggregate and 512 KiB per-file budgets.
    if entry not in modules or len(modules) > 250:
        raise SandboxUntrusted("Python MCP package AST module count exceeded")
    total_bytes = sum(len(files[path]) for path in modules)
    if total_bytes > 2_000_000 or any(len(files[path]) > 512_000 for path in modules):
        raise SandboxUntrusted("Python MCP package AST byte budget exceeded")

    sdk_import = False
    server_declared = False
    tool_declared = False
    for path in modules:
        try:
            parsed = ast.parse(files[path].decode("utf-8-sig"), filename=path)
        except (UnicodeError, SyntaxError, ValueError) as exc:
            raise SandboxUntrusted("Invalid Python MCP module AST: " + path[:160]) from exc

        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                sdk_import |= any(
                    alias.name == "mcp" or alias.name.startswith("mcp.")
                    or alias.name == "fastmcp" or alias.name.startswith("fastmcp.")
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                sdk_import |= (module == "mcp" or module.startswith("mcp.")
                               or module == "fastmcp" or module.startswith("fastmcp."))
            elif isinstance(node, ast.Call):
                callee = node.func
                server_declared |= (
                    isinstance(callee, ast.Name) and callee.id in {"FastMCP", "MCPServer"}
                ) or (
                    isinstance(callee, ast.Attribute) and callee.attr in {"FastMCP", "MCPServer"}
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    decorator = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if isinstance(decorator, ast.Attribute) and decorator.attr == "tool":
                        tool_declared = True

    if not (sdk_import and server_declared and tool_declared):
        raise SandboxUntrusted("AST lacks a declared MCP server and tool decorators")
    return entry



def local_binding(*, repository: str, source_sha256: str, tree_sha256: str,
                  tool, category: str) -> str:
    from aura_core.evolution.activation_runtime import tool_binding_digest
    return tool_binding_digest(
        repository=repository, source_sha256=source_sha256,
        tree_sha256=tree_sha256,
        image="windows-job-stdio@sha256:" + LOCAL_POLICY_SHA256,
        tool=tool, category=category,
    )


def local_sign(key, claims: dict) -> dict:
    signed = json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return {
        "schema": LOCAL_SCHEMA,
        "claims": claims,
        "signature_b64": base64.b64encode(key.sign(LOCAL_DOMAIN + signed)).decode("ascii"),
        "key_id": "operator_attestor",
    }


def verify_local(envelope: object, *, key: Ed25519PublicKey, grant: dict,
                 source_sha256: str, tree_sha256: str, binding_digest: str) -> int:
    if not grant.get("allow_local_windows_process", False):
        raise PermissionError("Owner has not signed permission for local Windows code")
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema", "claims", "signature_b64", "key_id",
    } or envelope["schema"] != LOCAL_SCHEMA or envelope["key_id"] != "operator_attestor":
        raise PermissionError("Invalid distinct Windows local attestation envelope")
    c = envelope["claims"]
    required = {
        "schema", "source_sha256", "runtime_tree_sha256", "binding_digest",
        "policy_sha256", "tests_sha256", "owner_grant_sha256", "runner_id",
        "issued_at", "expires_at", "job_object_kill_on_close", "outcome",
    }
    if not isinstance(c, dict) or set(c) != required or c["schema"] != LOCAL_SCHEMA:
        raise PermissionError("Unexpected local evidence fields")
    from aura_core.evolution.activation_delegation import canonical
    owner_digest = hashlib.sha256(canonical(grant)).hexdigest()
    now = int(time.time())
    if (c["source_sha256"] != source_sha256 or
        c["runtime_tree_sha256"] != tree_sha256 or
        c["binding_digest"] != binding_digest or
        c["policy_sha256"] != LOCAL_POLICY_SHA256 or
        c["tests_sha256"] != LOCAL_TESTS_SHA256 or
        c["owner_grant_sha256"] != owner_digest or
        c["runner_id"] != grant["attestor_runner_id"] or
        c["job_object_kill_on_close"] is not True or
        c["outcome"] != "passed" or
        type(c["issued_at"]) is not int or type(c["expires_at"]) is not int or
        not c["issued_at"] - 30 <= now < c["expires_at"] or
        not 0 < c["expires_at"] - c["issued_at"] <= 600):
        raise PermissionError("Local evidence fails Owner and job observation binding")
    try:
        signature = base64.b64decode(envelope["signature_b64"], validate=True)
        if len(signature) != 64:
            raise ValueError("wrong signature length")
        payload = json.dumps(c, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        key.verify(signature, LOCAL_DOMAIN + payload)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise PermissionError("Unsigned or forged Windows local evidence") from exc
    return c["expires_at"]


def bridge_parameters(runtime: Path, entry: str) -> StdioServerParameters:
    if os.name != "nt":
        raise PermissionError("Windows Job Object MCP can only run on Windows")
    if not runtime.is_absolute() or runtime.is_symlink() or not (runtime / entry).is_file():
        raise PermissionError("Invalid prepared local MCP runtime")
    return StdioServerParameters(
        command=sys.executable,
        args=["-B", "-u", "-m", "aura_core.evolution.windows_job_mcp",
              "--bridge", "--runtime", str(runtime), "--entry", entry],
        env={},
    )


class LocalWindowsMCPPreflight(IsolatedMCPPreflight):
    """Reuse the hardened ZIP extraction and quotas; never fabricate OCI pins."""

    def __init__(self, workspace: EvolutionWorkspace, *, timeout_seconds: int = 20,
                 owner_grant: dict | None = None, install: bool | None = None):
        self.workspace = workspace
        self.owner_grant = owner_grant
        self.install = install
        self.decisions = EvolutionDecisionEngine(workspace)
        self.runtime_root = workspace.root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        _checked_path(self.runtime_root)
        self.timeout = min(20, max(5, timeout_seconds))

    async def probe(self, package_name: str) -> dict:
        if os.name != "nt":
            raise PermissionError("Windows local MCP mode cannot be used on other hosts")
        # Do not allow a caller to turn on host execution through an env flag.
        # The attestor must independently verify the exact signed Owner grant.
        from aura_core.evolution.activation_delegation import ActivationDelegationVerifier
        signed = ActivationDelegationVerifier(self.workspace).verified_grant()
        if (signed is None or self.owner_grant is None or
            signed != self.owner_grant or
            signed.get("allow_local_windows_process") is not True):
            raise PermissionError("Signed Owner local Windows execution permission required")
        existing = self.runtime_root / package_name
        data, repository, digest = self.decisions._check_candidate(package_name)
        source = self.workspace.root / "verified" / package_name / "source.zip"
        with source.open("rb") as stream:
            files, _, _ = _validated_files(stream)
        entry = static_python_entry(files, data.get("entrypoint_hint", ""))
        if existing.exists():
            from aura_core.evolution.activation_runtime import runtime_fingerprint
            runtime_fingerprint(self.workspace, package_name)
            runtime = existing
        else:
            runtime, prepared_entry, _ = self.prepare(package_name)
            if prepared_entry != entry:
                raise SandboxUntrusted("Static entrypoint changed during preparation")
        from aura_core.evolution.isolated_venv import prepare_isolated_venv
        self._verify_runtime_capacity(0)
        # Only the separately authorized attestor may install dependencies.
        # Live Windows defaults to wheel-only isolated installation; unit tests
        # may disable it without creating any host process or network activity.
        await asyncio.to_thread(
            prepare_isolated_venv, runtime, files, self.workspace.root,
            install=self.install, entry=entry,
        )
        self._verify_runtime_capacity(0)
        connection = MCPConnection()
        try:
            await asyncio.wait_for(connection.connect_stdio(
                bridge_parameters(runtime, entry)), timeout=self.timeout)
            result = await asyncio.wait_for(connection.list_tools(), timeout=5)
            tools = result.tools if hasattr(result, "tools") else result
            if not isinstance(tools, (list, tuple)) or not 1 <= len(tools) <= 16:
                raise SandboxUntrusted("Local MCP tools/list missing or oversized")
            schemas = {}
            for tool in tools:
                name = getattr(tool, "name", None)
                schema = getattr(tool, "input_schema", None)
                if schema is None:
                    schema = getattr(tool, "inputSchema", None)
                if (not isinstance(name, str) or
                    not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) or
                    not isinstance(schema, dict) or name in schemas):
                    raise SandboxUntrusted("Invalid or duplicate MCP tool schema")
                schemas[name] = schema
            if sum(len(json.dumps(x)) for x in schemas.values()) > 32_000:
                raise SandboxUntrusted("Oversized MCP tool declarations")
            from aura_core.evolution.activation_runtime import runtime_fingerprint
            tree = runtime_fingerprint(self.workspace, package_name)
            return {"repository": repository, "source_sha256": digest,
                    "runtime_tree_sha256": tree, "status": "PREPARED_UNATTESTED",
                    "tool_schemas": schemas, "execution_profile": "windows-job-stdio"}
        finally:
            await connection.close()


def _scrubbed_windows_mcp_environment(scratch: Path) -> dict[str, str]:
    """Explicit allowlist: never copy Owner credentials or host user profile.

    The MCP/Python SDK expects a writable home/cache directory on Windows;
    redirect those paths to this bounded, disposable job-local scratch root.
    A Job Object is NOT a user-token/filesystem/network sandbox.
    """
    root = Path(os.environ.get("SystemRoot") or r"C:\Windows")
    scratch = Path(scratch).resolve()
    roaming = scratch / "AppData" / "Roaming"
    local = scratch / "AppData" / "Local"
    roaming.mkdir(parents=True, exist_ok=True)
    local.mkdir(parents=True, exist_ok=True)
    return {
        "SystemRoot": str(root),
        "WINDIR": str(root),
        "PATH": os.pathsep.join((
            str(Path(sys.executable).parent),
            str(Path(sys.base_prefix)),
            str(root / "System32"),
        )),
        "USERPROFILE": str(scratch),
        "HOMEDRIVE": scratch.drive,
        "HOMEPATH": str(scratch)[len(scratch.drive):],
        "APPDATA": str(roaming),
        "LOCALAPPDATA": str(local),
        "TEMP": str(scratch),
        "TMP": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }


def _project_script_launch(runtime: Path, entry: str) -> tuple[str, str] | None:
    """Validate the closest PEP-621 module:function without executing metadata."""
    import tomllib

    selected = runtime / entry
    if (not runtime.is_absolute() or runtime.is_symlink()
            or ".." in Path(entry).parts
            or not selected.is_relative_to(runtime)):
        raise SandboxUntrusted("Invalid Python project entry path")
    # Prefer the closest config, e.g. packages/roam/pyproject.toml, not a
    # different nested package or a root CLI with the same script name.
    for directory in (selected.parent, *selected.parents):
        if not directory.is_relative_to(runtime):
            break
        config = directory / "pyproject.toml"
        if not config.exists():
            continue
        if config.is_symlink() or not config.is_file() or config.stat().st_size > 128_000:
            raise SandboxUntrusted("Unsafe Python project metadata")
        try:
            metadata = tomllib.loads(config.read_text("utf-8-sig")).get("project", {})
            if not isinstance(metadata, dict):
                raise SandboxUntrusted("Invalid Python project metadata")
            scripts = metadata.get("scripts", {})
        except (UnicodeError, ValueError) as exc:
            raise SandboxUntrusted("Invalid project script metadata") from exc
        if not isinstance(scripts, dict) or len(scripts) > 64:
            raise SandboxUntrusted("Invalid project script declarations")
        relative = selected.relative_to(directory).as_posix()
        for name, value in scripts.items():
            if not isinstance(name, str) or not isinstance(value, str):
                raise SandboxUntrusted("Invalid PEP-621 script target")
            match = re.fullmatch(
                r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*):([A-Za-z_]\w*)",
                value.strip(),
            )
            if match is None:
                continue
            module, function = match.groups()
            suffix = module.replace(".", "/") + ".py"
            if relative in (suffix, "src/" + suffix):
                return module, function
    return None


def _isolated_entry_args(runtime: Path, entry: str, python: Path) -> list[str]:
    """Use -m for src modules so relative imports resolve in an isolated venv."""
    if (not re.fullmatch(r"[A-Za-z0-9_./-]{1,180}\.py", entry)
            or ".." in Path(entry).parts):
        raise SandboxUntrusted("Invalid isolated Python MCP entrypoint")
    parts = entry.removesuffix(".py").split("/")
    if "src" in parts:
        after = parts[parts.index("src") + 1:]
        if after and all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in after):
            module = ".".join(after[:-1] if after[-1] == "__main__" else after)
            if module:
                return [str(python), "-B", "-s", "-u", "-m", module]
    return [str(python), "-B", "-s", "-u", str(runtime / entry)]


def _package_pythonpath(runtime: Path, entry: str) -> str:
    """Never load host paths. Only package-local project/src roots are exposed."""
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,180}\.py", entry) or ".." in Path(entry).parts:
        raise SandboxUntrusted("Invalid isolated Python source tree")
    parts = entry.split("/")
    prefix = parts[:parts.index("src")] if "src" in parts else []
    bases = [runtime.joinpath(*prefix, "src"), runtime.joinpath(*prefix),
             runtime / "src", runtime]
    return os.pathsep.join(str(path) for path in dict.fromkeys(bases))



def _safe_mcp_stderr_tail(data: bytes) -> str:
    """Keep only a recognized Python import/syntax diagnostic, never raw stderr."""
    lines = data[-2048:].decode("utf-8", "replace").splitlines()
    for line in reversed(lines):
        value = line.strip()
        found = re.fullmatch(
            r"(ModuleNotFoundError|ImportError): No module named ['\"]"
            r"([A-Za-z_][A-Za-z0-9_.-]{0,100})['\"]",
            value,
        )
        if found:
            return found.group(1) + ": No module named " + found.group(2)
        if re.fullmatch(r"(?:SyntaxError|IndentationError): [A-Za-z0-9 _.,:()'-]{1,160}", value):
            return value[:200]
    return "Untrusted MCP stderr redacted"


def _write_mcp_diagnostic(runtime: Path, stderr_file: Path) -> None:
    """Diagnostics are informational, never authorization evidence."""
    if not stderr_file.is_file() or stderr_file.is_symlink():
        return
    try:
        with stderr_file.open("rb") as source:
            source.seek(max(0, stderr_file.stat().st_size - 2048))
            tail = _safe_mcp_stderr_tail(source.read(2048))
        logs = runtime.parents[1] / "logs"
        _checked_path(logs)
        destination = logs / (runtime.name + "-local-mcp-stderr.json")
        if destination.is_symlink():
            return
        destination.write_text(
            json.dumps({"reason_code": "MCP_CHILD_FAILURE", "stderr_tail": tail},
                       sort_keys=True), encoding="utf-8",
        )
    except (OSError, PermissionError, ValueError):
        return


def _bridge(runtime: Path, entry: str) -> int:
    """Start a *suspended* child, assign Job Object, then resume; no race."""
    if os.name != "nt":
        return 2
    import ctypes
    from ctypes import wintypes
    import msvcrt
    import shutil
    import subprocess
    import threading
    import tempfile
    from aura_core.evolution.isolated_venv import isolated_python

    if (not runtime.is_absolute() or runtime.is_symlink() or
        not re.fullmatch(r"[A-Za-z0-9_./-]{1,150}\.py", entry) or
        ".." in Path(entry).parts or not (runtime / entry).is_file()):
        return 2

    DWORD = wintypes.DWORD
    SIZE_T = ctypes.c_size_t
    HANDLE = wintypes.HANDLE

    class SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("nLength", DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                    ("bInheritHandle", wintypes.BOOL)]

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", DWORD), ("lpReserved", wintypes.LPWSTR),
                    ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                    ("dwX", DWORD), ("dwY", DWORD), ("dwXSize", DWORD),
                    ("dwYSize", DWORD), ("dwXCountChars", DWORD), ("dwYCountChars", DWORD),
                    ("dwFillAttribute", DWORD), ("dwFlags", DWORD),
                    ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", HANDLE),
                    ("hStdOutput", HANDLE), ("hStdError", HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE),
                    ("dwProcessId", DWORD), ("dwThreadId", DWORD)]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", DWORD), ("MinimumWorkingSetSize", SIZE_T),
                    ("MaximumWorkingSetSize", SIZE_T), ("ActiveProcessLimit", DWORD),
                    ("Affinity", SIZE_T), ("PriorityClass", DWORD),
                    ("SchedulingClass", DWORD)]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", SIZE_T), ("JobMemoryLimit", SIZE_T),
                    ("PeakProcessMemoryUsed", SIZE_T), ("PeakJobMemoryUsed", SIZE_T)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    # Explicit signatures prevent pointer/handle truncation on 64-bit Python.
    kernel.CreatePipe.argtypes = [ctypes.POINTER(HANDLE), ctypes.POINTER(HANDLE),
                                  ctypes.POINTER(SECURITY_ATTRIBUTES), DWORD]
    kernel.CreatePipe.restype = wintypes.BOOL
    kernel.SetHandleInformation.argtypes = [HANDLE, DWORD, DWORD]
    kernel.SetHandleInformation.restype = wintypes.BOOL
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = HANDLE
    kernel.SetInformationJobObject.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [HANDLE, HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.ResumeThread.argtypes = [HANDLE]
    kernel.ResumeThread.restype = DWORD
    kernel.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.POINTER(STARTUPINFO), ctypes.POINTER(PROCESS_INFORMATION)]
    kernel.CreateProcessW.restype = wintypes.BOOL
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, DWORD, DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES),
        DWORD, DWORD, HANDLE,
    ]
    kernel.CreateFileW.restype = HANDLE
    kernel.CloseHandle.argtypes = [HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [HANDLE, DWORD]
    kernel.WaitForSingleObject.restype = DWORD
    kernel.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL

    owned = []
    scratch = None
    stderr_file = None
    bridge_ok = False
    pi = PROCESS_INFORMATION()
    parent_in, child_in, parent_out, child_out, job = (HANDLE(), HANDLE(), HANDLE(), HANDLE(), HANDLE())
    try:
        sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, 1)
        if not kernel.CreatePipe(ctypes.byref(child_in), ctypes.byref(parent_in), ctypes.byref(sa), 0):
            raise OSError("Cannot create child input pipe")
        if not kernel.CreatePipe(ctypes.byref(parent_out), ctypes.byref(child_out), ctypes.byref(sa), 0):
            raise OSError("Cannot create child output pipe")
        owned.extend([child_in, parent_in, parent_out, child_out])
        if not kernel.SetHandleInformation(parent_in, 1, 0) or not kernel.SetHandleInformation(parent_out, 1, 0):
            raise OSError("Cannot isolate parent pipe handles")
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError("Job Object not available")
        owned.append(job)
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x100 | 0x8
        limits.BasicLimitInformation.ActiveProcessLimit = 4
        limits.ProcessMemoryLimit = 256 * 1024 * 1024
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError("Cannot establish mandatory Job Object limits")
        # Keep untrusted diagnostics away from the JSON-RPC stream and logs.
        # Only recognized Python import/syntax errors are released after exit.
        scratch = Path(tempfile.mkdtemp(prefix="aura-local-mcp-"))
        stderr_file = scratch / "child.stderr"
        child_err = kernel.CreateFileW(
            str(stderr_file), 0x40000000, 1, ctypes.byref(sa), 2, 0x80, None,
        )
        if not child_err or int(child_err) == ctypes.c_void_p(-1).value:
            raise OSError("Cannot create isolated MCP stderr handle")
        owned.append(child_err)
        si = STARTUPINFO()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = 0x100
        si.hStdInput, si.hStdOutput, si.hStdError = child_in, child_out, child_err
        env = _scrubbed_windows_mcp_environment(scratch)
        env["PYTHONPATH"] = _package_pythonpath(runtime, entry)
        local_python = isolated_python(runtime) or Path(sys.executable)
        if (runtime / ".venv").exists() and not (runtime / ".aura-isolated-env.json").is_file():
            raise PermissionError("Package virtual environment lacks signed runtime metadata")
        call = _project_script_launch(runtime, entry)
        if call:
            module, function = call
            # Both names were parsed as Python identifiers, never shell tokens.
            args = [str(local_python), "-B", "-s", "-u", "-c",
                    "import importlib; getattr(importlib.import_module(" +
                    repr(module) + "), " + repr(function) + ")()"]
        else:
            args = _isolated_entry_args(runtime, entry, local_python)
        packed = chr(0).join(f"{k}={v}" for k, v in sorted(env.items(), key=lambda p: p[0].lower())) + chr(0) * 2
        packed_buffer = ctypes.create_unicode_buffer(packed)
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(args))
        if not kernel.CreateProcessW(str(local_python), cmd, None, None, True,
                                    0x4 | 0x08000000 | 0x400,
                                    ctypes.cast(packed_buffer, ctypes.c_void_p), str(runtime),
                                    ctypes.byref(si), ctypes.byref(pi)):
            raise OSError("Suspended MCP process creation failed")
        owned.extend([pi.hProcess, pi.hThread])
        if not kernel.AssignProcessToJobObject(job, pi.hProcess):
            raise OSError("Cannot bind MCP to Job Object before execution")
        if kernel.ResumeThread(pi.hThread) == 0xFFFFFFFF:
            raise OSError("MCP suspended thread could not resume")
        kernel.CloseHandle(child_in)
        owned.remove(child_in)
        kernel.CloseHandle(child_out)
        owned.remove(child_out)
        import os as native_os
        reader = native_os.fdopen(msvcrt.open_osfhandle(int(parent_out.value), native_os.O_RDONLY | native_os.O_BINARY), "rb", buffering=0)
        writer = native_os.fdopen(msvcrt.open_osfhandle(int(parent_in.value), native_os.O_WRONLY | native_os.O_BINARY), "wb", buffering=0)
        owned.remove(parent_out)
        owned.remove(parent_in)
        def input_pump():
            try:
                while True:
                    data = sys.stdin.buffer.read1(65536)
                    if not data:
                        break
                    writer.write(data)
                    writer.flush()
            finally:
                writer.close()
        t = threading.Thread(target=input_pump, daemon=True)
        t.start()
        try:
            # JSON-RPC messages must be forwarded immediately, not buffered
            # until child EOF; initialize needs a response while it stays alive.
            while True:
                chunk = reader.read(65536)
                if not chunk:
                    break
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
        finally:
            reader.close()
        waited = kernel.WaitForSingleObject(pi.hProcess, 2000)
        exit_code = DWORD()
        if waited != 0 or not kernel.GetExitCodeProcess(pi.hProcess, ctypes.byref(exit_code)):
            print("Local MCP job stopped streaming before child exit", file=sys.stderr, flush=True)
            return 2
        if exit_code.value != 0:
            # Only the numeric code crosses this boundary, never untrusted stderr.
            print(f"Local MCP job child exit code: {exit_code.value}", file=sys.stderr, flush=True)
            return 2
        bridge_ok = True
        return 0
    except (OSError, ValueError, PermissionError, SandboxUntrusted) as error:
        print("Local MCP supervision failed: " + type(error).__name__ +
              f" (win32={ctypes.get_last_error()})", file=sys.stderr, flush=True)
        return 2
    finally:
        # Closing this Job handle terminates every child under KILL_ON_JOB_CLOSE.
        for handle in reversed(owned):
            if handle:
                kernel.CloseHandle(handle)
        if stderr_file is not None:
            if bridge_ok:
                log = runtime.parents[1] / "logs" / (runtime.name + "-local-mcp-stderr.json")
                if not log.is_symlink():
                    log.unlink(missing_ok=True)
            else:
                _write_mcp_diagnostic(runtime, stderr_file)
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Supervised local Windows MCP pipe bridge")
    parser.add_argument("--bridge", action="store_true", required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--entry", required=True)
    args = parser.parse_args()
    return _bridge(args.runtime, args.entry)


if __name__ == "__main__":
    # A stdio bridge owns an input reader which can still be blocked while its
    # peer disconnects. Finish Job/handle cleanup inside main(), then terminate
    # without Python's daemon-thread interpreter-finalization race.
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
