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
    """Do not import or evaluate untrusted code while inspecting its syntax."""
    entry = choose_python_entrypoint(files, hint)
    if not entry.endswith(".py") or len(files[entry]) > 512_000:
        raise SandboxUntrusted("Only bounded Python MCP servers are supported locally")
    try:
        tree = ast.parse(files[entry].decode("utf-8-sig"), filename=entry)
    except (UnicodeError, SyntaxError, ValueError) as exc:
        raise SandboxUntrusted("Invalid Python MCP server AST") from exc
    symbols = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imports = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    modules = {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and isinstance(node.module, str)
    }
    fastmcp = "FastMCP" in symbols
    declared_tools = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            (isinstance(d, ast.Attribute) and d.attr == "tool")
            or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                and d.func.attr == "tool")
            for d in node.decorator_list
        )
        for node in ast.walk(tree)
    )
    if (not fastmcp or not declared_tools or
        not any(name == "mcp" or name.startswith("mcp.") or
                name == "fastmcp" or name.startswith("fastmcp.")
                for name in imports | modules)):
        raise SandboxUntrusted("AST lacks a declared FastMCP server and tool decorators")
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

    def __init__(self, workspace: EvolutionWorkspace, *, timeout_seconds: int = 20):
        self.workspace = workspace
        self.decisions = EvolutionDecisionEngine(workspace)
        self.runtime_root = workspace.root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        _checked_path(self.runtime_root)
        self.timeout = min(20, max(5, timeout_seconds))

    async def probe(self, package_name: str) -> dict:
        if os.name != "nt":
            raise PermissionError("Windows local MCP mode cannot be used on other hosts")
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
        # Keep MCP stderr separate from stdout JSON-RPC: never merge them.
        # Suppress untrusted process diagnostics rather than logging secrets.
        nul = kernel.CreateFileW("NUL", 0x40000000, 3, ctypes.byref(sa), 3, 0x80, None)
        if not nul or int(nul) == ctypes.c_void_p(-1).value:
            raise OSError("Cannot create isolated MCP stderr handle")
        owned.append(nul)
        si = STARTUPINFO()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = 0x100
        si.hStdInput, si.hStdOutput, si.hStdError = child_in, child_out, nul
        system_root = os.environ.get("SystemRoot", r"C:\\Windows")
        env = {
            "SystemRoot": system_root, "WINDIR": system_root,
            # Windows venv redirector may need the trusted base Python DLL path.
            # Do not inherit arbitrary user PATH entries or AURA secrets.
            "PATH": os.pathsep.join((
                str(Path(sys.executable).parent),
                str(Path(sys.base_prefix)),
                str(Path(system_root) / "System32"),
            )),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        }
        scratch = Path(tempfile.gettempdir()) / "aura-local-mcp"
        scratch.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = env["TMP"] = str(scratch)
        packed = chr(0).join(f"{k}={v}" for k, v in sorted(env.items(), key=lambda p: p[0].lower())) + chr(0) * 2
        packed_buffer = ctypes.create_unicode_buffer(packed)
        cmd = ctypes.create_unicode_buffer(subprocess.list2cmdline(
            [sys.executable, "-B", "-s", "-u", str(runtime / entry)]))
        if not kernel.CreateProcessW(sys.executable, cmd, None, None, True,
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
        return 0
    except (OSError, ValueError, PermissionError) as error:
        print("Local MCP supervision failed: " + type(error).__name__ +
              f" (win32={ctypes.get_last_error()})", file=sys.stderr, flush=True)
        return 2
    finally:
        # Closing this Job handle terminates every child under KILL_ON_JOB_CLOSE.
        for handle in reversed(owned):
            if handle:
                kernel.CloseHandle(handle)


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
