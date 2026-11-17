"""Locally computed rectified-stereo depth, authorized by AURA MCP Gateway.

A real deterministic sum-of-absolute-differences (SAD) stereo matcher operates on
bounded binary PGM (P5) grayscale frames. No network, GPU dependency, shell,
screen capture or actuator. Sparse outputs are UNTRUSTED geometrical estimates,
never proof of a calibrated camera or physical action authorization.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import math
import re
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

_CAP = "vision.stereo.depth"
_OP = _CAP
_PROVIDER = "vision.stereo.sad.local"
_TOOL = "estimate_stereo_depth"
_SCOPE = "vision/consented/rectified-stereo"
_HEADER = re.compile(rb"\AP5\n([1-9][0-9]{1,3}) ([1-9][0-9]{1,3})\n255\n")
_MAX_PIXELS = 512 * 384
_MAX_B64 = ((_MAX_PIXELS + 32 + 2) // 3) * 4
_MAX_POINTS = 128


class StereoDepthDenied(PermissionError):
    """An authenticated principal lacks exact per-frame Gateway authority."""


class StereoDepthUnavailable(RuntimeError):
    """Stereo input or output is unsafe, inconsistent or unavailable."""


@dataclass(frozen=True, slots=True)
class StereoCalibration:
    """Trusted-composition input. Numerical validity is not hardware attestation."""

    focal_px: float
    baseline_m: float
    max_disparity: int = 16

    def __post_init__(self) -> None:
        if (
            type(self.focal_px) not in (int, float)
            or not math.isfinite(self.focal_px)
            or not 50 <= self.focal_px <= 5000
            or type(self.baseline_m) not in (int, float)
            or not math.isfinite(self.baseline_m)
            or not 0.01 <= self.baseline_m <= 1
            or type(self.max_disparity) is not int
            or not 4 <= self.max_disparity <= 32
        ):
            raise ValueError("Invalid bounded stereo rig calibration")


@dataclass(frozen=True, slots=True)
class DepthSample:
    x: int
    y: int
    disparity_px: int
    depth_m: float
    uniqueness: float


@dataclass(frozen=True, slots=True)
class StereoDepthEvidence:
    samples: tuple[DepthSample, ...]
    pair_sha256: str
    width: int
    height: int
    provider_id: str = _PROVIDER
    trust: str = "UNTRUSTED_STEREO_ESTIMATE"
    safe_for_physical_control: bool = False


def _pgm_bytes(data: bytes) -> tuple[int, int, bytes]:
    if type(data) is not bytes or not 16 <= len(data) <= _MAX_PIXELS + 32:
        raise ValueError("Expected bounded binary PGM input")
    match = _HEADER.match(data)
    if match is None:
        raise ValueError("Only canonical binary PGM P5 frames are accepted")
    width, height = (int(x) for x in match.groups())
    if not (48 <= width <= 512 and 32 <= height <= 384 and width * height <= _MAX_PIXELS):
        raise ValueError("Invalid stereo image dimensions")
    pixels = data[match.end():]
    if len(pixels) != width * height:
        raise ValueError("Malformed binary PGM pixel payload")
    return width, height, pixels


def _pair_hash(left: bytes, right: bytes) -> str:
    return hashlib.sha256(len(left).to_bytes(4, "big") + left + right).hexdigest()


def _match_rectified_pair(
    left: bytes,
    right: bytes,
    calibration: StereoCalibration,
) -> tuple[int, int, tuple[DepthSample, ...]]:
    """Actual sparse 5x5 SAD matching, O(samples * disparities * window_pixels).

    Frames must be rectified independently in a trusted upstream capture stage.
    The matcher returns no point if a distinctive correspondence is absent.
    """
    width, height, a = _pgm_bytes(left)
    rw, rh, b = _pgm_bytes(right)
    if (rw, rh) != (width, height) or width <= calibration.max_disparity + 6:
        raise ValueError("Stereo frames are not dimensionally compatible")
    points: list[DepthSample] = []
    disparity_limit = calibration.max_disparity
    # Sampling reduces worst-case CPU consumption on modest local machines;
    # the 128-point cap ensures predictable output, including large images.
    stride = max(6, math.ceil(math.sqrt((width * height) / _MAX_POINTS)))
    for y in range(2, height - 2, stride):
        for x in range(disparity_limit + 2, width - 2, stride):
            costs: list[tuple[int, int]] = []
            for disparity in range(1, disparity_limit + 1):
                total = 0
                for dy in (-2, -1, 0, 1, 2):
                    row = (y + dy) * width
                    for dx in (-2, -1, 0, 1, 2):
                        total += abs(a[row + x + dx] - b[row + x + dx - disparity])
                costs.append((total, disparity))
            costs.sort()
            first, d = costs[0]
            second = costs[1][0]
            uniqueness = (second - first) / max(second, 1)
            if uniqueness < 0.18:
                continue
            depth = float(calibration.focal_px) * float(calibration.baseline_m) / d
            if not 0.05 <= depth <= 250:
                continue
            points.append(DepthSample(x=x, y=y, disparity_px=d,
                                      depth_m=round(depth, 5),
                                      uniqueness=round(uniqueness, 4)))
            if len(points) >= _MAX_POINTS:
                return width, height, tuple(points)
    return width, height, tuple(points)


class LocalStereoDepthMCP:
    """Local deterministic CPU engine, never callable outside a Gateway grant."""

    def __init__(self, *, calibration: StereoCalibration) -> None:
        if not isinstance(calibration, StereoCalibration):
            raise TypeError("Trusted stereo calibration is required")
        self._calibration = calibration

    async def list_tools(self) -> tuple[MCPTool, ...]:
        return (MCPTool(
            name=_TOOL, description="Read sparse stereo depth hypotheses from rectified PGM frames",
            input_schema={
                "type": "object",
                "properties": {
                    "left_pgm": {"type": "string", "minLength": 20, "maxLength": _MAX_B64},
                    "right_pgm": {"type": "string", "minLength": 20, "maxLength": _MAX_B64},
                },
                "required": ["left_pgm", "right_pgm"],
                "additionalProperties": False,
            },
        ),)

    async def call_tool(self, name: str, arguments: dict[str, object] | None = None) -> dict[str, object]:
        grant = current_dispatch()
        if (grant is None or grant.capability_id != _CAP or grant.tool_name != _TOOL
                or grant.risk_level != "medium" or name != _TOOL):
            raise StereoDepthDenied("AURA MCP Gateway authorization is required")
        if not isinstance(arguments, dict) or set(arguments) != {"left_pgm", "right_pgm"}:
            raise ValueError("Invalid stereo input schema")
        images = []
        for key in ("left_pgm", "right_pgm"):
            encoded = arguments[key]
            if not isinstance(encoded, str) or not 20 <= len(encoded) <= _MAX_B64:
                raise ValueError("Invalid stereo image encoding")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid stereo base64") from exc
            _pgm_bytes(data)
            images.append(data)
        left, right = images
        width, height, points = _match_rectified_pair(left, right, self._calibration)
        return {
            "width": width,
            "height": height,
            "pair_sha256": _pair_hash(left, right),
            "trust": "UNTRUSTED_STEREO_ESTIMATE",
            "samples": [
                {"x": p.x, "y": p.y, "disparity_px": p.disparity_px,
                 "depth_m": p.depth_m, "uniqueness": p.uniqueness}
                for p in points
            ],
        }


def register_local_stereo_depth(
    *, services: ServiceRegistry, providers: ProviderRegistry,
    capabilities: CapabilityRegistry, calibration: StereoCalibration,
) -> LocalStereoDepthMCP:
    """Explicit Core registration; intentionally creates no ALLOW policies."""
    if not (isinstance(services, ServiceRegistry)
            and isinstance(providers, ProviderRegistry)
            and isinstance(capabilities, CapabilityRegistry)):
        raise TypeError("Existing AURA Core registries are mandatory")
    backend = LocalStereoDepthMCP(calibration=calibration)
    if any(row.definition.provider_id == _PROVIDER for row in providers.records()):
        raise ValueError("Stereo provider already exists")
    if capabilities.providers(_CAP):
        raise ValueError("Stereo capability already exists")
    service = services.register(ServiceDefinition(
        name="aura-local-stereo-depth", version="1.0.0",
        provider="mcp", category=ServiceCategory.MCP,
    ), object())
    providers.register(ProviderDefinition(
        provider_id=_PROVIDER, name="Local stereo depth",
        version="1.0.0", service_id=service.service_id,
    ), backend)
    capabilities.register(CapabilityDefinition(
        capability_id=_CAP, name="Bounded local stereo depth",
        version="1.0.0", description="Compute sparse local depth from rectified grayscale images",
        provider_id=_PROVIDER, provider_type=ProviderType.MCP,
        category=CapabilityCategory.VISION, risk_level="medium", tool_name=_TOOL,
    ))
    return backend


class GovernedStereoDepth:
    """Per-pair consent, principal identity, strict Gateway permission and output checking."""

    def __init__(self, gateway: MCPGateway, *, authenticated_principal_id: str) -> None:
        if not isinstance(gateway, MCPGateway):
            raise TypeError("An existing MCP Gateway is required")
        if not isinstance(authenticated_principal_id, str) or not 1 <= len(authenticated_principal_id) <= 128 or authenticated_principal_id != authenticated_principal_id.strip() or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in authenticated_principal_id):
            raise ValueError("Invalid authenticated principal")
        self._gateway = gateway
        self._principal = authenticated_principal_id

    async def estimate(
        self, left_pgm: bytes, right_pgm: bytes, *,
        capture_confirmed: bool,
    ) -> StereoDepthEvidence:
        if capture_confirmed is not True:
            raise StereoDepthDenied("Explicit capture consent for both frames required")
        lw, lh, _ = _pgm_bytes(left_pgm)
        rw, rh, _ = _pgm_bytes(right_pgm)
        if (lw, lh) != (rw, rh):
            raise ValueError("Stereo pair dimensions differ")
        try:
            response = await self._gateway.invoke(MCPGatewayRequest(
                request_id="stereo:" + str(uuid4()), principal_id=self._principal,
                capability_id=_CAP, operation_id=_OP, resource_scope=_SCOPE,
                risk_level=RiskLevel.MEDIUM, tool_name=_TOOL,
                arguments={
                    "left_pgm": base64.b64encode(left_pgm).decode("ascii"),
                    "right_pgm": base64.b64encode(right_pgm).decode("ascii"),
                },
            ))
        except Exception as exc:
            raise StereoDepthUnavailable("Local stereo Gateway unavailable") from exc
        if response.decision is not AuthorizationDecision.ALLOW:
            raise StereoDepthDenied("Explicit per-pair stereo PermissionEngine ALLOW required")
        result = response.result
        if (response.provider_id != _PROVIDER or not isinstance(result, dict)
                or result.get("status") == "failed"
                or result.get("trust") != "UNTRUSTED_STEREO_ESTIMATE"
                or result.get("pair_sha256") != _pair_hash(left_pgm, right_pgm)
                or type(result.get("width")) is not int or result["width"] != lw
                or type(result.get("height")) is not int or result["height"] != lh):
            raise StereoDepthUnavailable("Untrusted stereo result did not match the input")
        rows = result.get("samples")
        if not isinstance(rows, list) or len(rows) > _MAX_POINTS:
            raise StereoDepthUnavailable("Stereo output exceeded bounded size")
        points: list[DepthSample] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"x", "y", "disparity_px", "depth_m", "uniqueness"}:
                raise StereoDepthUnavailable("Malformed stereo sample")
            x, y, d, depth, uniq = (row[k] for k in ("x","y","disparity_px","depth_m","uniqueness"))
            if (type(x) is not int or type(y) is not int
                    or type(d) is not int or not 1 <= d <= 32
                    or not 0 <= x < lw or not 0 <= y < lh
                    or type(depth) not in (float, int) or not math.isfinite(depth)
                    or not 0.05 <= depth <= 250
                    or type(uniq) not in (float, int) or not math.isfinite(uniq)
                    or not 0.18 <= uniq <= 1):
                raise StereoDepthUnavailable("Invalid stereo sample values")
            points.append(DepthSample(x, y, d, float(depth), float(uniq)))
        return StereoDepthEvidence(
            samples=tuple(points), pair_sha256=_pair_hash(left_pgm, right_pgm),
            width=lw, height=lh,
        )
