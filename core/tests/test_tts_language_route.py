"""Read-only TTS locale route previews against authoritative Core registries."""
import pytest

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry, ProviderState
from aura_core.tts.language_route import (
    LanguageAwareSpeechRoutePreview, LanguageRouteUnavailable,
)


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def call_tool(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("Route metadata preview cannot execute a tool")


def _setup(*entries):
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    capabilities = CapabilityRegistry(services)
    instances = {}
    for backend, priority, tool in entries:
        pid = "tts." + backend
        service = services.register(
            ServiceDefinition(
                name="local-" + backend, version="1.0.0",
                provider="mcp", category=ServiceCategory.MCP,
            ),
            object(),
        )
        instance = FakeProvider()
        providers.register(
            ProviderDefinition(
                provider_id=pid, name=backend,
                version="1.0.0", service_id=service.service_id,
            ),
            instance,
        )
        capabilities.register(
            CapabilityDefinition(
                capability_id="speech.synthesize", name=backend + " speech",
                version="1.0.0", description="Local TTS",
                provider_id=pid, provider_type=ProviderType.MCP,
                category=CapabilityCategory.VOICE,
                tool_name=tool, risk_level="low", priority=priority,
            )
        )
        instances[pid] = instance
    return LanguageAwareSpeechRoutePreview(capabilities, providers), capabilities, providers, instances


@pytest.mark.parametrize("locale,backend,language", [
    ("tr", "piper", "tr"), ("tr-TR", "piper", "tr"),
    ("en", "kokoro", "en"), ("en-US", "kokoro", "en"),
    ("en-GB", "kokoro", "en"),
])
def test_selects_registered_healthy_local_provider_without_execution(locale, backend, language):
    router, _, _, providers = _setup((backend, 100, "synthesize"))
    result = router.select(locale)
    assert result.language == language
    assert result.provider_id == "tts." + backend
    assert result.capability_id == "speech.synthesize"
    assert result.tool_name == "synthesize"
    assert result.guarantee == "METADATA_ONLY_NOT_AUTHORIZED"
    assert providers[result.provider_id].calls == 0


@pytest.mark.parametrize("locale", [
    "fr", "es", "ru", "de-DE", "xx", "en-GB-secret", " EN ",
    "en\n", "tr\x00", "", 10, None, "Türkçe",
])
def test_unapproved_locale_or_input_fails_closed(locale):
    router, _, _, _ = _setup(("kokoro", 100, "synthesize"))
    with pytest.raises((ValueError, LanguageRouteUnavailable)):
        router.select(locale)


def test_no_provider_or_registry_authority_never_auto_registers():
    router, caps, providers, _ = _setup()
    assert caps.records() == ()
    assert providers.records() == ()
    with pytest.raises(LanguageRouteUnavailable):
        router.select("en")
    assert caps.records() == ()


def test_mismatched_gateway_selected_provider_fails_instead_of_switching_tools():
    router, caps, providers, instances = _setup(
        ("kokoro", 100, "synthesize"),
        ("piper", 200, "synthesize"),
    )
    assert caps.resolve("speech.synthesize").definition.provider_id == "tts.piper"
    assert router.select("tr").provider_id == "tts.piper"
    with pytest.raises(LanguageRouteUnavailable, match="not authoritative"):
        router.select("en")
    assert all(v.calls == 0 for v in instances.values())


def test_unhealthy_or_missing_provider_cannot_be_used():
    router, _, providers, _ = _setup(("kokoro", 100, "synthesize"))
    providers.update_health("tts.kokoro", available=False, healthy=False)
    with pytest.raises(LanguageRouteUnavailable):
        router.select("en")


def test_unhealthy_capability_and_wrong_tool_rejected():
    router, capabilities, _, _ = _setup(("piper", 100, "synthesize"))
    capabilities.update_health("speech.synthesize", "tts.piper", available=False, healthy=False)
    with pytest.raises(LanguageRouteUnavailable):
        router.select("tr")
    wrong, _, _, _ = _setup(("piper", 100, "delete_file"))
    with pytest.raises(LanguageRouteUnavailable):
        wrong.select("tr")


def test_unavailable_provider_registry_state_rejected():
    router, _, providers, _ = _setup(("kokoro", 100, "synthesize"))
    providers.update_state("tts.kokoro", ProviderState.FAILED)
    with pytest.raises(LanguageRouteUnavailable):
        router.select("en")


def test_constructor_rejects_non_core_registries():
    router, capabilities, providers, _ = _setup(("kokoro", 100, "synthesize"))
    with pytest.raises(TypeError):
        LanguageAwareSpeechRoutePreview(object(), providers)
    with pytest.raises(TypeError):
        LanguageAwareSpeechRoutePreview(capabilities, object())
