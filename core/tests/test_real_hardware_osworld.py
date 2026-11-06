"""Real-hardware / OSWorld live-runner safety contract regression tests.

No physical microphone, WebAuthn authenticator, Docker VM or signing key is
simulated as *production evidence*. Fake VM used here only to test that MCP
Gateway approvals cannot be bypassed; a real score requires real upstream
DesktopEnv and its official evaluator.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

def _load_script(name: str):
    """Load an operator CLI by its pinned repository path, not from sys.path."""
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location("test_cli_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Pinned hardware CLI could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # Required for Python 3.13 dataclass metadata.
    spec.loader.exec_module(module)
    return module


from aura_core.enterprise.approval_store import ApprovalStatus, SQLiteApprovalStore
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch
from aura_core.osworld.live_vm import (
    LiveEvaluationDenied, OSWorldVMMCPProvider, VMAction, evaluate_live_vm,
)
from aura_core.osworld.runtime import (
    OwnerApprovalPolling, compose_vm_gateway, policy_digest,
)


@pytest.mark.parametrize("payload", [
    {"action": "click", "x": -1, "y": 0},
    {"action": "click", "x": 1920, "y": 5},
    {"action": "click", "x": True, "y": 5},
    {"action": "type", "text": "__import__('os').system('evil')\n"},
    {"action": "type", "text": ""},
    {"action": "key", "key": "win"},
    {"action": "key", "key": "ctrl+alt+del"},
    {"action": "shell", "command": "sudo apt install x"},
    {"action": "wait", "source": "python"},
    {"action": "done", "code": "x"},
])
def test_guest_rejects_untrusted_action_escape(payload):
    with pytest.raises(LiveEvaluationDenied):
        VMAction.from_dict(payload)


def test_guest_generates_fixed_commands_without_exec():
    assert VMAction.from_dict({"action": "click", "x": 12, "y": 34}).command() == "pyautogui.click(12, 34)"
    typed = VMAction.from_dict({"action": "type", "text": "hello; __import__('os')"})
    assert typed.command().startswith("pyautogui.write(")
    assert "__import__" in typed.command()  # data only: JSON-quoted string
    assert VMAction.from_dict({"action": "done"}).command() == "DONE"
    assert VMAction.from_dict({"action": "wait"}).command() == "WAIT"


class FakeVM:
    def __init__(self):
        self.actions = []
        self.closed = False

    def reset(self, task_config):
        return {"accessibility_tree": "Safe offline fixture"}

    def step(self, command: str, pause: int = 0):
        self.actions.append(command)
        return {"accessibility_tree": "AURA VM fixture"}, 0, command == "DONE", {}

    def evaluate(self, logger):
        return 0.75

    def close(self):
        self.closed = True


def test_guest_requires_consumed_gateway_dispatch():
    async def run():
        vm, provider = FakeVM(), OSWorldVMMCPProvider(FakeVM())
        with pytest.raises(LiveEvaluationDenied):
            await provider.call_tool("osworld_guest_action", {"action": "done"})
        token = enter_dispatch(DispatchGrant(
            "local_owner", "OSWorldVM", "osworld_guest_action", False, "high"
        ))
        try:
            with pytest.raises(LiveEvaluationDenied):
                await provider.call_tool("osworld_guest_action", {"action": "done"})
        finally:
            leave_dispatch(token)
        token = enter_dispatch(DispatchGrant(
            "local_owner", "OSWorldVM", "osworld_guest_action", True, "high"
        ))
        try:
            result = await provider.call_tool("osworld_guest_action", {"action": "done"})
        finally:
            leave_dispatch(token)
        assert result["executed"] and result["done"]
    asyncio.run(run())


def test_gateway_stays_pending_without_owner_and_consumes_one_approval():
    async def run():
        vm = FakeVM()
        with SQLiteApprovalStore(":memory:") as store:
            gateway = compose_vm_gateway(
                environment=vm, store=store, fingerprint_key=b"x" * 32,
            )
            from aura_core.kernel.permissions import RiskLevel
            from aura_core.mcp.gateway import MCPGatewayRequest
            request = MCPGatewayRequest(
                request_id="run-test", principal_id="local_owner",
                capability_id="OSWorldVM", operation_id="GuestAction",
                resource_scope="osworld:v2.1:disposable_vm",
                risk_level=RiskLevel.HIGH, tool_name="osworld_guest_action",
                arguments={"action": "done"},
            )
            response = await gateway.invoke(request)
            assert response.decision is AuthorizationDecision.REQUIRE_APPROVAL
            assert response.approval_id and vm.actions == []
            approval = store.get(response.approval_id)
            assert approval.policy_digest == policy_digest()
            from dataclasses import replace
            pending = await gateway.invoke(replace(request, approval_id=response.approval_id))
            assert pending.decision is not AuthorizationDecision.ALLOW
            assert not vm.actions
            store.decide(
                approval.approval_id, expected_version=approval.version,
                approver_id="human:local-owner", decision=ApprovalStatus.APPROVED,
            )
            allowed = await gateway.invoke(replace(request, approval_id=response.approval_id))
            assert allowed.decision is AuthorizationDecision.ALLOW
            assert allowed.result["done"]
            assert vm.actions == ["DONE"]
            replay = await gateway.invoke(replace(request, approval_id=response.approval_id))
            assert replay.decision is not AuthorizationDecision.ALLOW
            assert vm.actions == ["DONE"]
    asyncio.run(run())


class FixedPlanner:
    async def next_action(self, **kwargs):
        return {"action": "done"}


class NoApproval:
    async def wait_for_owner_approval(self, approval_id, timeout_seconds):
        return False


def test_real_evaluation_aborts_without_external_owner_approval():
    async def run():
        vm = FakeVM()
        with SQLiteApprovalStore(":memory:") as store:
            gateway = compose_vm_gateway(
                environment=vm, store=store, fingerprint_key=b"y" * 32,
            )
            with pytest.raises(LiveEvaluationDenied, match="WebAuthn"):
                await evaluate_live_vm(
                    environment=vm, gateway=gateway, planner=FixedPlanner(),
                    approvals=NoApproval(),
                    task_config={"id": "unit-test", "instruction": "Do not touch host"},
                )
            assert vm.actions == []
    asyncio.run(run())


def test_live_runner_rejects_missing_real_upstream_and_firewall(tmp_path):
    inspect_real_environment = _load_script("run_osworld_v2_live").inspect_real_environment
    invalid = tmp_path / "no-osworld"
    with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
        inspect_real_environment(
            upstream=invalid, expected_commit="0"*40, assets=invalid,
            task_file=invalid, owner_db=invalid, website_suffix="example.org",
        )


def test_physical_probe_cannot_emit_hardware_approved_in_ci():
    WebAuthnProbeResult = _load_script("physical_webauthn_probe").WebAuthnProbeResult
    mic = _load_script("physical_microphone_probe")
    percentile, MicrophoneProbe = mic.percentile, mic.MicrophoneProbe
    assert percentile([10.0, 20.0, 30.0, 40.0], 0.95) == 40.0
    assert WebAuthnProbeResult(
        True, True, True, True, True, True, True,
    ).public()["hardware_verified"] is False
    assert MicrophoneProbe(40, 10, 20, 25, 40).public()["hardware_verified"] is False


def test_nonexistent_trusted_evidence_cannot_mint_hardware_verified(tmp_path):
    verify = _load_script("verify_physical_hardware").verify
    async def run():
        with pytest.raises(ValueError):
            await verify(
                evidence_path=tmp_path / "nonexistent-evidence.json",
                keys_path=tmp_path / "nonexistent-trust.json",
            )
    asyncio.run(run())


# Stage E physical-host hotfix regressions. Test doubles exercise interface
# compatibility only: they cannot sign or produce real physical evidence.

def test_fido2_2_assertion_selection_is_unwrapped_and_uv_checked():
    from types import SimpleNamespace

    probe = _load_script("physical_webauthn_probe")

    class Selection:
        def __init__(self, uv: bool):
            self.assertion = SimpleNamespace(
                response=SimpleNamespace(
                    authenticator_data=SimpleNamespace(
                        is_user_verified=lambda: uv,
                    ),
                ),
            )
            self.selected: list[int] = []

        def get_response(self, index: int):
            self.selected.append(index)
            return self.assertion

    class Server:
        def __init__(self):
            self.received = None

        def authenticate_complete(self, state, credentials, response):
            assert state == "fresh_challenge"
            assert credentials == ["local_credential"]
            assert response is not selection
            self.received = response
            # In python-fido2 2.x the return is credential data, NOT auth data.
            return object()

    selection = Selection(uv=True)
    server = Server()
    result = probe.verify_selected_assertion(
        server, "fresh_challenge", ["local_credential"], selection,
    )
    assert selection.selected == [0]
    assert server.received is result is selection.assertion

    selection = Selection(uv=False)
    with pytest.raises(probe.HardwareUnavailable, match="UV flag"):
        probe.verify_selected_assertion(
            Server(), "fresh_challenge", ["local_credential"], selection,
        )
    with pytest.raises(probe.HardwareUnavailable, match="selection"):
        probe.verify_selected_assertion(
            Server(), "fresh_challenge", ["local_credential"], object(),
        )


def test_windows_native_winmm_device_enumeration_and_48khz_fallback():
    import ctypes

    microphone = _load_script("physical_microphone_probe")

    class F:
        """ctypes-compatible WinMM function test wrapper (not an OS device)."""
        def __init__(self, fn):
            self.fn = fn
            self.argtypes = None
            self.restype = None

        def __call__(self, *args):
            return self.fn(*args)

    class FakeWinMM:
        def __init__(self):
            self.open_attempts = []
            self.queued = False
            self.started = False
            self.prepared = 0
            self.unprepared = 0

            self.waveInGetNumDevs = F(lambda: 1)
            self.waveInGetDevCapsW = F(self.get_caps)
            self.waveInGetErrorTextW = F(lambda *args: 1)
            self.waveInOpen = F(self.open)
            self.waveInStart = F(self.start)
            self.waveInStop = F(lambda handle: 0)
            self.waveInReset = F(lambda handle: 0)
            self.waveInClose = F(lambda handle: 0)
            self.waveInPrepareHeader = F(self.prepare)
            self.waveInAddBuffer = F(self.queue)
            self.waveInUnprepareHeader = F(self.unprepare)

        def get_caps(self, device_id, caps_ptr, size):
            assert int(device_id) == 0
            assert size == ctypes.sizeof(microphone.WAVEINCAPSW)
            caps = ctypes.cast(
                caps_ptr, ctypes.POINTER(microphone.WAVEINCAPSW)
            ).contents
            caps.szPname = "Example WinMM USB microphone"
            caps.wChannels = 1
            return 0

        def open(self, handle_ptr, device_id, fmt_ptr, *unused):
            fmt = ctypes.cast(
                fmt_ptr, ctypes.POINTER(microphone.WAVEFORMATEX)
            ).contents
            device, rate = int(device_id), int(fmt.nSamplesPerSec)
            self.open_attempts.append((device, rate, int(fmt.nChannels)))
            if device == microphone.WAVE_MAPPER or rate != 48000:
                return 32  # WAVERR_BADFORMAT
            ctypes.cast(
                handle_ptr, ctypes.POINTER(ctypes.c_void_p)
            ).contents.value = 0x112233
            return 0

        def prepare(self, handle, header_ptr, size):
            self.prepared += 1
            assert size == ctypes.sizeof(microphone.WAVEHDR)
            return 0

        def queue(self, handle, header_ptr, size):
            hdr = ctypes.cast(
                header_ptr, ctypes.POINTER(microphone.WAVEHDR)
            ).contents
            ctypes.memset(hdr.lpData, 8, hdr.dwBufferLength)
            hdr.dwBytesRecorded = hdr.dwBufferLength
            hdr.dwFlags |= microphone.WHDR_DONE
            self.queued = True
            return 0

        def start(self, handle):
            # Original implementation started before queueing a buffer.
            assert self.queued, "WinMM must have a queued buffer before start"
            self.started = True
            return 0

        def unprepare(self, handle, header_ptr, size):
            hdr = ctypes.cast(
                header_ptr, ctypes.POINTER(microphone.WAVEHDR)
            ).contents
            assert hdr.dwFlags & microphone.WHDR_DONE
            self.unprepared += 1
            return 0

    wave = FakeWinMM()
    enumerated = microphone.list_microphones(winmm=wave)
    assert [(d.device_id, d.max_channels) for d in enumerated] == [(0, 1)]
    assert "USB microphone" in enumerated[0].name

    result = microphone.capture_microphone(samples=30, winmm=wave)
    assert result.native_winmm and not result.hardware_verified
    assert result.sample_rate_hz == 48000 and result.channels == 1
    assert result.sample_count == result.audible_buffers == 30
    assert result.device_id == 0
    assert wave.started and wave.prepared == wave.unprepared == 30
    assert (microphone.WAVE_MAPPER, 16000, 1) in wave.open_attempts
    assert (0, 48000, 1) in wave.open_attempts

    wave = FakeWinMM()
    direct = microphone.capture_microphone(
        samples=30, device_id=0, winmm=wave,
    )
    assert direct.device_id == 0
    assert all(device == 0 for device, _, _ in wave.open_attempts)
    with pytest.raises(microphone.RealMicrophoneUnavailable, match="not enumerated"):
        microphone.capture_microphone(
            samples=30, device_id=9, winmm=FakeWinMM(),
        )


def test_winmm_unavailable_device_reports_actionable_diagnostics():
    microphone = _load_script("physical_microphone_probe")

    class F:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    class NoDevices:
        waveInGetNumDevs = F(lambda: 0)
        waveInGetDevCapsW = F(lambda *args: 0)
        waveInGetErrorTextW = F(lambda *args: 0)
        waveInOpen = F(lambda *args: 0)
        waveInStart = F(lambda *args: 0)
        waveInStop = F(lambda *args: 0)
        waveInReset = F(lambda *args: 0)
        waveInClose = F(lambda *args: 0)
        waveInPrepareHeader = F(lambda *args: 0)
        waveInAddBuffer = F(lambda *args: 0)
        waveInUnprepareHeader = F(lambda *args: 0)

    with pytest.raises(microphone.RealMicrophoneUnavailable, match="Privacy"):
        microphone.capture_microphone(samples=30, winmm=NoDevices())
