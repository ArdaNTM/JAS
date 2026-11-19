# Deterministic multi-screen HUD layout preview — feature #92 (partial)

Stacked dependency: **Draft PR #125**, feature #28, supplies validated immutable Core monitor geometry in `aura_core.application.monitor_topology`. This new feature provides `aura_core.application.hud_layout_plan.plan_hud_layout` for *preview-only* HUD panel rectangles; it does not create windows, draw pixels, grant screen/OS privileges, read actual monitors, or choose new MCP policies.

## Contract
- Accept a validated `DisplayTopology`, recheck both its digest and bounds by rerunning the existing #28 validator (constructing the dataclass manually is **not** proof of authenticity), plus 1–12 explicitly named bounded HUD panel requests.
- Panels can target the trusted primary display or an explicit ephemeral display ID; unknown IDs are rejected, never silently remapped.
- Calculate scale-aware integer pixel rectangles at one of four safe corners; preserve negative coordinates for multi-monitor desktops; deterministic per-anchor stacking and margins/gaps prevent clipping outside chosen display.
- Fail closed on duplicate/invalid IDs, invalid anchor/spacing/dimensions, unsupported topology, panel overlap, stack overflow, forged display bounds, and panels too large for the actual target.
- Output is immutable `HUDLayoutPlan(preview_only=True)`. Any actual HUD rendering, input interactions, screen capture, panel host control, or window positioning must be separately authorized and implemented by the trusted desktop runtime. MCP Gateway remains the sole tool-execution boundary.

## Tests
`cd core && uv run pytest -q tests/test_hud_layout_plan.py tests/test_monitor_topology.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

## Acceptance limitations
- This PR depends on #125 and **must target its feature branch**, not main. Until Owner approves the upstream merge, the combined lock only proves the stacked branch's exact sources.
- No Electron/UI/desktop overlay implementation, hardware DPI/hotplug/monitor mirroring acceptance, click-through/cross-app visual ordering, Owner UI consent, operating-system testing or actual multi-screen HUD demonstration.
- Geometric overlap checks assume rectangular displays without protected app windows or system/taskbars. Not a content-aware HUD-placement policy.
- Feature #92 remains TESTING/PARTIAL_VERIFIED after exact-head CI; no production/hardware acceptance or COMPLETED claim. No new dependency/license.
