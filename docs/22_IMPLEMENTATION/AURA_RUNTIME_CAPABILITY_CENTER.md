# AURA Runtime Capability Center — Bounded 117-source integration

Authority: ArdaNTM/JAS. Baseline: Owner-merged main 149c27e4400b1d1d5cc9b1a1c40b78166c64b580.

## Runtime truth

The 117 COMPLETED tracker entries are bounded source-v1 acceptances, NOT 117 active tool instances. Startup registers each pinned descriptor from core/src/aura_core/application/feature_index.json as a non-executable, unavailable metadata CapabilityDefinition under an actual FeatureCatalog ServiceRegistry and ProviderRegistry instance. The index mirrors the canonical docs/22_IMPLEMENTATION/AURA_FEATURE_TRACKER.json and its labels/IDs/phases are checked in tests. No fake MCP executor or runtime ALLOW policy is created for source-only entries.

Executable tool listings come only from actual Kernel CapabilityRegistry definitions with ProviderType.MCP and an exact tool_name connected by existing production bootstrap: TieredMemory, GraphMemory, ScreenRead/Control, opt-in live chart, managed applications, Docker terminal, research/TTS/filesystem stdio, etc. Unregistered or unhealthy providers are never presented as executable. F2.7 sealed security boundaries and physical hardware remain outside any catalog permission.

Authenticated routes:
- GET /api/capabilities/center: 117 descriptors and separately registered MCP tools; metadata status is not authorization or readiness.
- POST /api/capabilities/center/invoke: bound to an existing MCP capability; client may supply a resource_scope, JSON arguments and optionally an already-approved approval_id. The principal, operation ID, bound tool name, provider and risk level are server-owned. Existing MCPGateway.invoke is the only dispatch path. A denied/pending request does not execute a provider.

The new panel is the default Electron/Vite main view with a HUD tab. Execution is manual and never triggered by clicking a feature row. No implicit PermissionEngine ALLOW. The existing loopback Vite proxy injects the API bearer token server-side; browser code never stores it.

## Actual 500 trace was not included

The supplied PowerShell transcript contains no matched exception or traceback, only a route listing. Thus the exact old chat/task HTTP 500 has not been independently reproduced or resolved. The new center converts its own unavailable/invalid provider failures to typed 401/403/404/422/502/503 responses with Core X-Request-ID. Do not claim the unrelated old failure is fixed without a failing method/path, request ID, traceback and a matching regression test.

Read-only Windows diagnosis (do not paste bearer tokens):

    Select-String -Path D:\AURA\JAS\aura-daemon.stdout.log,D:\AURA\JAS\aura-daemon.stderr.log -Pattern 'HTTP request failed|Unhandled API exception|Traceback|http_unhandled_exception' -Context 2,12

Also record the failing HTTP method, URL path and X-Request-ID from DevTools Network.

## Verification

    cd core
    uv run pytest -q --tb=short tests/test_capability_center.py
    uv run pytest -q --tb=short
    uv run python scripts/verify_final_lock.py
    cd ../aura-ui
    npm ci --no-audit --no-fund
    npm run build

The Windows launcher CI builds aura-ui on source changes; a successful CI build is not proof of hardware or specific Windows runtime acceptance.
