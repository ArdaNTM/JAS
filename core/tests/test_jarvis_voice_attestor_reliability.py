"""Voice transport and independent cleanup regressions; no hardware required."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from aura_core.application.full_duplex_session import FasterWhisperRecognizer, GatewaySpeechSynthesizer
from aura_core.evolution import external_staging
from aura_core.evolution.attestor_worker import IndependentMCPAttestorWorker
from aura_core.evolution.external_staging import EvolutionWorkspace, WorkspacePruneError
from aura_core.kernel.permissions import AuthorizationDecision
from aura_core.mcp.connection import MCPConnection
from aura_core.mcp.gateway import MCPGatewayResponse
from test_ui_contract import make_client


@pytest.mark.parametrize("failure", ["load", "iteration"])
def test_cuda_fallback_preserves_buffer_and_caches_cpu(monkeypatch, failure):
    models = []
    calls = []
    decoded = []
    samples = object()
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 1))
    monkeypatch.setenv("AURA_STT_BEAM_SIZE", "3")

    def decode(audio):
        decoded.append(audio)
        return samples

    class Model:
        def __init__(self, size, *, device, compute_type):
            models.append((size, device, compute_type))
            self.device = device
            if device == "cuda" and failure == "load":
                raise RuntimeError("CUDA initialization failed")

        def transcribe(self, audio, **kwargs):
            calls.append((self.device, audio, kwargs))

            def segments():
                if self.device == "cuda":
                    raise RuntimeError("CUDA lazy inference failed")
                yield SimpleNamespace(text="Merhaba")
            return segments(), object()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    recognizer = FasterWhisperRecognizer()
    monkeypatch.setattr(recognizer, "_decode_audio", decode)

    async def scenario():
        for audio in (b"first", b"second"):
            assert await recognizer.transcribe(audio, session_id="session") == "Merhaba"

    asyncio.run(scenario())
    assert models == [("small", "cuda", "float16"), ("small", "cpu", "int8")]
    assert decoded == [b"first", b"second"]
    assert all(call[1] is samples for call in calls)
    assert [call[0] for call in calls] == (["cuda", "cpu", "cpu"] if failure == "iteration" else ["cpu", "cpu"])
    assert all(call[2]["language"] == "tr" and call[2]["vad_filter"] for call in calls)


def test_invalid_audio_never_loads_model_or_triggers_gpu_retry(monkeypatch):
    recognizer = FasterWhisperRecognizer()
    def bad_decode(audio):
        raise ValueError("Invalid container")
    monkeypatch.setattr(recognizer, "_decode_audio", bad_decode)
    monkeypatch.setattr(recognizer, "_load_model", lambda *_: pytest.fail("Must not load model"))
    with pytest.raises(ValueError, match="Invalid container"):
        asyncio.run(recognizer.transcribe(b"bad", session_id="session"))


def test_mcp_cancelled_queued_request_is_not_dispatched():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        transport = AsyncMock()
        transport.__aenter__.return_value = (object(), object())
        session = AsyncMock()
        session.__aenter__.return_value = session
        calls = []

        async def call(name, *, arguments):
            calls.append(name)
            if name == "first":
                started.set()
                await release.wait()
            return SimpleNamespace(structured_content={"ok": True})

        session.call_tool.side_effect = call
        with patch("aura_core.mcp.connection.stdio_client", return_value=transport), patch(
            "aura_core.mcp.connection.ClientSession", return_value=session,
        ) as constructor:
            connection = MCPConnection(read_timeout_seconds=15)
            await connection.connect_stdio(SimpleNamespace(command="fake"))
            assert constructor.call_args.kwargs["read_timeout_seconds"] == timedelta(seconds=15)
            try:
                first = asyncio.create_task(connection.call_tool("first", {}))
                await asyncio.wait_for(started.wait(), 1)
                queued = asyncio.create_task(connection.call_tool("cancelled", {}))
                await asyncio.sleep(0)
                assert connection._requests.qsize() == 1
                queued.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await queued
                release.set()
                assert await first == {"ok": True}
                assert await connection.call_tool("next", {}) == {"ok": True}
                assert calls == ["first", "next"]
            finally:
                release.set()
                await connection.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome,status", [
    ("timeout", 504), ("denied", 403), ("empty", 502), ("error", 502), ("ok", 200),
])
def test_tts_api_distinguishes_timeout_denial_and_provider_failure(outcome, status):
    requests = []

    async def invoke(request):
        requests.append(request)
        if outcome == "timeout":
            raise TimeoutError("private path")
        if outcome == "error":
            raise RuntimeError("private path")
        return MCPGatewayResponse(
            decision=AuthorizationDecision.DENY if outcome == "denied" else AuthorizationDecision.ALLOW,
            result={"mime_type": "audio/wav", "audio_base64": "YQ=="} if outcome == "ok" else None,
            provider_id="test", tool_name="synthesize", reason="denied",
        )

    with make_client() as client:
        client.app.state.mcp_gateway = SimpleNamespace(invoke=invoke)
        response = client.post("/api/speech/synthesize", json={"text": "Merhaba"})
    assert response.status_code == status
    assert "private path" not in response.text
    assert len(requests) == 1
    assert requests[0].principal_id == "local_owner"
    assert requests[0].capability_id == "speech.synthesize"
    assert requests[0].resource_scope == "local_default"


def test_session_tts_deadline_cancels_wait_without_bypassing_gateway(monkeypatch):
    import aura_core.application.full_duplex_session as module
    real_wait = asyncio.wait_for
    observed = []

    async def short_wait(coro, timeout):
        observed.append(timeout)
        return await real_wait(coro, .01)

    async def invoke(request):
        await asyncio.sleep(100)

    monkeypatch.setattr(module.asyncio, "wait_for", short_wait)
    adapter = GatewaySpeechSynthesizer(gateway=SimpleNamespace(invoke=invoke), principal_id="local_owner")
    with pytest.raises(TimeoutError):
        asyncio.run(adapter.synthesize("Merhaba", session_id="session"))
    assert observed == [20]


def _workspace(tmp_path):
    ws = EvolutionWorkspace(tmp_path / "evolution")
    for package in ("aa__terminal", "bb__active"):
        (ws.root / "verified" / package).mkdir()
        path = ws.root / "runtime" / package
        path.mkdir(parents=True)
        (path / "data").write_text("keep until safely removed")
    ws.active.write_text(json.dumps({
        "schema": "aura.external-capabilities.v1",
        "active": [
            {"repository": "aa/terminal", "status": "REVOKED"},
            {"repository": "bb/active", "status": "ACTIVE"},
        ],
    }))
    return ws


def test_terminal_delete_denied_is_deferred_only_for_independent_scan(tmp_path, monkeypatch):
    ws = _workspace(tmp_path)
    terminal = ws.root / "runtime" / "aa__terminal"
    active = ws.root / "runtime" / "bb__active"
    calls = []

    def denied(path):
        calls.append(path)
        raise PermissionError("private path")

    monkeypatch.setattr(external_staging.shutil, "rmtree", denied)
    with pytest.raises(WorkspacePruneError) as err:
        ws.prune_permanent_evolution_artifacts()
    assert err.value.code == "PruneTerminalDeleteFailed"
    assert ws.prune_permanent_evolution_artifacts(defer_locked_terminal=True) == 0
    assert ws.last_prune_deferred == {"aa/terminal"}
    assert calls == [terminal, terminal]
    assert terminal.is_dir() and active.is_dir()

    worker = object.__new__(IndependentMCPAttestorWorker)
    worker.workspace = ws
    worker._delegation = SimpleNamespace(verified_grant=lambda: {})
    worker._decisions = SimpleNamespace(evaluate_pending=lambda **_: [
        SimpleNamespace(repository=repo, status="AUTO_APPROVED_BY_POLICY")
        for repo in ("aa/terminal", "bb/active")
    ])
    seen = []

    async def attest(package):
        seen.append(package)
        return {"repository": package.replace("__", "/")}

    worker.attest = attest
    assert asyncio.run(worker.scan()) == [{"repository": "bb/active"}]
    assert seen == ["bb__active"]
    assert worker.last_scan_error == "PruneTerminalDeleteDeferred"


def test_invalid_quarantine_fails_closed_even_with_deferral(tmp_path):
    ws = _workspace(tmp_path)
    marker = ws.root / "verified" / "aa__terminal" / "local-windows-quarantined.json"
    marker.write_text("{invalid")
    with pytest.raises(WorkspacePruneError) as err:
        ws.prune_permanent_evolution_artifacts(defer_locked_terminal=True)
    assert err.value.code == "PruneQuarantineReadFailed"
    assert (ws.root / "runtime" / "aa__terminal").is_dir()


def test_runtime_symlink_is_not_treated_as_deferred_delete(tmp_path):
    ws = _workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "sentinel"
    target.write_text("untouched")
    try:
        (ws.root / "runtime" / "aa__terminal" / "link").symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(WorkspacePruneError) as err:
        ws.prune_permanent_evolution_artifacts(defer_locked_terminal=True)
    assert err.value.code == "PruneTerminalRuntimeLink"
    assert target.read_text() == "untouched"
