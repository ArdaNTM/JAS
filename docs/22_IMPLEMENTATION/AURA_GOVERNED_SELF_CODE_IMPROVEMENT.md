# Governed AURA self-code improvement

## Implemented lifecycle

The opt-in idle introspection worker uses the existing local, provider-neutral
JSON completion interface to inspect exact release-identified JAS source files
and produce a small line replacement and regression test plan. This is an
actual source patch, not an external MCP package suggestion.

The initial scope is limited to explicitly enumerated offline research helpers
in self_patch_review.py (citation rendering and range comparison). The updater,
Kernel, registries, PermissionEngine, Gateway, authentication, Owner/attestor,
F2.7, dependencies and release policy remain outside scope. Expanding the
allowlist itself requires a separate human-reviewed release.

Each draft binds the release digest, exact original source SHA-256, candidate
SHA-256 and proposed change to a content-addressed draft ID. AST and line
budgets restrict the change to one allowed function body. These are scope
checks, not proof of safety or correctness. Drafts are non-importable private
JSON outside JAS. GET /api/evolution/self-patches is local Owner-only review
metadata, never approval authority. No model tool can execute a patch, invoke
Git, mint a receipt, update the release lock or promote a release. Existing
external MCP activation/attestation remains unchanged.

## Live Windows proposal verification

From the trusted released JAS checkout, use a Core-account-owned independently
provisioned review directory outside JAS and outside attestor key storage.
It must pass require_private_acl on Windows or mode 0700 on POSIX. Never
relax the Owner or attestor ACL.

~~~powershell
$Review = 'D:\AURA\SelfPatchReview'
New-Item -ItemType Directory -Path $Review -ErrorAction Stop
$Sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
icacls.exe $Review /inheritance:r
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect review directory' }
icacls.exe $Review /grant:r ('*' + $Sid + ':(OI)(CI)F') '*S-1-5-18:(OI)(CI)F'
if ($LASTEXITCODE -ne 0) { throw 'Cannot grant review ACL' }
$env:AURA_BACKGROUND_THINKING_ENABLED = '1'
$env:AURA_EVOLUTION_REVIEW_ENABLED = '1'
$env:AURA_EVOLUTION_INTROSPECTION_ENABLED = '1'
$env:AURA_EVOLUTION_SELF_PATCH_ENABLED = '1'
$env:AURA_EVOLUTION_SELF_PATCH_REVIEW_DIR = $Review
$env:AURA_JAS_ROOT = 'D:\AURA\JAS'
$env:AURA_OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:AURA_EVOLUTION_MODEL = 'qwen3'
~~~

Set these in the trusted Core launch environment with local storage and
restart with the existing launcher. Leave Core idle for its configured
evolution cycle. Do not change the independent attestor scheduled task.
Inspect authenticated local GET /api/evolution/status and
GET /api/evolution/self-patches as local_owner, or inspect the private review
directory:

~~~powershell
Get-ChildItem -LiteralPath $Review -Filter '*.patch-review.json'
~~~

The model may decline, return invalid output, or time out; no draft in a
particular cycle is not proof of failure. A staged draft is NEEDS_OWNER_REVIEW,
authorization_granted=false, execution_performed=false, tests_passed=false.
Verify the live checkout is unchanged and existing MCP providers remain active.

## Independent release handoff (human operator only)

1. Read the exact draft JSON, full draft digest and proposed assertions.
   Reject side effects, weakened checks and unrelated changes. A model summary
   is never approval.
2. Provision an isolated disposable clone from the official JAS repository at
   the independently selected full base commit corresponding to the draft
   release digest. Use a low-privilege release/test environment without
   production credentials, Owner secrets, attestor keys or production data.
3. Verify the unchanged base release lock. Use a dedicated self-patch/* branch,
   never main. Stage the selected draft with the trusted operator script.
   It checks the exact base SHA, draft digest, source identity, JAS origin,
   clean separate clone and patch applicability. It does not execute code.

~~~powershell
$Live = 'D:\AURA\JAS'
$Lab = 'D:\AURA\JAS-selfpatch-lab'
$Base = '<full reviewed 40-character Git SHA>'
$Id = '<full reviewed 64-character draft digest>'
$Draft = Join-Path $Review "$Id.patch-review.json"
git clone --no-checkout https://github.com/ArdaNTM/JAS.git $Lab
git -C $Lab switch --detach $Base
git -C $Lab switch -c "self-patch/$($Id.Substring(0,12))"
Push-Location "$Lab\core"
try {
    uv sync --frozen --group dev
    if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed' }
    uv run --frozen python scripts/verify_final_lock.py
    if ($LASTEXITCODE -ne 0) { throw 'Base lock failed' }
} finally { Pop-Location }
Push-Location "$Live\core"
try {
    uv run --frozen python scripts/stage_self_patch.py --checkout $Lab --draft $Draft --expected-base $Base --approve-draft-id $Id
    if ($LASTEXITCODE -ne 0) { throw 'Patch staging failed' }
} finally { Pop-Location }
git -C $Lab diff --cached
~~~

The digest selection is not a WebAuthn receipt and does not grant deployment
authority. A separate operator must receive a private copy of the review
artifact under their account without granting Core any attestor key access.

4. A human reviewer adds actual positive/negative regression tests, reviews
   the diff, and runs the full test suite in an isolated disposable runner
   without production secrets. Do not execute model-generated code on the
   production host. After staging the reviewed tests and approved changes,
   regenerate and verify the release lock using existing scripts:

~~~powershell
# In the independent test clone, after source review:
cd <isolated-clone>\core
uv run --frozen pytest -q --tb=short
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
uv run --frozen python scripts/generate_final_lock.py
if ($LASTEXITCODE -ne 0) { throw 'Lock generation failed' }
uv run --frozen python scripts/verify_final_lock.py
if ($LASTEXITCODE -ne 0) { throw 'Release lock failed' }
~~~

5. The independent release operator commits/pushes the reviewed branch and
   opens a PR. Require Core Assurance, F2.7 and all applicable CI gates.
   Only explicit human Owner approval may merge/promote. Deployment/rollback
   follows existing JAS release governance; retain the prior trusted release.
   There is no unattended merge, deployment or GitHub credential in Core.

## Acceptance and limitations

Regressions exercise actual patch creation, protected targets, stale/tampered
reviews, malformed model response, idle/opt-in behavior and real Git staging in
a temporary standalone repository. Model transport is inert in tests, not a
live Ollama benchmark. The model's proposed improvement is not certified.
Human testing, PR review, merge and deployment are deliberately independent.
