"""Synthesis MCP dispatch calls the existing local InferenceService."""
import asyncio
import pytest

from aura_core.application.local_synthesis_mcp import (
    LocalSynthesisMCPProvider, CAPABILITY, TOOL,
)
from aura_core.application.service import InferenceService
from aura_core.contracts.messages import InferenceResponse
from aura_core.mcp.dispatch_context import DispatchGrant, enter_dispatch, leave_dispatch


class Model:
    def __init__(self):
        self.requests = []

    def infer(self, req):
        self.requests.append(req)
        return InferenceResponse(model=req.model, content="Özet: yerel model çalıştı.")


def test_synthesis_requires_authorized_gateway_context():
    service = InferenceService(Model())
    provider = LocalSynthesisMCPProvider(inference_service=service, model="qwen3:latest")
    with pytest.raises(PermissionError):
        asyncio.run(provider.call_tool("synthesize", {"prompt": "Özetle"}))


def test_synthesis_uses_real_inference_service_with_gateway_grant():
    runtime = Model()
    provider = LocalSynthesisMCPProvider(
        inference_service=InferenceService(runtime), model="qwen3:latest")
    grant = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY,
        tool_name=TOOL, risk_level="low", approval_consumed=False,
    ))
    try:
        result = asyncio.run(provider.call_tool("synthesize", {"prompt": "Neler öğrendik?"}))
    finally:
        leave_dispatch(grant)
    assert result["content"] == "Özet: yerel model çalıştı."
    assert len(runtime.requests) == 1
    assert runtime.requests[0].model == "qwen3:latest"
    assert result["tool_execution_performed"] is False


def test_synthesis_rejects_nonbounded_arguments():
    provider = LocalSynthesisMCPProvider(inference_service=InferenceService(Model()), model="qwen3")
    grant = enter_dispatch(DispatchGrant(
        principal_id="local_owner", capability_id=CAPABILITY,
        tool_name=TOOL, risk_level="low", approval_consumed=False,
    ))
    try:
        with pytest.raises(ValueError):
            asyncio.run(provider.call_tool("synthesize", {"prompt": ""}))
        with pytest.raises(ValueError):
            asyncio.run(provider.call_tool("synthesize", {"prompt": "a", "shell": "rm -rf"}))
    finally:
        leave_dispatch(grant)
