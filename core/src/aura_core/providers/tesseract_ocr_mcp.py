"""Real offline Tesseract OCR execution behind the AURA MCP Gateway.

No shell command is user-constructed. A trusted composition registers a fixed
absolute binary, a narrow operation and no default permission. The local
Tesseract process consumes only already-consented image bytes via stdin and
returns bounded untrusted text through stdout. No capture, cloud API or device
actuation is possible from this module.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from aura_core.kernel.capabilities import (
    CapabilityRegistry, CapabilityDefinition, CapabilityCategory, ProviderType,
)
from aura_core.kernel.permissions import AuthorizationDecision, RiskLevel
from aura_core.kernel.services import ServiceRegistry, ServiceDefinition, ServiceCategory
from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.gateway import MCPGateway, MCPGatewayRequest
from aura_core.mcp.mcp_provider import MCPTool
from aura_core.mcp.provider import ProviderRegistry, ProviderDefinition
from aura_core.providers.ollama_vision_mcp import _validate_image, _validate_identity

_CAP = "vision.ocr.extract"
_OP = "vision.ocr.extract"
_TOOL = "extract_image_text"
_PROVIDER = "ocr.tesseract.local"
_SCOPE = "vision/consented/ocr"
_ALLOWED_LANGUAGES = frozenset({"eng", "tur", "eng+tur"})
_MAX_IMAGE = 8 * 1024 * 1024
_MAX_BASE64 = ((_MAX_IMAGE + 2) // 3) * 4
_MAX_TEXT = 32000
_MAX_STDOUT = 128000


class OCRDenied(PermissionError):
    """Current Core PermissionEngine/Gateway grant is insufficient."""


class OCRUnavailable(RuntimeError):
    """Local Tesseract binary failed, timed out or returned invalid output."""


@dataclass(frozen=True, slots=True)
class OCREvidence:
    text: str
    language: str
    image_sha256: str
    provider_id: str = _PROVIDER
    trust: str = "UNTRUSTED_OCR_TEXT"
    physical_action: bool = False


def _lang(language: str) -> str:
    if not isinstance(language, str) or language not in _ALLOWED_LANGUAGES:
        raise ValueError("Unsupported local installed OCR language")
    return language


class LocalTesseractOCRProvider:
    """The real image-to-text subprocess backend, guarded by Gateway dispatch."""

    def __init__(
        self,
        *,
        executable: str = "/usr/bin/tesseract",
        timeout_seconds: float = 20.0,
    ) -> None:
        if (
            not isinstance(executable, str)
            or not 1 <= len(executable) <= 260
            or any(ord(c) < 32 or ord(c) == 127 for c in executable)
        ):
            raise ValueError("Invalid absolute OCR executable")
        path = Path(executable)
        if not path.is_absolute() or path.is_symlink():
            raise ValueError("An explicit nonsymlink absolute Tesseract executable is required")
        if (type(timeout_seconds) not in (int, float)
                or not math.isfinite(timeout_seconds)
                or not 1 <= timeout_seconds <= 60):
            raise ValueError("OCR timeout must be 1..60 seconds")
        self._executable = str(path)
        self._timeout_seconds = float(timeout_seconds)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Read text from consented image on local Tesseract OCR",
            input_schema={
                "type": "object",
                "properties": {
                    "image_base64": {"type": "string", "minLength": 20, "maxLength": _MAX_BASE64},
                    "language": {"type": "string", "enum": sorted(_ALLOWED_LANGUAGES)},
                },
                "required": ["image_base64", "language"],
                "additionalProperties": False,
            },
        ),)

    async def call_tool(
        self, name: str,
        arguments: dict[str, object] | None = None,
    ) -> dict[str, str]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP
                or grant.tool_name != _TOOL or grant.risk_level != "medium"
                or name != _TOOL):
            raise OCRDenied("Authorized AURA MCP Gateway dispatch is required")
        if not isinstance(arguments, dict) or set(arguments) != {"image_base64", "language"}:
            raise ValueError("Unsupported OCR tool input")
        language = _lang(arguments["language"])
        encoded = arguments["image_base64"]
        if not isinstance(encoded, str) or not 20 <= len(encoded) <= _MAX_BASE64:
            raise ValueError("Image is not bounded base64")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid OCR image encoding") from exc
        _validate_image(image)

        try:
            # No shell=True, no user-supplied filename, command switch or URL.
            proc = await asyncio.create_subprocess_exec(
                self._executable,
                "stdin", "stdout", "-l", language, "--psm", "6",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            )
        except OSError as exc:
            raise OCRUnavailable("Local Tesseract OCR is not installed or launchable") from exc
        try:
            output, _ = await asyncio.wait_for(
                proc.communicate(image), timeout=self._timeout_seconds,
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise OCRUnavailable("Local Tesseract OCR timed out") from exc
        if proc.returncode != 0 or not isinstance(output, bytes) or len(output) > _MAX_STDOUT:
            raise OCRUnavailable("Local Tesseract OCR failed or returned excessive text")
        decoded = output.decode("utf-8", errors="replace").replace("\x00", "").strip()
        if len(decoded) > _MAX_TEXT:
            raise OCRUnavailable("OCR text exceeds configured limit")
        return {
            "text": decoded,
            "language": language,
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "trust": "UNTRUSTED_OCR_TEXT",
        }


def register_local_tesseract_ocr(
    *,
    services: ServiceRegistry,
    providers: ProviderRegistry,
    capabilities: CapabilityRegistry,
    executable: str = "/usr/bin/tesseract",
) -> LocalTesseractOCRProvider:
    """Explicit trusted registration with **no automatic permission policy**."""
    if not (
        isinstance(services, ServiceRegistry)
        and isinstance(providers, ProviderRegistry)
        and isinstance(capabilities, CapabilityRegistry)
    ):
        raise TypeError("Authoritative existing Core registries are required")
    instance = LocalTesseractOCRProvider(executable=executable)
    if any(x.definition.provider_id == _PROVIDER for x in providers.records()):
        raise ValueError("OCR provider is already registered")
    if capabilities.providers(_CAP):
        raise ValueError("An OCR capability is already registered")
    service = services.register(ServiceDefinition(
        name="aura-local-tesseract-ocr", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Local Tesseract OCR",
        version="1.0.0", service_id=service.service_id,
    ), instance)
    capabilities.register(CapabilityDefinition(
        capability_id=_CAP, name="Consented local OCR",
        version="1.0.0", description="Offline image-to-text through Tesseract and MCP Gateway",
        provider_id=_PROVIDER, provider_type=ProviderType.MCP,
        category=CapabilityCategory.VISION, risk_level="medium",
        tool_name=_TOOL,
    ))
    return instance


class GovernedOCRReader:
    """Trusted-principal client that never invokes the OCR provider directly."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("Authoritative MCP Gateway is required")
        self._gateway = gateway
        self._principal = _validate_identity(authenticated_principal_id)

    async def read(
        self,
        image: bytes, *, language: str = "eng",
        capture_confirmed: bool,
    ) -> OCREvidence:
        if capture_confirmed is not True:
            raise OCRDenied("Explicit image consent is required")
        _validate_image(image)
        language = _lang(language)
        try:
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id="ocr-image:" + str(uuid4()),
                principal_id=self._principal,
                capability_id=_CAP, operation_id=_OP,
                resource_scope=_SCOPE,
                risk_level=RiskLevel.MEDIUM,
                tool_name=_TOOL,
                arguments={
                    "image_base64": base64.b64encode(image).decode("ascii"),
                    "language": language,
                },
            ))
        except Exception as exc:
            raise OCRUnavailable("Local OCR Gateway is unavailable") from exc
        if response.decision is not AuthorizationDecision.ALLOW:
            raise OCRDenied("Explicit OCR PermissionEngine policy is required")
        result = response.result
        if (
            not isinstance(result, dict)
            or result.get("status") == "failed"
            or result.get("trust") != "UNTRUSTED_OCR_TEXT"
            or result.get("language") != language
            or not isinstance(result.get("text"), str)
            or len(result["text"]) > _MAX_TEXT
            or result.get("image_sha256") != hashlib.sha256(image).hexdigest()
            or response.provider_id != _PROVIDER
        ):
            raise OCRUnavailable("Local OCR result failed validation")
        return OCREvidence(
            text=result["text"], language=language,
            image_sha256=result["image_sha256"],
        )
