# PR #64 → #158 → #65 merge preflight (not a conflict-free merge receipt)

**Source pins:** #64 `19a9c0a77ac7d6285c5d334064cd5c18567cc31d`, #158 preflight baseline `47ec68db107bdc054856f03d3d4a993408e00ea7`, #65 baseline `42052d1398ee0ea9af4b17ae54d775f2e3ca5de6`. At review, `main` = `b1ffe6f534ced0d329dae273a4b949a634cb8bfa`.

## GitHub actions completed

- **PR #64 base retargeted to `main`** without editing its sealed F2.7 files or SHA. GitHub reports `mergeable=true`. Because its original base is an unmerged **69-commit** intermediate branch and PR #64 itself adds 51 further commits, retargeting exposes **120 cumulative commits / 192 changed files**. Owner must inspect this cumulative security scope before merging.
- **PR #64 and PR #158 marked `Ready for review`** after verifying their exact-head CI workflow conclusions (8/8 and 7/7 green respectively). This is *review readiness only*, not approval to enable F2.7 live Broker/audit_only.
- **PR #65 was already ready**; its Core Assurance workflow was aligned byte-for-byte with #158 (the only different file among 13 shared paths). All 13 originally shared tracker/source paths now have identical Git blobs, pending final metadata updates. This reduces #65-on-#158 conflicts; it does not imply that all 29 features pass acceptance.

## PR #64 vs PR #158 source overlap

**7 paths have independent modifications** from `main`. GitHub currently finds each PR independently mergeable against old `main`, but **that is not evidence that #158 merges cleanly after #64**:

| File | Manual integration requirement |
|---|---|
| `aura-ui/src/HudOverlay.tsx` | Preserve both protected spatial HUD/voice controls from F2.7 ancestors and #158 game-studio / hologram modes; rerun browser/UI tests |
| `aura-ui/src/hud.css` | Combine transparency/input-pointer boundaries with #158 3D overlay styles; check click-through and screen capture |
| `core/src/aura_core/application/context_synthesizer.py` | Preserve strict bounded untrusted memory validation and original F2.7-context rules; rerun hostile-object/infinite-stream tests |
| `core/src/aura_core/application/full_duplex_session.py` | Preserve F2.7 live voice cancellation/timeout behavior and #158 prosody hooks; rerun voice/security tests |
| `core/src/aura_core/application/hud_api.py` | Preserve authenticated local HUD session and #158 model/image routing; rerun ingress/approval checks |
| `core/src/aura_core/main.py` | Merge both opt-in endpoint registrations, lifecycle closures, permissions and release guards; no unconditional gateway bypass |
| `release-manifest.final.json` | **Never choose either manifest**; compute a new one from the resolved union after true Git merge and generator reconciliation |

## F2.7 vs unified manifest analysis

| Metric | PR #64 | PR #158 |
|---|---:|---:|
| Source lock entries | 361 | 312 |
| Shared entries | 233 | 233 |
| Same-path differing SHA-256 | 34 | 34 |
| Exclusive entries | 128 | 79 |
| **Set union** | **440** | **440** |

The **440** count is the expected *union of currently enumerated lock paths only*. It is **not** an already generated, validated merged manifest; the generator's updated root selection and the actual resolved merged tree determine the authoritative lock. The 34 divergent SHA-256 entries are not 34 Git conflict files. The seven paths above are the actual *independently changed* PR path overlap. The F2.7 branch's `core/scripts/generate_final_lock.py` adds protected scripts and live OSWorld/F2.7 files absent from #158's original generator; it must be preserved in the resolved tree.

## Operator merge rehearsal — non-elevated, disposable local checkout

The Owner should **first review PR #64’s cumulative scope and merge it manually using a normal Git merge commit (not squash or rebase)**. In a separate, unprivileged Git worktree / branch *after* the #64 merge:

```bash
git fetch origin main feat/aura-117-unified-integration
git switch -c review/f27-unified origin/feat/aura-117-unified-integration
git merge --no-commit --no-ff origin/main
git diff --name-only --diff-filter=U
```

If conflicts exist, **STOP** and resolve all seven categories with source owner inspection, not `git merge -X ours` or `-X theirs`. After resolution, ensure `core/scripts/generate_final_lock.py` is the reviewed F2.7-inclusive version and from the local repo root run:

```bash
cd core
uv sync --frozen --group dev
uv run python scripts/generate_final_lock.py
uv run python scripts/verify_final_lock.py
uv run pytest -q --tb=short
cd ..
git diff --check
```

Rebuild/review the final candidate from a true merged tree. The release-lock generator intentionally rewrites only the manifest; no `main` push is performed by these instructions. **Do not commit or merge any test/host result if any command fails.** Keep `deny_only` and no SCM activation pending signed Windows/Ubuntu acceptance.

After the integrated #158 branch is verified green and GitHub confirms `mergeable=true` against the then-current `main`, the Owner can merge #158 manually. Finally review #65 (now overlap-source matched with #158), revalidate tracker and merge #65 manually. No existing 29 feature record is `COMPLETED` without exact missing-component implementation evidence and an accepted validator receipt. Closing earlier Draft PRs requires a separate complete source/ancestry reconciliation, not a blanket archival assumption.

**No zero-conflict guarantee is claimed** until the *actual* post-#64 merge simulation, full CI and final lock succeed on the exact candidate tree.



## 2026-11-19 — Actual Owner merge sequence and PR #65 resolution

- Owner merged sealed PR #64 into `main` as `e9c68dd1269e42df1731eac4d4b8acbfa9675ca7`; owner merged unified PR #158 into `main` as `b09ad74c49ebe1d73e2bb79524c8c8006e2ca40f`. This GitHub merge evidence supersedes historical preflight *future-tense* text above.
- PR #65 synchronized by a real two-parent merge commit `b7dd5f72a41ec96501e29bf18eb6ca0b2e4b6833` using these **two conflicting documentation files from updated main**, not the stale PR #65 variants. All other 16 previously shared governance blobs were byte-identical.
- Nine previously missing original B2-Owner-focused regression tests restored from original pinned source commits. This exposed seven real fail-open Swarm #58 regressions; hardened all-or-nothing pre-dispatch validation at `2ca63ca3c7892fa481e844ffd87e45f580bfd56f`, updated only the affected source and canonical 440-file lock.
- Exact-head Core Assurance [44450746726](https://github.com/ArdaNTM/JAS/actions/runs/44450746726): **2390 PASS / 14 SKIP**, 440-file Release Lock PASS. Owner-frozen bounded v1 B2-Owner=17 now accepted; **all B2-Env=71 still TESTING**, without physical/production attestation. Follow only explicit Owner PR #65 merge, not auto-merge.
