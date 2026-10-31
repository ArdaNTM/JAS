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
