# AURA — Governed Evolution Engine (review-only first release)

## Security principle

This is an **owner-governed evolution scaffold**, not self-replicating code.
It cannot promote generated Python into the trusted Core interpreter. The
Kernel, registries, PermissionEngine, MCP Gateway and JAS version governance
remain the only execution/authorization boundary.

A source-code model may suggest improvements, but its proposals are untrusted
data. The phrase "make yourself the most advanced AI" is **not** a standing
permission for self-modification, network calls, package installation or tool
activation. These require separate, explicit owner decisions.

## Implemented architecture

`evolution/autonomous_analyzer.py`
- Bounded read-only traversal of `core/src/aura_core`, `aura-ui/src`,
  and `docs`; rejects symlinks and known sensitive file/path names.
- Reports TODO/FIXME comments, Python syntax errors and silent exception
  handlers with path, line, SHA-256 and deterministic proposal ID.
- Reads up to 12 `logs/*.log` files with 32 KiB tails; returns counts of
  error categories only. **Never exposes raw log lines**.
- No network traffic, write operation, command execution or model inference.

`evolution/evolution_planner.py`
- Explicit opt-in `AURA_EVOLUTION_REVIEW_ENABLED=1`; separate from
  `AURA_BACKGROUND_THINKING_ENABLED=1`.
- Runs after 300 seconds idle (configurable within 60..86400), at most
  once every 900 seconds (configurable), capped at 100 cycles per runtime.
- Deduplicates bounded proposals in memory, exposes read-only
  `GET /api/evolution/status` and `GET /api/evolution/proposals`
  through existing authenticated local HTTP control plane.
- Optional discovery and draft adapters must be injected by the trusted
  composition root. **They are not installed by default**: this release does
  not autonomously search GitHub or invoke a code-writing LLM. An injected
  discovery adapter must call the existing authorized research capability,
  never raw HTTP on its own.
- Drafts are passed to existing `CandidateToolValidator` and remain
  proposal-only. AST analysis is **not** equivalent to sandbox isolation.

`evolution/skill_registry.py`
- `stage`: hash-binds a declarative alias to an existing registered MCP
  capability (no Python import, package install or dynamic execution).
- `validate`: independent attestation callback verifies sandbox evidence
  for exact candidate SHA-256; test results cannot self-approve.
- `activate`: checks the current healthy provider, valid sandbox evidence,
  and a one-time explicit owner approval for the full versioned manifest.
- `rollback` / `revoke`: require fresh owner approval; rollback requires
  previously attested artifact evidence. Newly selected aliases dispatch
  exclusively through MCP Gateway and current PermissionEngine policies.
- `owner_authority.py`: helper consumes a one-time
  `SQLiteApprovalStore` record and independently checks
  `PermissionEngine.authorize` for a JAS-governed
  `GovernedSkillActivation` capability. It NEVER creates or approves records.
  There is no unauthenticated activation HTTP endpoint.

## Deployment / owner trust boundary

The owner approval UI and independent attested sandbox runner are **external
trusted dependencies**. They are not implemented as arbitrary Python
`lambda: True` handlers in production. Until the JAS release governance layer
registers the capability and its explicit policy, activation **fails closed**.

Real immutability requires OS ACLs, read-only mounted Kernel code, signed
release artifacts, policy updates outside the agent's writable workspace
and an independent owner authentication mechanism. Marking a Python
directory "immutable" within agent-managed code is insufficient.

Drafted tools MUST be isolated in a networkless, socketless, resource-bounded
sandbox. Passing tests is necessary but not sufficient: review tool
permissions, provenance, dependency supply chain, rollback impact and
approval scope. This branch never executes untrusted artifacts.

If `AURA_STORAGE_MODE=remote`, the optional worker retains its backlog
only in memory and **never falls back to local SQLite**. Durable future
evolution proposals must use an explicit PostgreSQL repository adapter.

## Operator checks

1. Enable `AURA_EVOLUTION_REVIEW_ENABLED=1`, start Core normally,
   and inspect `/api/evolution/status`. An idle session yields reviewable
   proposals; default is disabled.
2. Confirm no change to the working tree or imported Python modules.
3. Check sanitized log categories; secret strings never appear in responses.
4. Validate that fake sandbox receipts, forged owner identity, stale versions
   and retired providers fail closed.
5. Validate rollback and revocation each consume separate owner approvals.
6. Confirm actual tool calls still require Gateway authorization.
7. Disable the flag and restart to stop the worker.

## Follow-up implementation gates

- Owner-authenticated signing service for `GovernedSkillActivation` receipts,
  independent OS-isolated sandbox attester, opt-in research adapter using
  existing SearXNG/GitHub MCP capabilities, durable remote proposal storage,
  per-skill provenance review, CI and native operator acceptance.
- No claim of always-on code rewriting, unbounded autonomous execution,
  automatic library acquisition or safe `importlib` execution in Core.

## Owner-approved candidate smoke test

`evolution/sandbox_review.py` offers `GovernedSandboxReview.smoke_test`
as a separately invoked review step. It requires an existing **high-risk**
`sandbox.codeact.execute` approval ID for each run, validates the bounded
candidate shape and expected JSON cases, and dispatches the code/test harness
ONLY through the MCP Gateway → pre-registered CodeAct Docker provider.

A smoke result is **provisional**, not a signed independent attestation:
malicious code can tamper with tests inside its own process. The active
`GovernedSkillRegistry.validate` callback must independently verify a
trusted sandbox attestation bound to the exact artifact SHA-256.

In packaged deployments the opt-in source root should be explicitly supplied
as `AURA_JAS_ROOT`; it must point to a valid JAS checkout. No missing-source
fallback is allowed. The scanner stops after repeated persistent failures.


## Review-only Goal Tree and quarantined mutation drafts

`evolution/goal_tree.py` groups at most 100 source-backed findings into
stable goals such as `runtime_reliability`. It does not send code/logs to
a model, decide privileges or turn broad instructions into deployment consent.
The authenticated, loopback-only `GET /api/evolution/goals` endpoint
returns this bounded, non-executable view when review is enabled.

`evolution/mutation_engine.py` is a **quarantined review queue**, not a
self-modifying agent. It accepts at most 20 bounded candidate drafts
as untrusted in-memory data, statically checks proposal shape, enforces
a 3-revision budget and records source SHA-256 without writing Python
to the live checkout or skill DB. Optional smoke tests **require a fresh
Local Owner approval** and execute only via `GovernedSandboxReview` →
MCP Gateway → isolated Docker CodeAct provider. A smoke test never creates
independent attestation, permission policies or a hot reload.

There is intentionally no `importlib` of generated source, no copy into
`core/src/aura_core/mcp/dynamic_tools`, no network scraper and no automatic
release-lock regeneration: source changes remain ordinary reviewed Git
commits. The existing `GovernedSkillRegistry` is the only declarative
owner-approved version switch for **already registered** MCP providers.


## Primal Anchor v2 — independent sandbox attestation (prototype)

The Core verifier at evolution/sandbox_attestor.py verifies Ed25519 signed,
canonical domain-separated v1 evidence. No private signing key is present in
the Core or sandbox. Signed claims bind:

- Candidate source SHA-256 and complete test-suite SHA-256.
- Immutable OCI container image digest (sha256), never a mutable image tag.
- SHA-256 of the isolated-runner security policy and complete reviewed MCP
  SkillBinding digest (capability, version, scope, operation and risk).
- Trusted runner identity, unique run ID, observed exit code, success status,
  issue/expiry timestamps (maximum 15 minutes), no-network and readonly
  rootfs observations.

Verifier pins the allowed Ed25519 public keys, runner ID, OCI image, test
suite and policy hash. Invalid signatures, tampering, wrong context, expired
results and failed isolation are rejected. AttestationReceiptRegistry admits
a signed run once, rejects duplicate run IDs and returns a receipt ID. On
lookup it rechecks validity and returns false after expiry. A trusted
AttestationReceiptRegistry.verify_binding callback may be injected as
signed_attestation_verifier into GovernedSkillRegistry; this adds a second,
signed cryptographic gate to the existing legacy sandbox-validation callback
during validate, activate AND rollback. Actual tool invocation remains
separately authorized by MCP Gateway and PermissionEngine.

The signer at core/scripts/evolution_attestor_sign.py is a SEPARATE,
operator-controlled CLI, not an MCP capability. It reads a trusted observation
and an Ed25519 PEM private key from outside the JAS checkout. Only the
separately provisioned operator attestor process may access the private key.
The signing CLI DOES NOT launch Docker or directly observe container exit,
network, mount state or test execution. Before treating an attestation as
production evidence, an independent trusted runner/observer must supply
observations directly and verify those facts through the container runtime.
A signed forged observation is still false. Smoke tests are provisional,
not independent signed attestations.

Replay limitation: duplicate (attestor key, runner job ID) registration is
blocked within one runtime. Its current bounded in-memory replay ledger does
NOT survive restart. A production attestor requires a durable owner-protected
ledger with an atomic unique-run constraint. Expiry and the separate one-shot
human owner approval remain mandatory. Runtime tests use ephemeral keys only.

Windows isolated acceptance:
1. In D:\\AURA\\JAS-evolution-test\\core run: uv sync --frozen --group dev
2. Run: uv run --frozen pytest -q tests/test_sandbox_attestor.py tests/test_governed_evolution.py tests/test_governed_evolution_owner.py
3. Run: uv run --frozen python scripts/verify_final_lock.py

Nothing is promoted into the trusted Core, no generated modules are imported,
and neither owner approval UI nor independent runner service are claimed
production-ready yet.


## Primal Anchor v2.1 — durable replay and owner passkey proof

New \`evolution/durable_attestation.py\` uses a preprovisioned, absolute,
owner-controlled SQLite file outside the AURA checkout. Transactions use
\`BEGIN IMMEDIATE\`, uniqueness on \`(key_id, run_id)\`, and full synchronous
commits to prevent replay across restarts and concurrent writers. The receipt
is re-verified against the pinned Ed25519 public key, image, test, policy,
source and MCP binding identities on every lookup and expires independently.
For actual production isolation, the replay ledger must be hosted by an
independently privileged owner control-plane process, not mounted writable in
Core or sandbox. OS ACLs (including Windows NTFS ACLs) must protect this data.

\`evolution/owner_passkey.py\` verifies registered WebAuthn ES256/P-256
assertions with exact \`localhost\` RP ID, expected \`http://localhost:5173\`
origin, challenge, credential ID, UP+UV flags and signature counter. This is
compatible with WebAuthn platform authenticators such as Windows Hello, but
hardware/device acceptance has NOT been demonstrated. It is NOT a Windows
Hello-specific password/prompt shortcut.

\`evolution/owner_challenge.py\` provides a trusted owner control-plane
library for one-shot, 90-second challenge creation and consumption. It binds
each challenge to an existing pending \`GovernedSkillActivation\` approval,
exact approval version and pinned policy digest, persists challenge consumption
and signature counter, and ONLY then records a
\`human:local-owner\` approval or denial. Duplicate challenge use, stale
approval identity and counter rollback are rejected. Separate owner
authentication is mandatory for sandbox smoke tests as well.

**Still to integrate before production**: a separate authenticated HTTP
control-plane service and credential enrollment, Windows Hello/passkey
browser UI with CORS/CSRF/origin controls, protected durable owner approval
store, NTFS ACL verification, and a real independent sandbox runner. Core's
existing bearer auth and untrusted React click handlers are NOT suitable
substitutes for physical Local Owner proof.

Important: current Vite UI uses 127.0.0.1:5173, while this passkey policy is
pinned to localhost:5173. Do not enable a passkey UI until the browser origin
and RP ID are migrated/tested deliberately, without broad wildcard origins.
No new approval route is mounted by this revision. The feature remains
disabled until the separate owner service has been provisioned.

Run local focused tests in the existing isolated worktree:
\`\`\`powershell
Set-Location D:\\AURA\\JAS-evolution-test\\core
uv sync --frozen --group dev
uv run --frozen pytest -q tests/test_evolution_owner_passkey_and_replay.py tests/test_evolution_owner_challenge.py tests/test_sandbox_attestor.py tests/test_governed_evolution_owner.py
uv run --frozen python scripts/verify_final_lock.py
\`\`\`


## Primal Anchor v2.2 — Trusted Owner Review UI (opt-in, fail-closed)

`aura-ui/src/components/EvolutionReviewPanel.tsx` is a **read-only**
dashboard for evidence-backed goal groups. Its amber external link opens a
separate origin: **http://localhost:8766/**. The existing AURA Vite UI may
continue using **http://127.0.0.1:5173/**: WebAuthn always runs only in the
isolated owner page at localhost:8766, with RP ID `localhost` and that exact
origin. No passkey credential or owner token is passed back to the AURA UI.

`core/src/aura_core/evolution/owner_control_plane.py` is a standalone
FastAPI **factory**, NOT a route mounted in the Core server. It exposes a
pinned-host, pinned-origin, no-CORS, CSP-isolated HTML/JS review page. Each
pending GovernedSkillActivation record displays its operation, capability,
scope, fingerprint SHA-256, version and expiry. Buttons invoke
`navigator.credentials.get({publicKey:{userVerification:"required"}})`.
The client submits the real WebAuthn assertion to a separate service: server
cryptographically verifies registered ES256 credential, RP ID, origin, UP+UV,
unexpired one-shot challenge and signature counter. Successful proof produces
an approval/denial with `human:local-owner` only through the protected
`TrustedOwnerPasskeyDecider`.

The service has **NO endpoint to register a new credential, create an
approval, or activate a tool**. Those functions remain in an independent
owner-provisioning/control-plane environment; ordinary AURA UI credentials
and the Core's HTTP bearer token cannot grant owner authority. An agent
cannot unlock a new credential by visiting this page.

Operator-only entrypoint:
`core/scripts/start_owner_control_plane.py`, e.g.:

```powershell
Set-Location D:\AURA\JAS-evolution-test\core
uv run --frozen python scripts/start_owner_control_plane.py `
  --owner-config "C:\OwnerVault\aura-public-credential.json" `
  --approval-db "C:\OwnerVault\governed-approvals.sqlite3" `
  --challenge-db "C:\OwnerVault\owner-challenges.sqlite3"
```

This command intentionally **fails closed unless all three files are
pre-provisioned**, outside the AURA checkout, and accessible only to an
independently protected owner control-plane identity. Do not create dummy
credentials or point these paths into the Core `.env.local` or source tree.

The config JSON must contain exactly:
```json
{
  "rp_id": "localhost",
  "origin": "http://localhost:8766",
  "credential_id": "<base64url registered credential ID>",
  "public_key_pem": "<PEM ES256 P-256 public key>",
  "policy_digest": "<64 lowercase SHA-256 characters>"
}
```

This file contains only PUBLIC credential data but is still trusted policy
configuration. Credential enrollment / attestation parsing is not yet
implemented; independently enroll the user's platform authenticator before
launching the service. **Do not deploy this as production** until supported
Windows Hello registration, NTFS ACL verification, a dedicated owner service
OS identity, trusted artifact/approval queue population, independently
observed sandbox attestor and cross-process owner receipt delivery exist.
Core and owner approval service run under separate security principals; merely
running two Python processes as the same Windows account provides no strong
isolation.

The separate owner screen records a one-time approval only; it DOES NOT
perform `GovernedSkillRegistry.activate`, bypass PermissionEngine, or import
candidate Python. Existing registry `activate/rollback` remains gated
through `LocalOwnerReceiptAuthority` and MCP Gateway with fresh policy
checks. Operator must review exactly the manifest digest displayed by the
independent trusted control plane. This milestone is **end-to-end WebAuthn
decision plumbing**, not production end-to-end skill deployment.

Tests:
```powershell
Set-Location D:\AURA\JAS-evolution-test\core
uv sync --frozen --group dev
uv run --frozen pytest -q tests/test_owner_control_plane_http.py `
  tests/test_evolution_owner_challenge.py `
  tests/test_evolution_owner_passkey_and_replay.py
uv run --frozen python scripts/verify_final_lock.py
```


## Primal Anchor v2.3 — signed owner decision handoff (incremental)

\`evolution/owner_receipt.py\` defines a domain-separated, canonical Ed25519
approval receipt. ONLY the owner-protected \`OwnerReceiptIssuer\` instance may
sign; Core receives its pinned **public** key and uses
\`DurableOwnerReceiptConsumer\` to validate scope, operation, policy digest,
binding digest, signed approval ID/version, and expiry. An atomic SQLite unique
constraint on the approval ID and nonce denies duplicate consumption across
process restarts. PermissionEngine authorization is required in addition to
cryptographic validity. Receipt lifetime is at most 90 seconds and never
exceeds the originating approval's own expiry.

The independent \`owner_control_plane.py\` may be configured with a receipt
issuer; **only an actually approved WebAuthn decision** can return a signed
receipt, and the page requires an explicit user gesture before copying it.
No receipt is sent to AURA HUD automatically. There is still NO HTTP route
that executes the receipt or directly calls \`GovernedSkillRegistry.activate\`.
Injection into the existing registry is through its preexisting
\`owner_receipt_consumer\` callback. The registry's \`validate\` and \`activate\`
methods continue to check separately signed independent sandbox evidence;
MCPGateway and PermissionEngine still gate all actual tool invocations.

Optional trusted owner launcher flags:
\`--owner-receipt-key <protected-Ed25519-private-key-PEM>\`
\`--owner-receipt-key-id <pinned-key-id>\`.
Both are required together; omission produces review-only decisions. The
private key must be provisioned outside AURA sources, under a separate
OS owner identity, and never made available to the Core agent/sandbox.
Public key distribution to Core requires an independently pinned trusted
configuration and must not accept data from model output, HUD content or
unverified requests. Existing legacy database receipt authority remains for
backward compatibility and MUST NOT be used as production cross-process
proof without the signed owner callback.

The operator still must enroll a genuine WebAuthn credential securely
(Windows Hello enrollment is NOT complete), protect and provision the
approval/receipt SQLite databases with appropriate Windows NTFS ACLs, and
provide an independent attested runner. In particular, this release does
**not** automatically activate a generated MCP provider and does not merge
Spatial HUD, Nirvana Voice and Evolution branches.

Local focused tests:
\`\`\`powershell
Set-Location D:\AURA\JAS-evolution-test\core
uv sync --frozen --group dev
uv run --frozen pytest -q tests/test_governed_owner_receipt.py tests/test_owner_control_plane_http.py tests/test_evolution_owner_challenge.py tests/test_sandbox_attestor.py
uv run --frozen python scripts/verify_final_lock.py
\`\`\`
