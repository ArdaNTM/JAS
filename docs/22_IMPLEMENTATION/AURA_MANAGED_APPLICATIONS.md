# Feature #26 — real local managed-application lifecycle (review only)

Draft PR #149, stacked on PR #148. This implements an actual
supervised local subprocess lifecycle, not an arbitrary terminal,
process enumerator, unattended installer or systemwide process killer.

## AURA Core architecture
- Trusted composition predefines at most eight ManagedApplicationSpec
  entries with stable ID, canonical absolute executable, SHA-256 binary
  fingerprint and fixed bounded argv. Operator JSON <=32 KiB and
  executable <=128 MiB. No caller-provided command/path or shell.
- LocalManagedApplicationsMCP starts with subprocess.Popen(shell=False).
  Only provider-owned child processes keyed by bound principal and
  application ID can be stopped, via bounded terminate/wait/kill.
- applications.managed.read is LOW-risk scoped
  applications/managed/read-only, with an independent PermissionEngine
  ALLOW; only provider-owned process status is exposed.
- applications.managed.start/stop are HIGH-risk with separate
  per-application scopes applications/managed/{app_id}/lifecycle.
  Even a normal Gateway ALLOW is insufficient. Provider requires a
  DispatchGrant containing approval_consumed=True from the existing
  one-shot SQLite/PostgreSQL approval workflow. The human approver must
  authenticate via an existing independent review surface. No grants
  are created at registration.
- EventBus emits metadata-only ManagedApplicationStateChanged. These
  events do not grant authority or control external applications.
- Production composition is opt-in through AURA_MANAGED_APPLICATIONS_ENABLED=1
  and absolute AURA_MANAGED_APPLICATIONS_MANIFEST path. Missing/untrusted
  manifest fails closed. Windows manifest loading fails closed until
  independent Owner NTFS ACL attestation is proven.

## Executable and security regression
- cd core && uv run pytest -q tests/test_managed_applications_gateway.py
- cd core && uv run pytest -q
- cd core && uv run python scripts/verify_final_lock.py

Tests launch and terminate a real local Python interpreter child process
without mocking subprocess execution, prove one-shot approval consumption,
fresh separate approval for stop, replay rejection, default DENY, pending
REQUIRE_APPROVAL, direct provider bypass, principal mismatch, invalid IDs,
no arbitrary argv, no system-wide PID stopping, digest failure and
untrusted manifest rejection.

## Unverified acceptance gates
- No trusted NTFS ACL/root-of-trust attestation, Authenticode verification,
  independently measured Windows GUI launch/desktop focus, process Job
  Objects, child-tree termination, system service management, signed
  trusted configuration, host performance or Owner hardware acceptance.
- Binary digest checks cannot fully eliminate replace-after-hash races.
  Fixed arguments referencing mutable script/config files need separate
  trusted provenance. Native owner review UI/real desktop must be tested.
- No F2.7 change, no main push, no merge, no COMPLETED declaration.

## Additional validated safety constraints

- Child subprocess environment uses a narrow fixed allowlist (system path/home/locale variables only), so AURA provider keys, API bearer tokens and database credentials are not inherited. A real subprocess negative test checks the credential canary is absent.
- At most eight child processes may be running at one time across all principals, independent of the eight-profile registration cap. A process launch is never retried automatically after a denial.
- No claim of Windows target acceptance: the opt-in manifest is deliberately blocked there until owner ACL attestation is implemented. This remains a PARTIAL implementation.
