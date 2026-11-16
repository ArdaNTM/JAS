"""Local OpenCV one-frame camera capture strictly under AURA MCP Gateway.

Device access is the external tool operation. Trusted composition must arm a
short-lived Owner consent lease and separately install a scoped HIGH-risk Core
PermissionEngine policy. A successful camera read does *not* grant the next
image-model call, which requires an independent MCP Gateway ALLOW.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import math
import os
import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from aura_core.kernel.capabilities import (
    CapabilityCategory, CapabilityDefinition, CapabilityRegistry, ProviderType,
)
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceCategory, ServiceDefinition, ServiceRegistry
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderDefinition, ProviderRegistry
from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, _validate_identity, _validate_image,
)

_CAP = "vision.camera.frame.read"
_TOOL = "capture_local_camera_frame"
_PROVIDER = "camera.opencv.local"
_MAX_IMAGE = 2 * 1024 * 1024
_MAX_B64 = ((_MAX_IMAGE + 2) // 3) * 4


class CameraReadDenied(PermissionError):
    """Camera read or independent model authorization was not granted."""


class CameraUnavailable(RuntimeError):
    """Local camera device or trusted model output is unavailable."""


def _session_id(value: str) -> str:
    if (
        not isinstance(value, str) or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(ch) < 32 or ord(ch) == 127 or 0xD800 <= ord(ch) <= 0xDFFF
               for ch in value)
    ):
        raise ValueError("Invalid authenticated camera session")
    return value


class OwnerCameraConsentLease:
    """Trusted application-side consent state. Never exposed as a network API."""

    def __init__(self, *, authenticated_principal_id: str) -> None:
        self._principal = _validate_identity(authenticated_principal_id)
        self._lock = threading.RLock()
        self._session: str | None = None
        self._deadline = 0.0

    def arm(
        self, *, session_id: str, owner_confirmed: bool,
        ttl_seconds: float = 120.0,
    ) -> None:
        _session_id(session_id)
        if owner_confirmed is not True:
            raise CameraReadDenied("Explicit local Owner camera confirmation required")
        if (
            type(ttl_seconds) not in (int, float)
            or not math.isfinite(ttl_seconds) or not 5 <= ttl_seconds <= 300
        ):
            raise ValueError("Camera consent duration must be bounded")
        with self._lock:
            self._session = session_id
            self._deadline = time.monotonic() + float(ttl_seconds)

    def require(self, *, session_id: str) -> None:
        _session_id(session_id)
        with self._lock:
            if self._session != session_id or time.monotonic() >= self._deadline:
                raise CameraReadDenied("Local Owner camera consent is absent, expired or revoked")

    def revoke(self) -> None:
        with self._lock:
            self._session = None
            self._deadline = 0.0


@dataclass(frozen=True, slots=True)
class CameraFrameEvidence:
    description: str
    image_sha256: str
    provider_id: str = _PROVIDER
    model_provider_id: str = "vision.ollama.local"
    trust: str = "UNTRUSTED_CAMERA_FRAME"
    computer_or_robot_actuation: bool = False


class LocalOpenCVCameraMCP:
    """Actual cv2.VideoCapture on a fixed local device ID, never an arbitrary URL."""

    def __init__(
        self, *, consent_lease: OwnerCameraConsentLease,
        trusted_device_index: int = 0, timeout_seconds: float = 10.0,
    ) -> None:
        if not isinstance(consent_lease, OwnerCameraConsentLease):
            raise TypeError("Trusted Owner consent lease is required")
        if type(trusted_device_index) is not int or not 0 <= trusted_device_index <= 3:
            raise ValueError("Trusted local camera index must be 0..3")
        if (
            type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds) or not 1 <= timeout_seconds <= 30
        ):
            raise ValueError("Camera timeout must be 1..30 seconds")
        self.device_index = trusted_device_index
        self._consent = consent_lease
        self.timeout = float(timeout_seconds)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL,
            description="One consented frame from one trusted local OpenCV camera",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "minLength": 1, "maxLength": 128},
                },
                "required": ["session_id"],
                "additionalProperties": False,
            },
        ),)

    def _capture_once(self) -> bytes:
        try:
            import cv2
        except ImportError as exc:
            raise CameraUnavailable("OpenCV is not installed locally") from exc
        cap = None
        try:
            backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.device_index, backend)
            if not cap.isOpened():
                raise CameraUnavailable("Trusted local camera is not available")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            okay, frame = cap.read()
            if not okay or frame is None:
                raise CameraUnavailable("Local camera returned no frame")
            if (
                not hasattr(frame, "shape") or len(frame.shape) < 2
                or type(frame.shape[0]) is not int or type(frame.shape[1]) is not int
                or not 1 <= frame.shape[0] <= 2048
                or not 1 <= frame.shape[1] <= 2048
            ):
                raise CameraUnavailable("Camera frame geometry is outside safe bounds")
            success, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not success:
                raise CameraUnavailable("Camera JPEG encoding failed")
            image = encoded.tobytes()
            if not 16 <= len(image) <= _MAX_IMAGE:
                raise CameraUnavailable("Camera JPEG size is outside safe bounds")
            _validate_image(image)
            return image
        except CameraUnavailable:
            raise
        except Exception as exc:
            raise CameraUnavailable("Local camera frame capture failed") from exc
        finally:
            if cap is not None:
                cap.release()

    async def call_tool(
        self, name: str, arguments: dict[str, object] | None = None,
    ) -> dict[str, str]:
        grant = current_dispatch()
        if (
            grant is None or grant.capability_id != _CAP
            or grant.tool_name != _TOOL or grant.risk_level != "high"
            or name != _TOOL
        ):
            raise CameraReadDenied("Local camera must be called inside authorized MCP Gateway")
        if not isinstance(arguments, dict) or set(arguments) != {"session_id"}:
            raise ValueError("Caller cannot select camera devices or streaming options")
        session_id = _session_id(arguments["session_id"])
        if grant.principal_id != self._consent._principal:
            raise CameraReadDenied("Camera dispatch principal is not the consented Owner")
        # This is checked *inside* the provider, not only the facade:
        # direct Gateway calls without a live owner lease cannot open a camera.
        self._consent.require(session_id=session_id)
        # to_thread has a soft timeout: it cannot terminate a stuck OS driver.
        # A native helper process/broker is required for hard production isolation.
        try:
            frame = await asyncio.wait_for(asyncio.to_thread(self._capture_once), self.timeout)
        except TimeoutError as exc:
            raise CameraUnavailable("Local camera acquisition timed out") from exc
        self._consent.require(session_id=session_id)
        return {
            "image_base64": base64.b64encode(frame).decode("ascii"),
            "image_sha256": hashlib.sha256(frame).hexdigest(),
            "trust": "UNTRUSTED_CAMERA_PIXELS",
        }


def register_local_opencv_camera(
    *, services: ServiceRegistry, providers: ProviderRegistry,
    capabilities: CapabilityRegistry, consent_lease: OwnerCameraConsentLease,
    trusted_device_index: int = 0,
) -> LocalOpenCVCameraMCP:
    """Trusted opt-in registration; no automatic camera policies or capture."""
    if not (
        isinstance(services, ServiceRegistry)
        and isinstance(providers, ProviderRegistry)
        and isinstance(capabilities, CapabilityRegistry)
    ):
        raise TypeError("Existing Core Service/Capability/Provider registries required")
    if any(x.definition.provider_id == _PROVIDER for x in providers.records()):
        raise ValueError("Local camera provider already registered")
    if capabilities.providers(_CAP):
        raise ValueError("Local camera capability already registered")
    instance = LocalOpenCVCameraMCP(
        consent_lease=consent_lease, trusted_device_index=trusted_device_index,
    )
    service = services.register(ServiceDefinition(
        name="aura-verified-local-camera", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Owner local OpenCV camera",
        version="1.0.0", service_id=service.service_id,
    ), instance)
    capabilities.register(CapabilityDefinition(
        capability_id=_CAP, name="Consent-bound one-frame local camera",
        version="1.0.0", description="High-risk transient camera access",
        provider_id=_PROVIDER, provider_type=ProviderType.MCP,
        category=CapabilityCategory.VISION, risk_level="high",
        tool_name=_TOOL,
    ))
    return instance


class GovernedLocalCameraReader:
    """Camera -> bounded JPEG -> separately allowed Ollama image description."""

    def __init__(
        self, gateway: MCPGateway, *,
        authenticated_principal_id: str,
        image_reader: GovernedImageUnderstanding,
        consent_lease: OwnerCameraConsentLease,
        trusted_device_index: int = 0,
    ) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Existing MCP Gateway is required")
        principal = _validate_identity(authenticated_principal_id)
        if not isinstance(image_reader, GovernedImageUnderstanding):
            raise TypeError("Existing authenticated local vision reader required")
        if image_reader._gateway is not gateway or image_reader._principal != principal:
            raise CameraReadDenied("Camera and image permissions must bind same principal and Gateway")
        if not isinstance(consent_lease, OwnerCameraConsentLease) or consent_lease._principal != principal:
            raise CameraReadDenied("Trusted camera consent lease must bind same principal")
        if type(trusted_device_index) is not int or not 0 <= trusted_device_index <= 3:
            raise ValueError("Invalid trusted camera device index")
        try:
            registered = gateway._provider_registry.resolve(_PROVIDER)
        except Exception as exc:
            raise CameraReadDenied("Registered camera provider is unavailable") from exc
        if (not isinstance(registered, LocalOpenCVCameraMCP)
                or registered._consent is not consent_lease
                or registered.device_index != trusted_device_index):
            raise CameraReadDenied("Camera lease and device must match the registered provider")
        self._gateway = gateway
        self._principal = principal
        self._images = image_reader
        self._consent = consent_lease
        self._device = trusted_device_index

    async def describe_frame(
        self, *, session_id: str,
        question: str = "Describe visible objects in this camera frame.",
    ) -> CameraFrameEvidence:
        self._consent.require(session_id=session_id)
        if (
            not isinstance(question, str) or not 1 <= len(question.strip()) <= 500
            or any(ord(c) < 32 or ord(c) == 127 for c in question)
        ):
            raise ValueError("Invalid bounded camera question")
        try:
            result = await self._gateway.invoke(MCPGatewayRequest(
                request_id="camera-frame:" + str(uuid4()),
                principal_id=self._principal, capability_id=_CAP,
                operation_id=_CAP,
                resource_scope=f"vision/camera/{self._device}/frame",
                risk_level=RiskLevel.HIGH, tool_name=_TOOL,
                arguments={"session_id": session_id}, session_id=session_id,
            ))
        except CameraReadDenied:
            # A lease revoked by the provider during device read is a
            # security denial, not merely an unavailable camera.
            raise
        except Exception as exc:
            raise CameraUnavailable("Local camera Gateway is unavailable") from exc
        if result.decision is not AuthorizationDecision.ALLOW:
            raise CameraReadDenied("Explicit scoped camera PermissionEngine ALLOW required")
        self._consent.require(session_id=session_id)
        metadata = result.result
        if (
            result.provider_id != _PROVIDER
            or not isinstance(metadata, dict) or metadata.get("trust") != "UNTRUSTED_CAMERA_PIXELS"
            or not isinstance(metadata.get("image_base64"), str)
            or not 20 <= len(metadata["image_base64"]) <= _MAX_B64
        ):
            raise CameraUnavailable("Camera Gateway result is malformed")
        try:
            image = base64.b64decode(metadata["image_base64"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise CameraUnavailable("Malformed camera JPEG encoding") from exc
        if len(image) > _MAX_IMAGE:
            raise CameraUnavailable("Camera JPEG exceeds safe bounds")
        _validate_image(image)
        if metadata.get("image_sha256") != hashlib.sha256(image).hexdigest():
            raise CameraUnavailable("Camera frame hash does not match bytes")
        try:
            description = await self._images.describe(
                image, prompt=question, capture_confirmed=True,
            )
        except Exception as exc:
            raise CameraUnavailable("Local camera image-model Gateway unavailable") from exc
        self._consent.require(session_id=session_id)
        return CameraFrameEvidence(
            description=description.description,
            image_sha256=description.image_sha256,
        )
