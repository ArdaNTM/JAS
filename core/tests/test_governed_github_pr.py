"""JAS read-only PR status: real MCP Gateway, PermissionEngine and strict metadata."""
import asyncio
from types import SimpleNamespace

import pytest

from aura_core.application.governed_github_pr import (
    GitHubReadDenied, GitHubReadMalformed, GovernedJASPullRequestReader,
)
from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry

_HEAD = "0123456789abcdef" * 2 + "01234567"


def _metadata(**overrides):
    record = {
        "repository_full_name": "ArdaNTM/JAS",
        "number": 65,
        "state": "open",
        "merged": False,
        "draft": True,
        "title": "Pending security review",
        "head_sha": _HEAD,
        "base_ref": "main",
    }
    record.update(overrides)
    return record


class FakeGitHub:
    def __init__(self, response=None):
        self.calls = []
        self.response = response

    async def list_tools(self):
        return (
            MCPTool(
                name="get_pull_request",
                description="Read-only PR status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "repository_full_name": {"type": "string"},
                        "pr_number": {"type": "integer"},
                    },
                    "required": ["repository_full_name", "pr_number"],
                    "additionalProperties": False,
                },
            ),
        )

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return SimpleNamespace(
            is_error=False,
            structured_content=self.response if self.response is not None else _metadata(),
        )


def _system(*, allow=False, response=None):
    services = ServiceRegistry()
    service = services.register(
        ServiceDefinition(
            name="GitHub MCP test", version="1.0.0", provider="mcp",
            category=ServiceCategory.MCP,
        ), object(),
    )
    registry = ProviderRegistry(services)
    provider = FakeGitHub(response)
    registry.register(ProviderDefinition(
        provider_id="github.test", name="test-GitHub",
        version="1.0.0", service_id=service.service_id,
    ), provider)
    caps = CapabilityRegistry(services)
    caps.register(CapabilityDefinition(
        capability_id="github.pull_request.read",
        name="Read JAS PR", version="1.0.0",
        description="Read-only pull request status through MCP",
        provider_id="github.test", provider_type=ProviderType.MCP,
        category=CapabilityCategory.CODING, tool_name="get_pull_request",
        risk_level="low",
    ))
    engine = PermissionEngine(caps)
    if allow:
        engine.add_policy(PermissionPolicy(
            policy_id="trusted-owner.github.read",
            policy_version="1.0.0",
            principal_id="trusted-owner",
            capability_id="github.pull_request.read",
            operation_id="github.pull_request.read",
            resource_scope="github/ArdaNTM/JAS/pulls/65",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        ))
    gateway = MCPGateway(caps, registry, engine)
    return GovernedJASPullRequestReader(gateway, authenticated_principal_id="trusted-owner"), provider, engine


def _read(reader, number=65):
    return asyncio.run(reader.read(number))


def test_real_authorized_gateway_reads_exact_jas_pr_without_mutation():
    reader, provider, engine = _system(allow=True)
    result = _read(reader)
    assert result.repository_full_name == "ArdaNTM/JAS"
    assert result.number == 65
    assert result.head_sha == _HEAD
    assert result.draft is True and result.merged is False
    assert result.base_ref == "main"
    assert result.trust == "UNTRUSTED_PROVIDER_METADATA"
    assert result.read_only is True
    assert provider.calls == [("get_pull_request", {
        "repository_full_name": "ArdaNTM/JAS", "pr_number": 65,
    })]
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW


def test_default_deny_never_invokes_github_provider():
    reader, provider, engine = _system()
    with pytest.raises(GitHubReadDenied):
        _read(reader)
    assert provider.calls == []
    assert engine.audit_records()[0].decision.decision is AuthorizationDecision.DENY


def test_policy_for_single_pr_cannot_authorize_another_pr():
    reader, provider, engine = _system(allow=True)
    with pytest.raises(GitHubReadDenied):
        _read(reader, number=66)
    assert provider.calls == []


@pytest.mark.parametrize("invalid", [0, -1, 1_000_001, True, 1.5, "65", None])
def test_invalid_pr_number_never_dispatches(invalid):
    reader, provider, engine = _system(allow=True)
    with pytest.raises(ValueError):
        _read(reader, invalid)
    assert provider.calls == []
    assert engine.audit_records() == ()


@pytest.mark.parametrize("bad", [
    {"repository_full_name": "Other/repo"},
    {"number": 66},
    {"number": True},
    {"head_sha": "bad"},
    {"head_sha": "x" * 40},
    {"state": "pending"},
    {"state": "open", "merged": True},
    {"draft": "false"},
    {"title": "bad\nexfiltration"},
    {"title": "X" * 201},
    {"title": ""},
    {"base_ref": "../secret"},
    {"base_ref": " bad"},
])
def test_malformed_or_spoofed_provider_metadata_rejected(bad):
    reader, provider, _ = _system(allow=True, response=_metadata(**bad))
    with pytest.raises(GitHubReadMalformed):
        _read(reader)
    assert len(provider.calls) == 1


def test_no_client_chosen_principal_or_repository_is_accepted():
    reader, provider, _ = _system(allow=True)
    with pytest.raises(TypeError):
        asyncio.run(reader.read(65, repository_full_name="Other/repo"))
    with pytest.raises(TypeError):
        asyncio.run(reader.read(65, principal_id="admin"))
    assert provider.calls == []


def test_wrong_constructor_dependencies_and_malformed_identity():
    reader, provider, _ = _system(allow=True)
    with pytest.raises(TypeError):
        GovernedJASPullRequestReader(object(), authenticated_principal_id="trusted-owner")
    for bad in ("", "x\nadmin", " x", "x" * 129, "\ud800"):
        with pytest.raises(ValueError):
            GovernedJASPullRequestReader(reader._gateway, authenticated_principal_id=bad)


def test_provider_failure_does_not_leak_tool_error_details():
    reader, provider, _ = _system(allow=True)
    async def fail(name, arguments):
        raise RuntimeError("PRIVATE_GITHUB_TOKEN:/private/config")
    provider.call_tool = fail
    with pytest.raises(GitHubReadMalformed) as error:
        _read(reader)
    assert "PRIVATE_GITHUB_TOKEN" not in str(error.value)
