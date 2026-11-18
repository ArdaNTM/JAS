"""Real sum-of-absolute-differences depth algorithm and Core Gateway security tests."""
import asyncio
import base64
import math
from dataclasses import FrozenInstanceError

import pytest

from aura_core.providers.stereo_depth_mcp import (
    DepthSample, GovernedStereoDepth, LocalStereoDepthMCP, StereoCalibration,
    StereoDepthDenied, StereoDepthUnavailable, _match_rectified_pair,
    _pgm_bytes, register_local_stereo_depth,
)
from aura_core.kernel.capabilities import CapabilityRegistry
from aura_core.kernel.permissions import (
    AuthorizationDecision, AuthorizationLevel, PermissionEngine, PermissionPolicy,
)
from aura_core.kernel.services import ServiceRegistry
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry


def _images(*, w=80, h=56, shift=5):
    # Synthetic textured, rectified greyscale stereo correspondence with known
    # pixel disparity. The actual deterministic SAD algorithm is executed.
    left_pixels = bytes(
        ((x * 73 + y * 29 + x * y * 11 + x * x * 7) % 256)
        for y in range(h) for x in range(w)
    )
    right_pixels = bytes(
        left_pixels[y * w + x + shift] if x + shift < w else 0
        for y in range(h) for x in range(w)
    )
    header = f"P5\n{w} {h}\n255\n".encode("ascii")
    return header + left_pixels, header + right_pixels


def _system(*, decision=None, calibration=None):
    services = ServiceRegistry()
    providers = ProviderRegistry(services)
    capabilities = CapabilityRegistry(services)
    backend = register_local_stereo_depth(
        services=services, providers=providers, capabilities=capabilities,
        calibration=calibration or StereoCalibration(focal_px=400, baseline_m=0.08),
    )
    engine = PermissionEngine(capabilities)
    if decision is not None:
        engine.add_policy(PermissionPolicy(
            policy_id="owner.stereo", policy_version="1.0.0",
            principal_id="owner", capability_id="vision.stereo.depth",
            operation_id="vision.stereo.depth",
            resource_scope="vision/consented/rectified-stereo",
            authorization_level=AuthorizationLevel.READ, decision=decision,
        ))
    reader = GovernedStereoDepth(
        MCPGateway(capabilities, providers, engine),
        authenticated_principal_id="owner",
    )
    return reader, backend, engine, providers, capabilities


def _run(reader, left=None, right=None, *, consent=True):
    a, b = _images()
    return asyncio.run(reader.estimate(
        a if left is None else left,
        b if right is None else right,
        capture_confirmed=consent,
    ))


def test_real_cpu_depth_algorithm_recovers_rectified_stereo_geometry():
    left, right = _images()
    w, h, samples = _match_rectified_pair(
        left, right, StereoCalibration(focal_px=400, baseline_m=0.08),
    )
    assert (w, h) == (80, 56)
    assert len(samples) >= 20
    assert sum(s.disparity_px == 5 for s in samples) >= len(samples) * 0.9
    assert [s.depth_m for s in samples if s.disparity_px == 5] == [6.4] * sum(
        s.disparity_px == 5 for s in samples
    )
    assert all(0.18 <= s.uniqueness <= 1 for s in samples)


def test_authorized_core_gateway_dispatches_real_local_matcher():
    reader, backend, engine, providers, caps = _system(
        decision=AuthorizationDecision.ALLOW,
    )
    evidence = _run(reader)
    assert len(evidence.samples) >= 20
    assert evidence.width == 80 and evidence.height == 56
    assert evidence.trust == "UNTRUSTED_STEREO_ESTIMATE"
    assert evidence.safe_for_physical_control is False
    assert len(evidence.pair_sha256) == 64
    assert providers.resolve("vision.stereo.sad.local") is backend
    assert caps.resolve("vision.stereo.depth").definition.tool_name == "estimate_stereo_depth"
    assert engine.audit_records()[-1].decision.decision is AuthorizationDecision.ALLOW
    with pytest.raises(FrozenInstanceError):
        evidence.samples[0].depth_m = 0


@pytest.mark.parametrize("decision", [
    None, AuthorizationDecision.DENY, AuthorizationDecision.REQUIRE_APPROVAL,
])
def test_no_policy_or_unconsumed_approval_fails_closed(decision):
    reader, backend, engine, *_ = _system(decision=decision)
    with pytest.raises(StereoDepthDenied):
        _run(reader)
    assert engine.audit_records()[-1].decision.decision is not AuthorizationDecision.ALLOW


def test_missing_double_frame_consent_is_denied_before_gateway():
    reader, _, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    with pytest.raises(StereoDepthDenied):
        _run(reader, consent=False)
    assert engine.audit_records() == ()


def test_direct_provider_execution_cannot_bypass_gateway():
    reader, backend, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    left, right = _images()
    with pytest.raises(StereoDepthDenied):
        asyncio.run(backend.call_tool("estimate_stereo_depth", {
            "left_pgm": base64.b64encode(left).decode(),
            "right_pgm": base64.b64encode(right).decode(),
        }))
    assert engine.audit_records() == ()


def test_flat_or_untextured_frames_return_no_fabricated_depth():
    w, h = 80, 56
    pgm = f"P5\n{w} {h}\n255\n".encode() + bytes([120]) * (w * h)
    reader, _, _, *_ = _system(decision=AuthorizationDecision.ALLOW)
    result = _run(reader, pgm, pgm)
    assert result.samples == ()
    assert result.safe_for_physical_control is False


@pytest.mark.parametrize("bad", [
    b"", b"this is not a PGM", b"P2\n80 56\n255\n" + b"\x00" * 4480,
    b"P5\n80 56\n256\n" + b"\x00" * 4480,
    b"P5\n80 56\n255\n" + b"\x00" * 4479,
    b"P5\n80 56\n255\n" + b"\x00" * 4481,
    b"P5\n10 56\n255\n" + b"\x00" * 560,
    b"P5\n80 500\n255\n" + b"\x00" * 40000,
    bytearray(_images()[0]),
])
def test_bad_pgm_rejected_before_policy_or_provider(bad):
    reader, _, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    with pytest.raises(ValueError):
        _run(reader, bad, _images()[1])
    assert engine.audit_records() == ()


def test_mismatched_dimensions_rejected_before_gateway():
    reader, _, engine, *_ = _system(decision=AuthorizationDecision.ALLOW)
    with pytest.raises(ValueError):
        _run(reader, _images()[0], _images(w=96)[1])
    assert engine.audit_records() == ()


@pytest.mark.parametrize("invalid", [
    {"focal_px": float("nan"), "baseline_m": 0.1},
    {"focal_px": float("inf"), "baseline_m": 0.1},
    {"focal_px": 49, "baseline_m": 0.1},
    {"focal_px": 400, "baseline_m": 0},
    {"focal_px": 400, "baseline_m": 1.01},
    {"focal_px": 400, "baseline_m": 0.1, "max_disparity": 100},
    {"focal_px": 400, "baseline_m": 0.1, "max_disparity": True},
])
def test_unsafe_calibration_rejected(invalid):
    with pytest.raises(ValueError):
        StereoCalibration(**invalid)


def test_unregistered_or_wrong_principal_cannot_open_gateway():
    services = ServiceRegistry()
    caps = CapabilityRegistry(services)
    providers = ProviderRegistry(services)
    gateway = MCPGateway(caps, providers, PermissionEngine(caps))
    for principal in ("", "owner\nadmin", " owner", "x" * 129, "\ud800"):
        with pytest.raises(ValueError):
            GovernedStereoDepth(gateway, authenticated_principal_id=principal)


def test_provider_result_tampering_is_not_trusted_even_with_allow():
    reader, backend, _, *_ = _system(decision=AuthorizationDecision.ALLOW)
    original = backend.call_tool

    async def bad(name, args):
        result = await original(name, args)
        result["samples"][0]["depth_m"] = float("inf")
        return result

    backend.call_tool = bad
    with pytest.raises(StereoDepthUnavailable):
        _run(reader)


def test_wrong_device_operations_not_available_to_stereo_reader():
    reader, _, _, *_ = _system(decision=AuthorizationDecision.ALLOW)
    assert not hasattr(reader, "move_robot")
    assert not hasattr(reader, "click")
    assert not hasattr(reader, "capture")
    with pytest.raises(TypeError):
        asyncio.run(reader.estimate(*_images(), capture_confirmed=True,
                                    principal_id="other"))


def test_no_auto_permission_and_duplicate_registration_rejected():
    reader, backend, engine, providers, caps = _system()
    with pytest.raises(StereoDepthDenied):
        _run(reader)
    with pytest.raises(ValueError):
        register_local_stereo_depth(
            services=providers._service_registry,
            providers=providers, capabilities=caps,
            calibration=StereoCalibration(focal_px=400, baseline_m=0.08),
        )
    assert len(providers.records()) == len(caps.records()) == 1
