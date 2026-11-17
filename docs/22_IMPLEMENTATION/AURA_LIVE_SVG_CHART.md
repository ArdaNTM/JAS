# Feature #95 — live SVG telemetry visualization powered by EventBus and MCP Gateway

**Stacked on PR #144**: this is a working offline, zero-JavaScript/zero-cloud dynamic visualization of actual AURA Core Gateway runtime timings. It implements a genuinely rendered SVG line graph and a real protected FastAPI endpoint, not a frontend placeholder.

## Runtime integration

`AURA_LIVE_CHART_ENABLED=1` opts the existing production `build_app()` into `register_live_svg_chart(...)`. The module registers a concrete local MCP provider in the existing `ServiceRegistry`, `ProviderRegistry` and `CapabilityRegistry` (`visualization.telemetry.read`, risk `LOW`, tool `read_latency_samples`, scope `visualization/gateway-latency/read-only`). No default read policy is added. The provider subscribes to the **existing** `EventBus` for `Telemetry.MCPGatewayExecution` emitted by the live Core `RuntimeProfiler` and collects only bounded numeric `duration_ms` from events claiming `source_component='aura.mcp.gateway'`. No raw prompts, URLs, event diagnostics, principal IDs, tokens, tool arguments or provider names are copied.

An independently authenticated local Owner must configure a server-side bearer token (`AURA_API_BEARER_TOKEN` at least 32 characters) and principal identity (`AURA_API_PRINCIPAL_ID`). Endpoint `GET /api/runtime/gateway-latency.svg` checks bearer auth and exact bound principal **and then** invokes `GovernedLiveSVGChart.render()`; each render issues a fresh MCPGatewayRequest requiring an explicit **PermissionEngine ALLOW** for the exact capability and scope. An absent/denied/approval-required policy returns 403 without samples.

The provider only returns an array of finite, bounded floating-point milliseconds; any direct call outside an authenticated Gateway `current_dispatch` grant fails. The trusted Core client renders a genuine SVG path from revalidated numbers. Untrusted provider markup is **never** included, preventing SVG XML/script injection. Graph shows at most 120 recent numeric samples on a fixed 0–2,000ms axis, and a zero-sample chart until real telemetry has been dispatched. SVG response disables caching and includes a restrictive Content Security Policy. Provider event subscription is released during AURA lifespan shutdown.

## Real tests

`cd core && uv run pytest -q tests/test_live_svg_chart.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

The test suite instantiates **real** AURA EventBus, Service/Capability/Provider registries, PermissionEngine and MCPGateway, publishes/dispatches actual KernelEvent measurements, verifies deterministic SVG geometry, sanitized output, bounded 120-sample buffer, default DENY and REQUIRE_APPROVAL, fake source/numeric injection, direct-provider bypass, redacted provider exception and authenticated **real FastAPI/TestClient** HTTP rendering, 401/403/503 and no auto-grant.

## Acceptance gaps

- This is a real Core telemetry visualization but **not yet** a production graphical HUD/window; native multi-monitor Electron integration, animations, live user feedback, actual Windows GPU/render latency, accessibility and long-session memory behaviour require Owner tests.
- If the Core event transport is not running, the graph stays empty, correctly. An in-process event source is not independently cryptographically attested: sample values remain `REDACTED_UNTRUSTED_TELEMETRY` rather than proof of a production service level.
- Feature #95 remains `TESTING/PARTIAL_VERIFIED` after exact-head CI and release-lock verification, not COMPLETED. PR #144 must be reviewed together with its earlier unmerged dependencies. No new external model/dependency/license.
