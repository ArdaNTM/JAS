"""Read-only local TTS language-route preview over *existing* Core registries.

The preview neither registers a capability nor invokes a provider or MCP tool.
It fails closed when the existing MCP Gateway's capability selection would
resolve to a different voice provider. Actual authorization and execution must
remain in the MCP Gateway and cannot be inferred from a preview.
"""
from __future__ import annotations

from dataclasses import dataclass

from aura_core.kernel.capabilities import (
    CapabilityCategory,
    CapabilityRegistry,
    CapabilityState,
    ProviderType,
)
from aura_core.mcp.provider import ProviderRegistry, ProviderState


_LOCAL_PROVIDER_BY_LANGUAGE = {"tr": "tts.piper", "en": "tts.kokoro"}
_SUPPORTED_CODES = {
    "tr": "tr", "tr-tr": "tr",
    "en": "en", "en-us": "en", "en-gb": "en",
}
_ALLOWED_PROVIDER_STATES = {
    ProviderState.REGISTERED, ProviderState.READY, ProviderState.RUNNING,
}
_ALLOWED_CAPABILITY_STATES = {CapabilityState.AVAILABLE, CapabilityState.ACTIVE}


class LanguageRouteUnavailable(LookupError):
    """No safe, active, already-registered provider matches requested language."""


@dataclass(frozen=True, slots=True)
class LanguageRoutePreview:
    language: str
    locale: str
    provider_id: str
    capability_id: str = "speech.synthesize"
    operation_id: str = "speech.synthesize"
    tool_name: str = "synthesize"
    guarantee: str = "METADATA_ONLY_NOT_AUTHORIZED"


class LanguageAwareSpeechRoutePreview:
    """Inspect current registries; never create a provider or execution grant."""

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        providers: ProviderRegistry,
    ) -> None:
        if not isinstance(capabilities, CapabilityRegistry):
            raise TypeError("existing Core CapabilityRegistry is required")
        if not isinstance(providers, ProviderRegistry):
            raise TypeError("existing MCP ProviderRegistry is required")
        self._capabilities = capabilities
        self._providers = providers

    def select(self, locale: str) -> LanguageRoutePreview:
        if (not isinstance(locale, str)
                or not 2 <= len(locale) <= 8
                or locale != locale.strip()
                or any(ord(ch) > 127 or ord(ch) < 33 for ch in locale)):
            raise ValueError("invalid local voice locale")
        locale_key = locale.lower()
        language = _SUPPORTED_CODES.get(locale_key)
        if language is None:
            raise LanguageRouteUnavailable("No approved local TTS locale")
        intended_provider = _LOCAL_PROVIDER_BY_LANGUAGE[language]

        try:
            # This is the same authoritative selection used by the existing
            # MCP Gateway. A route never overrides the selected capability.
            selected = self._capabilities.resolve("speech.synthesize")
            record = self._providers.get(intended_provider)
        except (LookupError, KeyError) as exc:
            raise LanguageRouteUnavailable("Local voice provider is not available") from exc

        definition = selected.definition
        if (
            definition.provider_id != intended_provider
            or definition.provider_type is not ProviderType.MCP
            or definition.category is not CapabilityCategory.VOICE
            or definition.tool_name != "synthesize"
            or not selected.available
            or not selected.healthy
            or selected.state not in _ALLOWED_CAPABILITY_STATES
            or not record.available
            or not record.healthy
            or record.state not in _ALLOWED_PROVIDER_STATES
            or record.definition.provider_id != intended_provider
        ):
            raise LanguageRouteUnavailable("Local voice route is not authoritative")
        return LanguageRoutePreview(
            language=language,
            locale=locale_key,
            provider_id=intended_provider,
        )
