# Secure Evolution — Stark-Sunhoon Paradigm (AURA)

## Architecture

The JAS deterministic Kernel, PermissionEngine and EventBus are immutable.
The model is **not** a Local Owner identity and does not authorize actions.

1. Idle review `EvolutionPlanner` scans bounded read-only source evidence.
2. Optional `ProactiveEvolutionCoordinator` asks the configured provider
   (Ollama/Qwen3 is the local default, but implements a generic JSON model
   interface) for a bounded metadata-only gap proposal. It writes an
   `EvolutionTask` to `hierarchical_memory.SQLiteEpisodicMemory` using
   principal `evolution_worker`; recalled text remains untrusted.
3. `GovernedMutationDebugLoop` accepts independently chosen test inputs,
   proposes bounded source revisions, and uses the **existing**
   `GovernedSandboxReview` through the **MCP Gateway**. The Gateway
   checks PermissionEngine and consumes a separate, user-provided
   Owner approval for **each** sandbox attempt. No approval, no execution.
   A sandbox success is provisional smoke evidence, not a signed attestation.
4. `EvolutionReviewGateway` stores a source digest and an owner-guarded
   non-importable `*.review.py.txt` file in an absolute, preprovisioned
   private directory outside the locked JAS checkout. Its metadata-only
   `EvolutionReviewRequest` EventBus event is visible in the read-only
   Evolution HUD.
5. A trusted independent owner-review service, after server-verified
   Windows Hello/Passkey WebAuthn, issues a short-lived signed owner receipt.
   The independently signed sandbox attestation must bind the **exact
   guarded source digest** and complete `SkillBinding` digest. Only the
   existing `GovernedSkillRegistry` can activate a pre-installed,
   healthy MCP provider. Every invocation still crosses MCP Gateway.
6. Generating new code and loading it into the running Core, writing to
   Kernel/Security, promoting files to `dynamic_tools/`, changing
   `release-manifest.final.json`, or running `generate_final_lock.py`
   **cannot be initiated by the evolution worker**. A separately controlled,
   owner-authenticated human release process must package reviewed source,
   run all tests, commit it, and publish a new signed/CI-validated release.

The currently implemented ProviderRegistry has `register`, but **not**
`register_dynamic_tool`. Never fabricate this API or introduce an unsafe
hot-loader. A generated tool must be packaged and pre-registered by
a trusted deployer, then activated through GovernedSkillRegistry.

## Default-deny configuration

The existing proposal-only mode remains available when only
`AURA_EVOLUTION_REVIEW_ENABLED=1` is set.

To enable model introspection **without execution** in local storage mode:

```powershell
$env:AURA_BACKGROUND_THINKING_ENABLED = "1"
$env:AURA_EVOLUTION_REVIEW_ENABLED = "1"
$env:AURA_EVOLUTION_INTROSPECTION_ENABLED = "1"
$env:AURA_BACKGROUND_THINKING_IDLE_SECONDS = "300"
$env:AURA_EVOLUTION_INTERVAL_SECONDS = "900"
$env:AURA_EVOLUTION_MODEL = "qwen3"
```

Quarantine opt-in requires a private, pre-existing directory outside
`D:\AURA\JAS` / any JAS worktree, provisioned by an operator and
ACL-protected before Core starts. Do **not** use the trusted owner signing
directory or share its Windows OS principal with the AURA worker.

```powershell
$env:AURA_EVOLUTION_DRAFTS_ENABLED = "1"
$env:AURA_EVOLUTION_DRAFTS_PATH = "D:\AURA-Quarantine\review"
```

The read-only HUD can fetch `GET /api/evolution/drafts`.
The authenticated local owner may stage metadata and source *as data only*
with `POST /api/evolution/drafts`. No API exists for an agent to
approve, promote, import or rewrite a release.

## Validation

```powershell
cd D:\AURA\JAS-secure-evolution-test\core
uv sync --frozen --group dev
uv run --frozen python -m pytest -q tests/test_secure_evolution_pipeline.py
uv run --frozen python -m pytest -q
uv run --frozen python scripts/verify_final_lock.py
cd ..\aura-ui
npm ci --no-audit --no-fund
npm run build
npm audit --audit-level=high
```

Docker sandbox preflight is separate: an image pinned by SHA256 must be
present locally. The existing runner already denies network, host mounts,
Docker socket, packages and persistent workspace, with --pull=never,
--read-only, --cpus, --memory and --pids-limit. It runs Python -I -S
with deterministic assertions rather than installing pytest at runtime.
Host-side pytest verifies the review path. No attempt guarantees 100% success;
unsuccessful or unknown outcomes stop without activating any tool.

## Release acceptance

The operator must independently inspect code and trusted test cases,
obtain signed sandbox attestation and a one-time verified owner receipt,
confirm a preinstalled provider binding, re-run full JAS CI and regenerate
the manifest as a separate manually controlled release. All model output,
web content, memory records and sandbox logs are untrusted input.
