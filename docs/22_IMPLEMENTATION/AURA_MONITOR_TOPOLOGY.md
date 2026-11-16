# Read-only validated multi-monitor topology — feature #28 (partial)

Existing AURA Electron/HUD already uses desktop display enumeration. This new **Core-side**, portable metadata contract accepts monitor descriptors supplied by a trusted shell with an explicitly confirmed local UI session; it never enumerates monitors itself, reads pixels, controls windows, or grants any OS/MCP/Owner permission.

## Behavior
- `validate_display_topology` accepts 1–8 immutable `DisplayGeometry` entries (ephemeral display IDs; signed origin coordinates including valid negative positions; bounded dimensions/scaling; exactly one primary). Reject malformed IDs, duplicate entries, controls/Unicode invalidity, unbounded scale/dimensions/coordinate extents and boolean-number confusion.
- Returns canonical ID-sorted metadata with a stable SHA-256 **change fingerprint**, primary and virtual desktop bounds. The digest is **not** device identity, ownership proof, EDID attestation, trusted hardware provenance or a security boundary.
- `MonitorTopologyObserver` requires a separately authenticated and explicitly confirmed local shell session. Emits `DisplayTopologyChanged` to the existing Core EventBus only on changed snapshots; the event carries coarse display count/bounds/session only, **not** display IDs, screenshots or screen content.
- Session stop invalidates the observer generation. Concurrent analysis cannot publish stale events after stop. No provider execution, mouse/keyboard operations, window manipulation or Gateway bypass.

## Verification
`cd core && uv run pytest -q tests/test_monitor_topology.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

## Missing acceptance
- No real Electron/native display bridge or authenticated display inventory API wiring, Windows/Linux/macOS hardware tests, monitor hotplug input, DPI transformation, mirrored display semantics, HUD placement or multi-screen rendering (#92). Geometry still comes from an upstream source that must be trusted and validated by the real deployment.
- The EventBus metadata signal is not an Owner command, permission, or authenticated hardware identity. Any actual screen capture or system control remains subject to separate user consent and MCP Gateway/PermissionEngine authorization.
- No new dependency or license. Feature #28 remains TESTING/PARTIAL_VERIFIED only after exact-head Core/Persistence/Release Lock CI, never COMPLETED without real integration and Owner hardware acceptance.
