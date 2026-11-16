# Safe authenticated live Core status — feature #93 (partial)

This PR adds a real low-information, read-only status projection from existing JAS Core `ServiceRegistry`, `CapabilityRegistry`, `ProviderRegistry`, `HealthMonitor` and `SystemTelemetry`. It does **not** create a second registry, observability daemon, policy engine, provider, MCP tool or request permission.

## Component and HTTP contract
- `core/src/aura_core/application/safe_live_status.py` contains `SafeLiveStatus` and an opt-in `live_status_router` for `GET /api/runtime/live-status`.
- The handler uses the existing `authenticated_principal` bearer dependency. No bearer gets **401** before telemetry sampling; missing server auth or missing configured status service gets **503**. Exceptions reveal only generic safe errors.
- The snapshot reports aggregate service/provider/capability health counts, CPU/memory percentages (finite, 0..100 only), timezone-aware sampling timestamp and **fixed allowlisted** `cpu_pressure`/`memory_pressure` alert codes. It never exposes service/provider IDs, capability names, machine endpoints, paths, model names, raw warning text, event payloads or token values.
- If telemetry is absent or malformed, status is `unavailable` and metrics are null; unhealthy/unreported components result in degraded/unknown counts without inventing a healthy status.
- No network or filesystem write, external model, command execution or MCP Gateway bypass occurs. Underlying SystemTelemetry remains the existing best-effort host collector; its optional psutil dependency status is not changed.

## Wiring and tests
Trusted application composition must explicitly set `app.state.safe_live_status = SafeLiveStatus(services, capabilities, providers, health, telemetry)` and `app.include_router(live_status_router)`. This isolated PR does **not** modify the large `application/api.py` composition root or automatically expose a new endpoint to a running instance. It is a usable authenticated FastAPI router and snapshot service whose production activation needs a later review.

`cd core && uv run pytest -q tests/test_safe_live_status.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Regression tests use real Core registries/HealthMonitor, a real FastAPI TestClient, fake telemetry readings, positive status, unauthenticated denial prior to sampling, absent configuration, bad/NaN metrics, registry failures, and forbidden provider/credential string redaction.

## Missing full acceptance
- No running HUD/desktop UI widget or live EventBus subscription, push transport, principal role separation or actual Windows/GPU health sensor hardware tests.
- Backend status remains sampled on request and is not independently guaranteed fresh. More granular metrics must be authorized explicitly before any user-facing broadcast; authentication by a bearer alone does not prove Owner enrollment.
- No production composition deployment or Owner security/privacy acceptance. Feature #93 remains `TESTING/PARTIAL_VERIFIED`, not COMPLETED.
- Standard-library and existing Core/FastAPI only; no new external license, service or model.
