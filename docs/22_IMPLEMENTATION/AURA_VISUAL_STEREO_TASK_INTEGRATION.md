# Integration review — stereo geometry (#81), live telemetry (#95), task panel (#97)

Stacked on Draft PR #147, combining unmerged Draft PR #145 real sparse
stereo matcher with the #144 -> #146 -> #147 real local Core stack. No
merged PR, main direct push, or F2.7/Owner boundary change.

The same existing AURA Core ServiceRegistry, ProviderRegistry,
CapabilityRegistry, EventBus, PermissionEngine and MCP Gateway register
all three independently authorized capabilities. Exact PermissionEngine
scopes remain separate:
- vision.stereo.depth / vision/consented/rectified-stereo
- visualization.telemetry.read / visualization/gateway-latency/read-only
- visualization.tasks.read / visualization/tasks/read-only

The integrated tests execute real locally matched rectified stereo
input, Gateway runtime profiler -> EventBus -> SVG, and persisted
SQLite task state -> Gateway task panel in one Core composition.
An authorization grant for stereo does not grant task or telemetry
access. Stereo evidence never provides actuation authority or changes
task state. No raw frames or task goals are persisted in HUD results.

Final complete release source lock must account for 263 canonical
source files, and exact-head full CI and persistence workflows must
PASS before referring to the branch as verified.

Acceptance remains PARTIAL for each: no calibrated physical stereo
rig/Owner identity, native Electron multi-monitor panel, signed
cross-process telemetry, remote device benchmarks, or older sealed
PR #64–#111 cumulative integration. Do not merge automatically or
declare any feature COMPLETED without those gates.
