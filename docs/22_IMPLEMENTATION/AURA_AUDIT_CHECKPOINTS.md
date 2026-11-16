# Independent audit checkpoint (feature #107) — review-only slice

Source: core/src/aura_core/enterprise/audit_checkpoint.py.
Reuses the existing HashChainAuditLedger from enterprise/runtime_controls.py.

## Purpose
Create independently key-verifiable, non-authoritative checkpoints over metadata already recorded by the existing Gateway audit ledger. It does not invoke MCP tools, grant PermissionEngine policies, authorize Owner actions, or alter Gateway dispatch.

An external verifier supplies a separately held secret key (minimum 32 bytes) and exact scope. The checkpoint contains only schema, event count, terminal chain digest, HMAC-derived scope digest, previous checkpoint MAC, and current HMAC. It excludes principal IDs, tool arguments, prompts, provider output and the secret key.

## Use
```python
from aura_core.enterprise.runtime_controls import HashChainAuditLedger
from aura_core.enterprise.audit_checkpoint import create_audit_checkpoint, verify_audit_checkpoint

ledger = HashChainAuditLedger()
ledger.append(principal_id='owner', action='capability.read',
              resource_scope='local', outcome='denied',
              reason_code='policy_denied')
key = verifier_supplied_secret_key  # external secret; never commit
receipt = create_audit_checkpoint(ledger, key=key, scope='host-audit')
assert verify_audit_checkpoint(ledger, receipt, key=key, scope='host-audit')
```

Store receipt.to_dict() and the signing key in an independently protected, durable destination. Later appends require a new checkpoint with previous=receipt. Independently retaining the earlier checkpoint detects truncation and rewriting of the signed prefix. A previous receipt alone does not grant any authority.

## Security and acceptance limits
- SHA-256 hash chains alone do not authenticate the writer; HMAC authenticity depends on the externally protected secret.
- The ledger is still in-memory. This slice does not supply a durable/WORM sink, authenticated audit ingestion, external verifier service, secure key custody, independently authenticated identity, or complete capture of every tool execution.
- An attacker with both the ledger and the HMAC key can forge receipts. An attacker with a mutable in-memory ledger can suppress events before a checkpoint. Neither gap is solved here.
- A checkpoint is an integrity signal, not an Owner approval or a PermissionEngine/MCP Gateway execution grant.
- Standard-library-only; no external dependency, model or added license obligations.
- Real hardware, production incident investigation and independent host attestation remain unverified. Feature #107 is TESTING/PARTIAL_VERIFIED, not COMPLETED.

## Test commands
cd core && uv run pytest -q tests/test_audit_checkpoint.py
cd core && uv run python scripts/verify_final_lock.py

Full Core Assurance, Remote Persistence and Final Release Lock must pass on the exact PR head. After separately approved merges, recompute the common source-lock inventory and rerun CI; do not take arbitrary manifest conflict resolutions.
