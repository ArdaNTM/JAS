"""Provider contracts keep device and SDK implementations outside agents."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class VoiceRequest:
    audio: bytes
    language: str | None = None


@dataclass(frozen=True, slots=True)
class VoiceResult:
    text: str
    language: str | None = None


@dataclass(frozen=True, slots=True)
class VisionRequest:
    image: bytes
    mime_type: str
    prompt: str = ""


@dataclass(frozen=True, slots=True)
class VisionResult:
    content: str
    metadata: dict[str, str] = field(default_factory=dict)


class VoiceProvider(Protocol):
    async def transcribe(self, request: VoiceRequest) -> VoiceResult:
        raise NotImplementedError


class VisionProvider(Protocol):
    async def analyze(self, request: VisionRequest) -> VisionResult:
        raise NotImplementedError


class BrowserOperation(StrEnum):
    NAVIGATE = "navigate"
    INSPECT = "inspect"
    CLICK = "click"
    TYPE = "type"


@dataclass(frozen=True, slots=True)
class BrowserRequest:
    session_id: str
    operation: BrowserOperation
    target: str
    value: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class BrowserResult:
    session_id: str
    content: str | None
    url: str | None


class BrowserProvider(Protocol):
    async def execute(self, request: BrowserRequest) -> BrowserResult:
        raise NotImplementedError
    async def close_session(self, session_id: str) -> None:
        raise NotImplementedError


class ComputerActionType(StrEnum):
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    SCREENSHOT = "screenshot"
    WINDOW = "window"


@dataclass(frozen=True, slots=True)
class ComputerAction:
    session_id: str
    action_type: ComputerActionType
    payload: dict[str, Any]
    requires_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class ComputerResult:
    session_id: str
    output: dict[str, Any]


class ComputerProvider(Protocol):
    async def perform(self, action: ComputerAction) -> ComputerResult:
        raise NotImplementedError
