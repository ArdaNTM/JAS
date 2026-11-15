# AURA engineering blockers

Updated 2026-11-15; evidence is repository inspection and user-supplied host logs, not independently verified host attestation.

- **F2.7 PR #64:** Draft; broker-owned VM lifecycle, signed isolation receipt, live SCM approval, and physical-host validation are not complete. Do not merge or activate.
- **117-feature assessment:** Existing code implements parts of several categories, but no comprehensive per-feature acceptance inventory has been demonstrated. Do not call unassessed features absent or complete.
- **Tools/hardware:** Dedicated physical robots, laboratory hardware, cameras and external keys cannot be claimed tested from CI.
- **External service/license audit:** Individual dependency/model licenses and cloud free-tier claims require review before selection.
- **Trust boundary:** Existing JAS Kernel/PermissionEngine/MCP Gateway and Owner approval must not be bypassed.
