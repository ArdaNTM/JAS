"""Session-scoped, permission-gated anonymous speaker diarization."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from threading import RLock
from typing import Sequence
from uuid import uuid4

from aura_core.kernel.capabilities import CapabilityCategory, CapabilityDefinition, CapabilityRegistry, LatencyClass, ProviderType, QualityClass
from aura_core.kernel.events import EventBus, KernelEvent
from aura_core.kernel.permissions import AuthorizationDecision, AuthorizationRequest, PermissionEngine, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.providers.speaker_embedding import SpeakerEmbeddingProvider


@dataclass(frozen=True, slots=True)
class SpeakerMatch:
    speaker_id: str
    similarity: float
    created: bool


@dataclass(slots=True)
class _Centroid:
    vector: tuple[float, ...]
    observations: int = 1


@dataclass(slots=True)
class _Session:
    principal_id: str
    speakers: dict[str, _Centroid] = field(default_factory=dict)


class SpeakerRecognitionService:
    """Cluster voice segments only within a single authorized session."""
    CAPABILITY_ID = "voice.speaker.recognize"
    OPERATION_ID = "voice.speaker.recognize"

    def __init__(self, *, provider: SpeakerEmbeddingProvider, permission_engine: PermissionEngine,
                 event_bus: EventBus, similarity_threshold: float = 0.35, max_speakers: int = 8) -> None:
        if not 0.0 < similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be in (0, 1]")
        if not 1 <= max_speakers <= 8:
            raise ValueError("max_speakers must be in 1..8")
        self._provider, self._permissions, self._events = provider, permission_engine, event_bus
        self._threshold, self._max_speakers = similarity_threshold, max_speakers
        self._sessions: dict[str, _Session] = {}
        self._lock = RLock()

    @staticmethod
    def _normalize(values: Sequence[float]) -> tuple[float, ...]:
        if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= 8192:
            raise ValueError("Speaker embedding must contain 1..8192 values")
        vector = tuple(float(x) for x in values)
        if any(not math.isfinite(x) for x in vector):
            raise ValueError("Speaker embedding contains non-finite values")
        norm = math.sqrt(sum(x * x for x in vector))
        if norm <= 1e-12:
            raise ValueError("Speaker embedding must not be zero")
        return tuple(x / norm for x in vector)

    def _authorize(self, *, principal_id: str, session_id: str, operation: str) -> None:
        if not isinstance(principal_id, str) or not principal_id.strip() or len(principal_id) > 128:
            raise ValueError("A valid authenticated principal is required")
        if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 128:
            raise ValueError("A valid voice session id is required")
        decision = self._permissions.authorize(AuthorizationRequest(
            request_id=str(uuid4()), principal_id=principal_id,
            capability_id=self.CAPABILITY_ID, operation_id=operation,
            resource_scope=f"voice:session:{session_id}", risk_level=RiskLevel.MEDIUM,
            session_id=session_id,
        ))
        if decision.decision is not AuthorizationDecision.ALLOW:
            raise PermissionError("Speaker recognition was not authorized")

    def recognize(self, *, principal_id: str, session_id: str, wav_bytes: bytes) -> SpeakerMatch:
        self._authorize(principal_id=principal_id, session_id=session_id, operation=self.OPERATION_ID)
        if not isinstance(wav_bytes, bytes) or not 44 <= len(wav_bytes) <= 2_000_000:
            raise ValueError("WAV payload must contain 44 bytes..2 MB")
        # Check ownership before passing any audio to the model provider.
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None and existing.principal_id != principal_id:
                raise PermissionError("Voice session belongs to another principal")
        vector = self._normalize(self._provider.embed(wav_bytes))
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = _Session(principal_id=principal_id)
                self._sessions[session_id] = session
            elif session.principal_id != principal_id:
                raise PermissionError("Voice session belongs to another principal")
            best_id, best_similarity = None, -1.0
            for speaker_id, centroid in session.speakers.items():
                if len(centroid.vector) != len(vector):
                    continue
                score = sum(a * b for a, b in zip(vector, centroid.vector, strict=True))
                if score > best_similarity:
                    best_id, best_similarity = speaker_id, score
            created = best_id is None or best_similarity < self._threshold
            if created:
                if len(session.speakers) >= self._max_speakers:
                    raise RuntimeError("Maximum speakers reached for this session")
                speaker_id, similarity = f"speaker-{len(session.speakers) + 1}", 1.0
                session.speakers[speaker_id] = _Centroid(vector)
            else:
                speaker_id, similarity = best_id, best_similarity
                centroid = session.speakers[speaker_id]
                count = centroid.observations
                average = tuple((old * count + new) / (count + 1) for old, new in zip(centroid.vector, vector, strict=True))
                centroid.vector = self._normalize(average)
                centroid.observations += 1
        result = SpeakerMatch(speaker_id, max(-1.0, min(1.0, similarity)), created)
        self._events.publish(KernelEvent(
            event_type="SpeakerSegmentClassified", source_component="aura.speaker_recognition",
            correlation_id=session_id, session_id=session_id,
            payload={"speaker_id": result.speaker_id, "created": result.created,
                     "similarity": round(result.similarity, 4),
                     "raw_audio_retained": False, "speaker_embedding_persisted": False},
        ))
        return result

    def end_session(self, *, principal_id: str, session_id: str) -> None:
        self._authorize(principal_id=principal_id, session_id=session_id, operation="voice.speaker.session.close")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None and session.principal_id != principal_id:
                raise PermissionError("Voice session belongs to another principal")
            self._sessions.pop(session_id, None)


def register_speaker_recognition_service(*, service_registry: ServiceRegistry,
        capability_registry: CapabilityRegistry, permission_engine: PermissionEngine,
        event_bus: EventBus, provider: SpeakerEmbeddingProvider,
        similarity_threshold: float = 0.35) -> SpeakerRecognitionService:
    service = SpeakerRecognitionService(provider=provider, permission_engine=permission_engine,
                                        event_bus=event_bus, similarity_threshold=similarity_threshold)
    definition = ServiceDefinition(
        name="speaker-recognition", version="1.0.0", provider="aura.local",
        category=ServiceCategory.CORE,
        capabilities=frozenset({SpeakerRecognitionService.CAPABILITY_ID}),
        tags=frozenset({"voice", "speaker-diarization", "local-only", "session-scoped"}),
    )
    service_registry.register(definition, service)
    capability_registry.register(CapabilityDefinition(
        capability_id=SpeakerRecognitionService.CAPABILITY_ID,
        name="Anonymous session speaker recognition", version="1.0.0",
        description="Cluster speaker segments within one authorized voice session using local embeddings.",
        provider_id=definition.service_id, provider_type=ProviderType.SERVICE,
        category=CapabilityCategory.VOICE, priority=50,
        latency_class=LatencyClass.MEDIUM, quality_class=QualityClass.HIGH, risk_level="medium",
    ))
    return service
