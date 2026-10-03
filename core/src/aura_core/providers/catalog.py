"""Capability declarations for externally hosted MCP providers.

The declarations are inert. A deployment registers an MCP provider first, then
registers the matching capability; Core never calls device or network tools.
"""

from __future__ import annotations

from dataclasses import dataclass

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, ProviderType
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionPolicy


@dataclass(frozen=True, slots=True)
class ExternalCapability:
    capability_id: str
    name: str
    category: CapabilityCategory
    description: str

    def definition(self, provider_id: str) -> CapabilityDefinition:
        return CapabilityDefinition(self.capability_id, self.name, "1.0.0", self.description, provider_id, ProviderType.MCP, self.category)


EXTERNAL_CAPABILITIES = (
    ExternalCapability("internet.search", "Internet search", CapabilityCategory.RESEARCH, "Searches public internet sources through an MCP provider."),
    ExternalCapability("file.workspace", "Workspace file access", CapabilityCategory.STORAGE, "Reads or writes policy-authorized workspace resources."),
    ExternalCapability("browser.automation", "Browser automation", CapabilityCategory.BROWSER, "Performs browser actions through an MCP provider."),
    ExternalCapability("voice.transcription", "Voice transcription", CapabilityCategory.VOICE, "Transcribes audio through an MCP provider."),
    ExternalCapability("vision.analysis", "Vision analysis", CapabilityCategory.VISION, "Analyzes a supplied image through an MCP provider."),
    ExternalCapability("computer.control", "Computer control", CapabilityCategory.AUTOMATION, "Performs user-approved computer actions through an MCP provider."),
)


def approval_policy(principal_id: str, capability_id: str, operation_id: str, resource_scope: str) -> PermissionPolicy:
    """Create an explicit default policy for a side-effecting external tool."""
    return PermissionPolicy(
        policy_id=f"approval:{principal_id}:{capability_id}:{operation_id}", policy_version="1.0.0",
        principal_id=principal_id, capability_id=capability_id, operation_id=operation_id,
        resource_scope=resource_scope, authorization_level=AuthorizationLevel.USER_APPROVAL_REQUIRED,
        decision=AuthorizationDecision.REQUIRE_APPROVAL,
    )
