# Core registry and policy integrity gate — feature #106 (partial)

Purpose: detect unexpected changes to the *existing* Core ServiceRegistry, CapabilityRegistry, ProviderRegistry and PermissionEngine before an MCP Gateway call. The small `PermissionEngine.integrity_digest()` method exposes a **read-only SHA-256 digest** of local active/revoked policies and optional enterprise policy bundle, without altering authorization decisions.

## Deny-only architecture
- `core/src/aura_core/enterprise/core_integrity.py` computes a deterministic bounded snapshot of registered service/provider/capability identity, tool binding, risk, health/state and effective policy digest.
- An independent caller supplies a verifier-held secret (>=32 random bytes) and exact scope. `attest_core_registries()` produces a metadata-only HMAC-SHA256 receipt; it never includes raw policy/principal text or the key.
- `verify_core_registries()` fails on wrong key/scope, forged MAC, altered provider/capability/service status, changed policy rules, malformed receipt or snapshot error.
- `GuardedMCPGateway` is an **opt-in deny-only adapter**. If verification fails, it emits a redacted `CoreIntegrityRejected` EventBus event and denies before provider dispatch. If valid, it calls the **original** MCPGateway, leaving PermissionEngine decisions, one-time approvals, tool schemas, circuit breakers and provider authorization unchanged.
- No new capability, service, default policy, Owner approval or direct tool/provider invocation is introduced. No external network or OS permission is needed.

## Usage sketch
```python
from aura_core.enterprise.core_integrity import (
    CoreRegistryState, GuardedMCPGateway, attest_core_registries
)
# These are the existing authoritative Core instances created by composition.
state = CoreRegistryState(services, providers, capabilities, permissions)
key = externally_provisioned_32plus_byte_secret
receipt = attest_core_registries(state, key=key, scope='aura-instance')
guarded_gateway = GuardedMCPGateway(gateway, state, receipt, key=key, scope='aura-instance')
# Every authorized execution entrypoint would have to use guarded_gateway.
```

## Verification
`cd core && uv run pytest -q tests/test_core_integrity_guard.py tests/test_permission_engine.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use actual Core registries/PermissionEngine and an MCPGateway with a fake provider; validate valid ALLOW, default DENY, REQUIRE_APPROVAL, policy revocation/addition, health/state drift, HMAC and scope forgery, invalid configuration, and redacted EventBus rejection.

## Critical limitations and acceptance blockers
- The signer/verifier secret is passed into a process and is **not independently hardware protected**. A privileged attacker controlling both key and process can forge receipts. An old valid state can be replayed without an external monotonic trust anchor.
- Existing production composition is **not rewired** to enforce this wrapper at every Gateway/tool entrypoint. Unwrapped calls still use the original Gateway. Registry snapshots taken across several locks are not transactionally atomic; legitimate policy/provider updates need a separately authenticated baseline rotation to avoid denial.
- The manifest check is file-level; this runtime HMAC is not a substitute for signed binaries, protected code pages, UEFI Secure Boot, Windows ACLs, TPM, external audit custody, immutable Owner Security or F2.7 broker proof.
- Independent source lock, production Owner enrollment, signed policy deployment, memory runtime tamper tests, full attack coverage, hardware/root-of-trust validation and cross-platform acceptance remain missing.
- Feature #106 must remain TESTING/PARTIAL_VERIFIED after exact PR CI; **never COMPLETED or immutable kernel** on this evidence.
