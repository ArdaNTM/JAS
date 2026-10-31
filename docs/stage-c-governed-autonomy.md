# AURA Stage C: review-only release candidate

## Security boundaries
AURA deterministic Kernel, registries, PermissionEngine, EventBus and MCP Gateway
remain the only authority. LangGraph is an unprivileged orchestrator.
The Stage C planner proposes a bounded catalog of `ScreenControl` and
`BrowserControl` MCP operations; it cannot create permissions.

**All actions require a consumed Gateway approval**. HUD can only submit,
inspect, request re-check of an externally decided approval and permanently stop
new actions. It never signs, issues or approves passkeys.

The SQLite ledger persists reservation **before** invoking the Gateway.
A crash, cancellation, timeout or transport uncertainty during an in-flight
action locks the run into `needs_review`: no automatic replay. One GUI action
at a time globally. Budget is eight operations (including pending approvals),
120 seconds wall-clock from creation. Kills persist across restarts.
An already dispatched native Windows input cannot be retracted.

## Enable only in disposable evaluation environments

Stage C is **off by default**. The separate Owner Control Plane remains
separate from Core. Operators must provision a private Stage C directory
(NTFS private and non-inherited ACL on Windows; chmod 0700 on Unix), explicitly
set `AURA_STAGE_C_DB_PATH` to an absolute path, and configure the existing
approval store and `AURA_APPROVAL_FINGERPRINT_KEY`. On Windows, use the
repository's existing trusted owner ACL provisioning procedures for a new
dedicated application-state directory; never reuse the owner signing-key folder.

- `AURA_STAGE_C_ENABLED=1` enables only the bounded control API.
- `AURA_SCREEN_CONTROL_ENABLED=1` independently enables the existing
  Windows SendInput provider; approval store is required.
- `AURA_STAGE_C_BROWSER_ENABLED=1` enables the optional browser provider.
  It requires `AURA_STAGE_C_EGRESS_ISOLATED=1` and a comma-separated
  `AURA_STAGE_C_BROWSER_ORIGINS` list of exact public HTTPS origins.
  The proxy/firewall **must** block metadata, loopback and private networks.
  Route/DNS checks are defense-in-depth and do not eliminate DNS rebinding.
- `AURA_STAGE_C_DB_PATH=D:\\AURA-Private\\stage-c.sqlite3` (example only).
- Run `uv run --frozen playwright install chromium` before browser evaluation
  (network download requires explicit operator action).

Never enable desktop automation in your everyday administrator desktop for the
initial evaluation. Run one disposable account and VM. No unattended remote
login, no credential handling, no unrestricted shell, no cross-origin navigation.

## API / operator sequence

1. GET `/api/stage-c/status` as the authenticated local principal.
2. POST `/api/stage-c/runs` with `{"goal":"...","confirmed":true}`.
3. GET `/api/stage-c/runs/{id}` until `awaiting_approval`.
4. Approve only via a separate authorized approval process; the HUD does
   not decide any approval. The Gateway checks fingerprint and consumes once.
5. POST `/api/stage-c/runs/{id}/resume` to re-check external approval.
6. POST `/api/stage-c/kill-switch` to persist emergency stop; there is **no**
   remote/HTTP reset. Do not delete database to bypass kill governance.

## OSWorld-V2.1 and hardware laboratory

```powershell
cd D:\AURA\JAS-stage-c-test\core
uv run --frozen python scripts/osworld_v2_lab.py
uv run --frozen python scripts/hardware_stage_c_acceptance.py
uv run --frozen python -m pytest -q tests/test_stage_c_runtime.py
```

The lab script emits offline provenance and evidence requirements only. This
is **not** a real OSWorld benchmark score or successful hardware acceptance.
Official OSWorld-V2.1 requires independently pinned code, task classes,
assets, mock websites and provider VM images from the same `osworld-v2.1`
release, with upstream gated downloads, self-hosted sites and operator-led
isolation. No downloads, billing, AWS provisioning or physical inputs happen
in these scripts.

## Release gates
Core full pytest, Windows ACL acceptance, Electron HUD tests, both npm audits,
release-lock cross-platform verification and live hardware validation.
Browser DNS pinning/egress proxy, native input cancellation and signed
independent hardware results remain non-negotiable production gates.
