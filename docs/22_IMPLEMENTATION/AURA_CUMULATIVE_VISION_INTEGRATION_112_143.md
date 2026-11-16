# AURA integrated visual runtime review — cumulative PR #112–#143

**Status:** independent Draft integration review. **No pull request merged.** `main` remains pinned at `b1ffe6f534ced0d329dae273a4b949a634cb8bfa`. No property here is full Owner/device production acceptance or proof that all 117 features are COMPLETED.

## Sourced source-tree hierarchy

- Starts from separately green cumulative Draft PR #136 (`feat/aura-integration-review-112-135`), which integrated **22 distinct feature PRs #112–#135** and later PRs #137–#139 (local Ollama, Tesseract and object locations). Prior #136 Core 969+ tests, Final Lock/Persistence/Windows PASS at exact then-current heads; this review must **re-verify its own exact HEAD**.
- Adds four distinct tested visual features without overwriting their standalone PRs: #140 actual FFmpeg video frame extraction + local Ollama model; #141 actual SQLite visual metadata with per-owner scoped Core policies; #142 actual HIGH-risk OpenCV camera one-frame provider with in-provider Owner consent lease; #143 actual lossless stdlib PNG pixel diff + optional Pillow JPEG/WebP, combined with two separately authorized local image model calls.
- All four new sources have distinct paths; each new PR's tests and documentation were copied from its **exact CI-verified HEAD**. Feature #143 was updated following a CI quality finding: prior full Pillow test module was skipped because Pillow was absent. Its latest HEAD includes **genuine PNG codec tests that execute in CI without Pillow**, preventing a fake integration PASS.

## Trust chain and measured scope

Every external camera/FFmpeg/Ollama provider tool executes only through the existing deterministic Kernel `ServiceRegistry`, `CapabilityRegistry`, `ProviderRegistry`, `PermissionEngine`, `MCPGateway` dispatch grant and appropriately scoped Owner policies. A temporary approved camera device lease is checked **inside the provider**, not only in its facade. Video frames and model descriptions require separate policy grants. SQLite memory writes/reads/deletes require distinct Core permissions, and stored descriptions remain untrusted/plaintext; human visual verification never claims automatic task success.

The `core/tests/test_visual_cumulative_gateway.py` cross-module test uses actual Core/Gateway/SQLite/PNG and model HTTP request formatting. It injects controlled devices, FFmpeg transport, and HTTP responses **only at the native hardware/process/model boundary**; there is no fake authorization engine. Positive flow covers a consented camera frame, FFmpeg frame, local Ollama model call, visual SQLite write/read/delete, real pixel changed-state evidence, mandatory human review and final revoked camera lease denial.

## Mandatory acceptance still missing

- Older unmerged #64–#111 (including sealed F2.7 #64 Owner boundaries) are **not yet imported** into this branch. A future cumulative review must preserve their exact security locks, audit changes and multi-provider ABI; do not assume their CI or release-lock proof applies here.
- No real local FFmpeg/OpenCV/Pillow optional codecs/Windows camera hardware, Qwen-VL weights, GPU performance, real authenticated Owner consent UI, secure Windows NTFS storage, out-of-process camera driver containment, video benchmarks, or accepted production deployments.
- Local image captions, camera frames, model boxes and visual diff are **UNTRUSTED evidence**, not any permission to execute desktop/robot actions.
- All feature PRs and this integration PR must remain Draft/unmerged until full Owner acceptance. `COMPLETED` requires real production/hardware evidence, not unit test count.

## Verification

`cd core && uv run pytest -q`
`cd core && uv run pytest -q tests/test_visual_cumulative_gateway.py`
`cd core && uv run python scripts/verify_final_lock.py`

Remote Persistence, Windows launcher when triggered, and all Core CI must be green for this exact integration head. `release-manifest.final.json` is recomputed from the canonical JAS included paths and all new source SHA256 digests. Test/docs files are not part of the production source lock by design.
