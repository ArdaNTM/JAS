# Feature #26 — genuine owner-approved local application supervision

Draft PR stacked on the #148 visual, vision and task integration. This is
real executable lifecycle control, not a mock or broad shell wrapper.
The existing AURA ServiceRegistry, ProviderRegistry, CapabilityRegistry,
PermissionEngine, MCPGateway and EventBus remain authoritative.

## Privileged execution
A trusted composition explicitly registers immutable TrustedApplication
profiles (fixed app ID, absolute executable, SHA-256 and fixed argument tuple)
before use. Models and API request payloads cannot select an executable path,
shell, arbitrary argv, environment, working directory or PID.

Three independent exact capabilities/scopes are registered:
- application.instances.read: LOW read-only, owned handles only.
- application.launch: HIGH, fixed trusted binary, consumed Owner approval.
- application.stop: HIGH, only a process handle created by this provider and
  associated with the exact principal, consumed Owner approval.

The backend requires a current_dispatch grant from the existing Gateway, and
for launch/stop requires grant.approval_consumed=True. A regular ALLOW policy
by itself cannot launch or stop a process: real SQLiteApprovalStore approval
must be decided by a separately authenticated human and consumed atomically,
bound to exact principal/capability/operation/scope/input fingerprint.

Local implementation uses subprocess.Popen(shell=False, close_fds=True,
stdin/stdout/stderr=DEVNULL) and a small explicit environment allowlist. It
verifies the executable SHA-256 and rejects a direct symlink executable.
Only private Popen handles are managed, never a user-supplied PID. Local
process cap is 8. Process lifecycle notifications use real Core EventBus,
with no process arguments, goals, paths or private stdout included.

## Executable positive and negative tests
Run cd core && uv run pytest -q tests/test_governed_app_supervisor.py
Run cd core && uv run pytest -q
Run cd core && uv run python scripts/verify_final_lock.py

Tests launch a **real local Python subprocess** with fixed trusted argv and
check no process exists before a human approval receipt is consumed. They
verify actual stop/reaping and event delivery, same-approval replay denial,
foreign principal isolation, default deny, direct backend call rejection,
bad binary hash, symlink alias, fixed argv and accidental ALLOW fail-closed.

## Limits / deployment blockers
No default executable catalog or insecure environment loading is installed:
a trusted Owner-controlled composition must supply audited profiles. Native
Windows protected-directory NTFS ACL/Owner consent UI, executable replacement
TOCTOU review, signed catalog identity, process-tree confinement and OS
resource budgets are NOT tested. This does not replace F2.7 or grant
arbitrary terminal execution. Lifecycle close kills only provider-owned children.
Feature #26 is TESTING/PARTIAL_VERIFIED only after exact-head green CI; do
not mark COMPLETED until physical Owner/host and security acceptance.
