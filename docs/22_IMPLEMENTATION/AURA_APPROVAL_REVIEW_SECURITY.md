# Fail-closed approval review authorization — feature #100 (partial)

The existing HTTP approval API previously listed all pending records to any authenticated principal and allowed cross-principal decisions without a second authorization policy. This slice adds an explicit **existing Core PermissionEngine** review check.

## Security contract
- Bearer authentication remains server-owned via authenticated_principal. Header-supplied principal IDs are ignored.
- A requester can view their own pending record but cannot approve their own request.
- Reading another principal's pending approval requires PermissionEngine authorization for capability=approval.review, operation=approval.list and exact record scope.
- Deciding another principal's approval requires a separate explicit ALLOW for capability=approval.review, operation=approval.decide.
- Each authorization scope is approval/<percent-encoded requester>/<percent-encoded approval ID>. Requester IDs containing slashes cannot widen a scope.
- No approval.review provider or policies are automatically installed. Unless the composition root explicitly registers the capability and a narrow policy, review is default-deny. DENY/DEFER/REQUIRE_APPROVAL all fail closed.
- The existing SQLiteApprovalStore retains version/expiration/one-use atomicity. This change never bypasses the MCP Gateway to execute the approved tool; Gateway still consumes any valid approval before dispatch.

## Unfinished acceptance
These routes are reviewable subcomponents; main's application composition may not mount the approval router. There is no new authenticated multi-actor credential setup, verified Owner-signature custody, self-service reviewer enrollment, production UI, or external approval acceptance. A bearer identity is not proof of human identity. Actual composition root, device authentication, policy lifecycle and production integration remain outstanding.

## Tests
cd core && uv run pytest -q tests/test_approval_api.py tests/test_approval_review_authorization.py
cd core && uv run python scripts/verify_final_lock.py

Tests use the real CapabilityRegistry + ServiceRegistry, PermissionEngine, in-memory SQLiteApprovalStore, FastAPI TestClient and negative self-approval/cross-principal cases. No dependency additions. This is a PARTIAL feature #100, not COMPLETED.
