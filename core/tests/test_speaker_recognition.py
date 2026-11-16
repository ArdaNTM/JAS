from __future__ import annotations
import asyncio
import pytest
from aura_core.application.speaker_recognition import SpeakerRecognitionService, register_speaker_recognition_service
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.events import EventBus
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.provider import ProviderRegistry


class FakeEmbeddingProvider:
    def __init__(self, vectors):
        self.vectors, self.calls = iter(vectors), 0
    def embed(self, wav_bytes):
        self.calls += 1
        return next(self.vectors)


def service_registry_id(service):
    return "aura.local:speaker-recognition:1.0.0"


def build(*, vectors, allowed=True):
    bus = EventBus()
    services = ServiceRegistry(bus)
    capabilities = CapabilityRegistry(services, bus)
    providers = ProviderRegistry(services, bus)
    permissions = PermissionEngine(capabilities, bus)
    provider = FakeEmbeddingProvider(vectors)
    service = register_speaker_recognition_service(
        service_registry=services, capability_registry=capabilities,
        permission_engine=permissions, event_bus=bus, provider_registry=providers, provider=provider,
        similarity_threshold=0.9,
    )
    if allowed:
        for session_id in ("session-1", "session-2"):
            for operation in (SpeakerRecognitionService.OPERATION_ID, "voice.speaker.session.close"):
                permissions.add_policy(PermissionPolicy(
                    policy_id=f"speaker:{session_id}:{operation}", policy_version="1",
                    principal_id="local-user", capability_id=SpeakerRecognitionService.CAPABILITY_ID,
                    operation_id=operation, resource_scope=f"voice:session:{session_id}",
                    authorization_level=AuthorizationLevel.READ, decision=AuthorizationDecision.ALLOW,
                ))
    while bus.snapshot()["queued_total"]:
        asyncio.run(bus.dispatch_once())
    assert providers.resolve("voice.speaker.local") is provider
    assert providers.get("voice.speaker.local").definition.service_id == service_registry_id(service)
    return service, provider, bus


def test_default_deny_prevents_embedding_provider_access():
    service, provider, _ = build(vectors=[(1.0, 0.0)], allowed=False)
    with pytest.raises(PermissionError):
        service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=b"RIFF" + b"x" * 40)
    assert provider.calls == 0


def test_same_speaker_clusters_and_different_speaker_gets_new_label():
    service, provider, bus = build(vectors=[(1.0, 0.0), (0.99, 0.01), (0.0, 1.0)])
    payload = b"RIFF" + b"x" * 40
    first = service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    same = service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    other = service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    assert first.speaker_id == same.speaker_id == "speaker-1"
    assert same.created is False and other.speaker_id == "speaker-2"
    assert provider.calls == 3
    events = []
    bus.subscribe("SpeakerSegmentClassified", events.append)
    assert asyncio.run(bus.dispatch_once()) is True
    assert events[0].payload["raw_audio_retained"] is False


def test_speaker_labels_are_isolated_between_sessions():
    service, _, _ = build(vectors=[(1.0, 0.0), (1.0, 0.0)])
    payload = b"RIFF" + b"x" * 40
    a = service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    b = service.recognize(principal_id="local-user", session_id="session-2", wav_bytes=payload)
    assert a.speaker_id == b.speaker_id == "speaker-1"


def test_session_cannot_be_reused_by_another_principal_before_model_access():
    service, provider, _ = build(vectors=[(1.0, 0.0)])
    payload = b"RIFF" + b"x" * 40
    service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    with pytest.raises(PermissionError):
        service.recognize(principal_id="other-user", session_id="session-1", wav_bytes=payload)
    assert provider.calls == 1


def test_bounded_audio_and_embedding_validation():
    service, provider, _ = build(vectors=[(0.0, 0.0)])
    with pytest.raises(ValueError):
        service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=b"x")
    assert provider.calls == 0
    with pytest.raises(ValueError):
        service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=b"RIFF" + b"x" * 40)
    assert provider.calls == 1


def test_end_session_erases_session_centroids():
    service, _, _ = build(vectors=[(1.0, 0.0), (1.0, 0.0)])
    payload = b"RIFF" + b"x" * 40
    service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    service.end_session(principal_id="local-user", session_id="session-1")
    new = service.recognize(principal_id="local-user", session_id="session-1", wav_bytes=payload)
    assert new.created is True and new.speaker_id == "speaker-1"
