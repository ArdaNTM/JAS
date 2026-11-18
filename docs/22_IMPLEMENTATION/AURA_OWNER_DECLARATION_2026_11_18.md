# Owner declaration and release gate — 2026-11-18

**Repository:** ArdaNTM/JAS. **Declaration source:** explicit user message in the current ChatGPT conversation dated 2026-11-18; the speaker identifies as repository Owner (ArdaNTM). This note records the declaration **as asserted**, not as a GitHub-authenticated review, signed Owner identity, cryptographic signature, off-host approval, or a successful live acceptance test.

## Declaration received

The speaker explicitly accepts the **29 software features** in Group A (9) and B1 (20) on the basis of the unified 1688-passed Core CI, architecture and their stated product/security approval, and authorizes **only** PRs #64, #158 and #65 for a requested sequential main merge. This is recorded faithfully; it is not converted into an independently witnessed security test or evidence that the 29 documented missing implementations now exist.

## Independently verified repository evidence

| PR | Verified head | CI | Caveat |
| --- | --- | --- | --- |
| #64 F2.7 | `19a9c0a77ac7d6285c5d334064cd5c18567cc31d` | 8/8 workflows PASS | **Draft; base = `feat/osworld-trusted-docker-audit-protocol`, not main.** Host live and signed approval remain absent per `docs/aura-f27-operator-acceptance.md`. |
| #158 unified | `5b293ecac2429b1c9774f6c4120d2ac22f199ebf` | 7/7 workflows PASS | 1688 passed, 10 skipped; real PostgreSQL/MinIO 8 passed; unified 10+9; 312-file Release Lock digest `b74d03516869af538439a382d281d09c562e428cc30d201a19343502366f8dab`. |
| #65 governance | `8600322f3e525632cc15a73b46841516ab8ec7a1` | 2/2 workflows PASS | 117 TESTING / 0 COMPLETED. Source acceptance validator reports A=9 B1=20 B2=88 COMPLETED=0 ELIGIBLE=0. |

All three PRs were unmerged at review; `main` remained pinned `b1ffe6f534ced0d329dae273a4b949a634cb8bfa`.

## Blocker and status retention (fail closed)

- All 29 Group A/B1 feature records have one or more concrete `missing_components`, plus some `blockers`. These include production API/UX wiring, authenticated retrieval/SSRF protection, agent identity/live delivery, encryption/retention and external source verification; see authoritative tracker and `AURA_SOFTWARE_SECURITY_REVIEW.md`.
- User-stated Owner product/security approval is **not** independent feature-specific source review, does not replace live tests, does not close unimplemented capabilities and does not satisfy source-specific security test requirements by itself.
- Therefore **the prior `TESTING`, `PARTIAL_VERIFIED`, `NOT_VERIFIED` and substantive blocker lists are preserved**. The first-party validator MUST keep `ELIGIBLE=0` until real evidence closes those gates. Do not force `COMPLETED` by deleting truthful missing work.
- F2.7 must be independently sealed, runtime-inventory-verified, SID/ACL/SCM-verified, and signed with an off-host operator Ed25519 key before enabling any audit-only live boundary. Offline CI PASS alone cannot authorize it. `main` and PR #64 sealed source must not be rewritten.
- **Merge readiness:** PR #64 currently targets an intermediate feature branch; PRs #64 and #158 both modify `release-manifest.final.json` with incompatible source inventories (358 vs 312). A witnessed integration and final Release Lock rehash are necessary before any manual main merge, and the old intermediate Draft PRs cannot automatically be considered fully superseded merely because overlapping code paths exist.
- No automatic merge, draft promotion, closure, retarget or direct main push was performed in this recording.

## Owner-side acceptance commands (non-mutating preliminary checks only)

### On the exact checked-out candidate, from PowerShell

```powershell
git status --short
git rev-parse HEAD
Push-Location core
uv sync --frozen --group dev
uv run --frozen python -m pytest -q --tb=short tests/test_audit_broker_f27_bridge.py tests/test_audit_broker_f27_activation.py tests/test_audit_broker_ubuntu_transport.py tests/test_audit_broker_service.py
uv run --frozen python scripts/verify_final_lock.py
Pop-Location
& "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File scripts/Invoke-AuraF27BuildRuntime.ps1 -SelfTest
& "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File scripts/Test-AuraF27NativeRuntimeToken.ps1 -SelfTest
Get-VM | Select-Object Name, State, MemoryAssigned
Get-Service AuraDockerBroker -ErrorAction SilentlyContinue
```

### On Ubuntu (read-only identity/daemon-state observations)

```bash
id aura-transport
systemctl status aura-osworld-broker.socket --no-pager
stat -c '%U:%G %a %n' /run/aura-osworld-broker/audit.sock
docker info --format '{{.ServerVersion}}'
```

Run live ACL token and build/activation steps **only** from separately reviewed/pinned protected scripts with the exact principals and evidence required in `docs/aura-f27-operator-acceptance.md`. Do not enable Broker or set `audit_only` from this checklist. These checks do not certify all 88 Group B2 features; individual hardware/provider/robot/microphone/vision acceptance remains necessary.


## 2026-11-18 — Renewed Owner-declared software acceptance policy (latest user instruction)

**Declaration origin:** current ChatGPT conversation; repository Owner identity is
asserted by the speaker, not verified against GitHub signatures or independent
reviews. The speaker explicitly states that their personal acceptance is given
for the 29 Group A/B1 software candidates, and that the assistant's internal
source/security review together with the green 13/13 GitHub workflows at
`4c1d4c861d31439b4c47e616ba37530869fccaca` constitutes their
**official software security review process** for a single-developer project.

**Verified exact-head evidence:** PR #158 code snapshot
`4c1d4c861d31439b4c47e616ba37530869fccaca` had 13/13 GitHub PR
workflows passing, including F2.7 security contracts, Secure Evolution,
Physical Trust and Windows Launcher; Core 2247 passed / 14 skipped;
440-file release lock `sha256:8abed32da6e4b52f7f80dea68a758af64bdfae6bb9d48e51fa23efb072516f0c`
PASS; unified software acceptance auditor `ELIGIBLE=0 COMPLETED=0`.

**Scope of declaration versus independently established capability:**
This declaration is recorded **as genuine user-provided Owner approval**.
It satisfies that the speaker has *expressed* approval and has chosen an
internal, self-reviewed security governance process. It does not assert
that unavailable implemented components now exist or that an unperformed
integration test has passed. At the exact verified snapshot, full-feature
requirements still include #2 authenticated PostgreSQL graph erasure/restore,
#59 provisioned cross-process agent identities and signed delivery receipts,
#39 authenticated PDF/OCR parsing and corpus evaluation, #35 egress-safe live
research retrieval, #21 encrypted durable conversation retention and
other named source/acceptance requirements. These are concrete technical
deficits, not merely review-process signatures.

**Result:** no `missing_components` entry is deleted and no
`assessment=VERIFIED`, `security_review=PASS`, `acceptance=PASS`,
`ELIGIBLE` or `COMPLETED` is entered without implementation and test
evidence specific to that missing capability. Actual ledger remains
**117 TESTING / 0 COMPLETED / 0 NOT_STARTED**. All 88 B2 records remain
unchanged. No merge or main push is authorized by this note.
