"""Regression for Piper/Kokoro speech tool schemas through HTTP -> Gateway.

Piper explicitly forbids extra arguments. The former HTTP request model
added Kokoro's `af_heart` voice even when UI only sent `{"text": ...}`,
causing a schema denial (403) despite an existing authorization policy.
No real voice model or network access is required here.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from mcp.types import CallToolResult, TextContent

from aura_core.application.api import create_api
from aura_core.config.backend import BackendConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry


class FakeTTSProvider:
    def __init__(self, *, allows_voice: bool):
        self.calls: list[tuple[str, dict]] = []
        properties = {"text": {"type": "string"}}
        if allows_voice:
            properties["voice"] = {"type": "string"}
        self.schema = {
            "type": "object",
            "properties": properties,
            "required": ["text"],
            "additionalProperties": False,
        }

    async def list_tools(self):
        return (MCPTool("synthesize", "Produce local audio", self.schema),)

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return CallToolResult(
            content=[TextContent(type="text", text="Local WAV generated")],
            structuredContent={
                "mime_type": "audio/wav",
                "audio_base64": "UklGRgAAAAA=",
            },
        )


def make_client(*, allows_voice: bool, allow_policy: bool = True,
                principal: str = "local_owner"):
    services = ServiceRegistry()
    registered = services.register(
        ServiceDefinition("local-tts-test", "1", "mcp", ServiceCategory.MCP),
        object(),
    )
    capabilities = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    fake = FakeTTSProvider(allows_voice=allows_voice)
    provider_id = "tts.kokoro" if allows_voice else "tts.piper"
    providers.register(
        ProviderDefinition(provider_id, "Local speech", "1", registered.service_id),
        fake,
    )
    capabilities.register(CapabilityDefinition(
        "speech.synthesize", "Speech synthesis", "1", "Local governed voice",
        provider_id, ProviderType.MCP, CapabilityCategory.VOICE,
        tool_name="synthesize", risk_level="low",
    ))
    engine = PermissionEngine(capabilities)
    if allow_policy:
        engine.add_policy(PermissionPolicy(
            policy_id="local-user:speech.synthesize:local_default",
            policy_version="1.0.0",
            principal_id="local_owner",
            capability_id="speech.synthesize",
            operation_id="speech.synthesize",
            resource_scope="local_default",
            authorization_level=AuthorizationLevel.EXECUTE,
            decision=AuthorizationDecision.ALLOW,
        ))
    gateway = MCPGateway(capabilities, providers, engine)

    app = create_api(
        RuntimeConfig(model="qwen3:latest"),
        BackendConfig(endpoint="http://127.0.0.1:11434", timeout=5.0),
    )
    app.state.mcp_gateway = gateway
    app.state.http_bearer_token = "t" * 40
    app.state.http_principal_id = principal
    client = TestClient(app, headers={"Authorization": "Bearer " + "t" * 40})
    return client, fake, engine


def test_piper_text_only_request_dispatches_through_existing_scope_policy():
    client, provider, engine = make_client(allows_voice=False)
    response = client.post("/api/speech/synthesize", json={"text": "Merhaba AURA"})
    assert response.status_code == 200, response.text
    assert response.json() == {
        "mime_type": "audio/wav",
        "audio_base64": "UklGRgAAAAA=",
    }
    assert provider.calls == [("synthesize", {"text": "Merhaba AURA"})]
    records = engine.audit_records()
    assert records and records[-1].decision.decision is AuthorizationDecision.ALLOW


def test_kokoro_explicit_voice_is_preserved():
    client, provider, _ = make_client(allows_voice=True)
    response = client.post("/api/speech/synthesize", json={
        "text": "Merhaba", "voice": "af_heart",
    })
    assert response.status_code == 200
    assert provider.calls == [
        ("synthesize", {"text": "Merhaba", "voice": "af_heart"})
    ]


def test_piper_rejects_explicit_unsupported_voice_without_dispatch():
    client, provider, _ = make_client(allows_voice=False)
    response = client.post("/api/speech/synthesize", json={
        "text": "Merhaba", "voice": "af_heart",
    })
    assert response.status_code == 403
    assert provider.calls == []


def test_tts_missing_policy_stays_default_deny():
    client, provider, engine = make_client(allows_voice=False, allow_policy=False)
    response = client.post("/api/speech/synthesize", json={"text": "Merhaba"})
    assert response.status_code == 403
    assert provider.calls == []
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.DENY


def test_tts_wrong_principal_is_denied_even_when_policy_exists():
    client, provider, engine = make_client(allows_voice=False, principal="another_user")
    response = client.post("/api/speech/synthesize", json={"text": "Merhaba"})
    assert response.status_code == 403
    assert provider.calls == []
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.DENY


def test_tts_requires_bearer_even_with_gateway_and_policy():
    client, provider, _ = make_client(allows_voice=False)
    response = client.post("/api/speech/synthesize", json={"text": "Merhaba"},
                           headers={"Authorization": ""})
    assert response.status_code == 401
    assert provider.calls == []
