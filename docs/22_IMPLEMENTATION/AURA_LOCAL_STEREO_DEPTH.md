# Feature #81 — offline stereo 3D geometry, bounded real CPU depth engine

**Implementation:** `core/src/aura_core/providers/stereo_depth_mcp.py` adds a real, deterministic sum-of-absolute-differences 5×5 rectified-stereo matching engine, rather than a stub or model hallucination. It accepts two aligned monochrome **binary PGM/P5** frames, 48–512 pixels wide and 32–384 high, with bounded bytes and no disk, network, shell or GPU dependency. It samples local 5×5 patches at candidate pixel disparities, selects distinctive matches and computes `depth_m = focal_px * baseline_m / disparity_px` from a fixed rig calibration supplied by trusted local composition.

## AURA architecture

- Trusted composition registers `LocalStereoDepthMCP` in the existing `ServiceRegistry`, `ProviderRegistry` and `CapabilityRegistry` with fixed capability/operation `vision.stereo.depth`, tool `estimate_stereo_depth`, MEDIUM risk and scope `vision/consented/rectified-stereo`.
- No automatic permissions are installed. An authenticated principal is bound to `GovernedStereoDepth`; **each** `estimate()` requires explicitly confirmed capture consent for both images and a fresh `MCPGatewayRequest`. Any default DENY, DEFER or unconsumed REQUIRE_APPROVAL never reaches the matcher.
- The provider also checks an active short-lived `current_dispatch()` grant. Calling the Python provider directly bypassing MCP Gateway is refused.
- Sparse bounded output (at most 128 3D depth estimates) is cross-checked against exact pair SHA-256, original image dimensions and finite ranges. No raw frame is stored. Result is immutable `UNTRUSTED_STEREO_ESTIMATE`, explicitly `safe_for_physical_control=False`.

## Tests and actual algorithmic proof

`cd core && uv run pytest -q tests/test_stereo_depth_gateway.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests generate an actual textured 80×56 rectified grayscale stereo pair with known **5-pixel disparity** and independently run the real SAD matcher; recover depth near **6.4 metres** for focal length 400 pixels and 0.08-metre baseline. Additional real registries and actual PermissionEngine/MCPGateway cases cover exact ALLOW, default DENY, unconsumed approval, missing capture consent, direct provider bypass, flat texture (no invented points), malformed PGM, mismatched dimensions, invalid calibration and malicious provider metadata.

## Safety and genuine acceptance gaps

- **This is real stereo computational geometry but not a fully validated 3D perception system.** It assumes frames have already been **rectified and synchronized** by an authorized local camera calibration layer. Numerical calibration validation does not attest hardware origin, calibration accuracy, distance correctness or scene change timing.
- Camera drivers, stereo rectification/lens distortion, time synchronization, independent depth accuracy benchmarks, confidence calibration, stereo occlusion tests and real GPU/CPU target latency are not yet integrated. A robot or mouse may never execute physical actions from these depth points without independent validation and high-risk Owner+Gateway authorization.
- This intentionally uses the auditable Python standard library matcher on bounded local images; optional future OpenCV stereo acceleration must be integrated behind the **same** Gateway boundary with exact version/license governance.
- Mark feature #81 `TESTING/PARTIAL_VERIFIED` only after exact-head CI Core/Persistence/Final Release Lock. Do **not** mark `COMPLETED` without hardware acceptance.
