# B2-Env 71-feature post-merge validation plan

Baseline: Owner-merged `main` `b83689381cec291a5d72299c8d8f985c6e7c5753`; B2-Owner=17 bounded v1 COMPLETED; **all 71 B2-Env remain TESTING**. This file is a scheduling inventory, not a waiver, permission grant, hardware test result, or release signoff.

## Three-way disjoint validation cohort

| Test location | IDs | Count | Evidence boundary |
|---|---|---:|---|
| Windows + local Ollama, audio, UI and offline Core | `1, 3, 4, 6, 7, 9, 11, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 24, 26, 28, 29, 30, 31, 32, 48, 49, 54, 55, 56, 57, 63, 69, 77, 78, 79, 80, 82, 83, 84, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 103, 104, 105, 106, 107, 113, 115, 116` | 57 | Actual Windows session, speech/models, Owner device/ACL when relevant, plus scoped regression |
| Hyper-V Ubuntu / Docker in isolated AURA-Broker-Lab | `25, 27, 33, 45, 51, 60, 101` | 7 | Actual sandbox / POSIX descriptor, broker isolation, no privileged socket or Gateway bypass |
| Missing dedicated physical hardware; simulation **only** | `81, 85, 86, 87, 88, 89, 90` | 7 | Stereo rig, Home Assistant bridge, robotic actuators and trusted sensors; no real-device acceptance possible by simulation |

**Hardware exception policy:** The Owner can explicitly approve a *separate, scoped software-only simulation* acceptance track after signed review of actual negative cases, and after updating the technical_goal to a simulation-only promise. It cannot attest a physical robot, stereo rig, Home Assistant device, sensor or safety interlock, and **cannot silently mark these seven physical features COMPLETED**. Original `missing_components` and outstanding hardware acceptance continue to block full scope.

## Restored source-pinned tests

Exact original Git blobs restored without fabricated positive hardware evidence:

| Test | Feature IDs | Original source commit |
|---|---|---|
| `test_persona_initiative_validation.py` | 3, 4 | `fb76d221381ec6304758d063e387f20ec8f98650` |
| `test_tts_text_safety.py` | 15 | `a1568cdcf248e6f6992fa5e0355e032a84394f86` |
| `test_kokoro_voice_controls.py` | 18 | `595215246cf60c2a0a27cc5acf6131c1491be952` |
| `test_disk_health_telemetry.py` | 29 | `517aacecf257435b4085261642ac1cc5b5f0bf02` |
| `test_system_diagnosis.py` | 30 | `0a9ebb18f480690e1eaed2a91b45ef5335d7c9d7` |
| `test_runtime_evaluation_summary.py` | 48, 56 | `4717161b9bf077dd32de69d8e20d5163eb7c9cf6` |
| `test_specialist_performance.py` | 63 | `e5f4432142d0da302c4398e6e95a4a514af87205` |
| `test_approval_review_authorization.py` | 100 | `46b1660bc95ff909cb5409f3b651c4030067d5ed` |
| `test_sandbox_output_guard.py` | 101 | `019b62e327b21bb3c1538cac7dafa3a2eab6ad78` |
| `test_legacy_ws_auth.py` | 103 | `da5e2948079c36dcbf2e59ad47c5b6b11d7c3e90` |
| `test_offline_backup_integrity.py` | 105 | `3279fe5238f532ad21ee0bd919da970c401408ce` |
| `test_audit_checkpoint.py` | 107 | `a145504a3ce80b496333169bb393b3ed42b1848b` |
| `test_offline_language_learning.py` | 115 | `6533e49a915bdf1d43b3e3cf6eb192d676b9bcc2` |

The original #30 `DiagnosticsService.diagnose` read-only aggregate function was missing from the integrated main and must be restored exactly from its pinned PR. This does not authorize remediation.

## Windows PowerShell after Owner manually merges this PR

From `D:\AURA\JAS`:

```powershell
git switch main
git pull --ff-only origin main
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --list-only
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --group windows_local --tests-only
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --group hyperv_docker --tests-only
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --group external_hardware_simulation --tests-only
```

All three `--tests-only` steps are **offline regression evidence, not a physical acceptance claim**. Follow Windows real Ollama/audio/UI tests and Ubuntu/Docker supervised broker tests separately under existing PermissionEngine/MCP Gateway policy. The sole final full live preflight remains `core/scripts/b2_postmerge_check.py` without `--tests-only`, and it refuses to claim physical success without independently signed receipts.

## Physical evidence: single **assembly** command, not self-signing

The JAS repository deliberately has **no private key generator or physical attestation signer**. A physically separate trusted Windows-lab principal must collect all six real observations and sign each receipt according to `SignedHardwareEvidence.signing_payload()` (Ed25519, domain-separated) within one hour. Its provisioned signer key must be custody-audited and its **public** key pinned *out of band* before collecting evidence. Expected receipt filenames in `D:\AURA\Trust\PhysicalLab\receipts`: `webauthn_uv.json`, `microphone_latency.json`, `voice_barge_in.json`, `hud_multimonitor.json`, `hud_negative_coords.json`, `emergency_stop.json`. Each contains all exact `SignedHardwareEvidence` fields with real measured metrics, independent signature, unique nonce and common run UUID. No fixed signatures, generated placeholders, mock devices or invented measurements are accepted.

The **one-command assembler** verifies those independently obtained inputs before creating both files in the trust directory:

```powershell
& ".\core\.venv\Scripts\python.exe" -m aura_core.acceptance.b2_evidence_bundle --receipt-dir "D:\AURA\Trust\PhysicalLab\receipts" --pin-source "D:\AURA\Trust\PhysicalLab\preapproved-public-keys.json" --evidence-output "D:\AURA\Trust\PhysicalLab\SIGNED_EVIDENCE.json" --public-keys-output "D:\AURA\Trust\PhysicalLab\PINNED_PUBLIC_KEYS.json"
```

Then run the unchanged full runner with both resulting files and the actual Ubuntu VM SSH address. Failure/missing physical signer yields **BLOCKED** and no new trust file. Receipt validation only confirms signatures, freshness and metric thresholds **conditional on an independently audited physical collector**; it never creates an Owner MCP approval, VM security attestation or a simulation exemption.


## Software-only bounded v1 completion review candidates (not yet COMPLETED)

Exact combined-source CI on `06cdec4f4d9caa696c9277ffd74014a1624e7288`: Core Assurance **2572 passed / 14 skipped**, Unified Acceptance PASS, 441-source release lock PASS. Among the 15 features covered by the 13 restored tests, the following **12 are candidates for an explicit future narrow-v1 Owner/security review**:

| Candidate IDs | Proven narrow tested behavior | Further acceptance not proven by CI |
|---|---|---|
| 3, 4 | Strict persona/initiative input validation | Persistent preference UI, notifications and actual speech UX |
| 15 | Safe spoken-text normalization | Real acoustic latency/interrupt measurements |
| 29 | Best-effort disk advisory metrics | Real host disk observation, frontend, thermal/GPU |
| 30 | Read-only aggregate diagnostic findings | Signed/real host diagnostics, approved remediation |
| 48, 56 | Bounded descriptive runtime summary | Real task quality and longitudinal baselines |
| 63 | Scoped Swarm event timing estimates | Independent event authenticity and real provider timing |
| 103 | Deny-by-default legacy WebSocket shared secret | Production identity, device-bound proof, route acceptance |
| 105 | Offline backup integrity envelope | Encrypted durable storage, governed restore and recovery drill |
| 107 | HMAC audit checkpoint metadata | Independent signer/key custody and durable verifier deployment |
| 115 | Scoped SQLite vocabulary review | UI, authenticated storage, erasure/backup lifecycle |

**This is a review queue, not `ready_for_completion=true`.** All remain `TESTING`, with their original `missing_components` and `known_limitations`. Before any bounded v1 `COMPLETED`, independently verify each exact `technical_goal`, real deny-path tests, signed Owner scope approval, security/license review, and harmonized acceptance validator. #18 (live Kokoro model/audio), #100 (real Owner approval lifecycle) and #101 (Docker isolation) are **not** software-only candidates.


## 2026-11-19 — Owner-approved bounded v1, exact new main 5e51d3f

**Signed-off in chat by repo Owner for software/simulation *scope*, not physical lab evidence.**

- B2-Env software-v1 accepted **12**: `3,4,15,29,30,48,56,63,103,105,107,115` — only frozen offline `technical_goal`; actual live UI, model, scheduler, cryptographic custody and production identity require separate v2 acceptance.
- B2-Env hardware-exception simulation-v1 accepted **7**: `81,85,86,87,88,89,90`. These test artificial frames, inventory/state samples or simulated MQTT transport/attestations in scoped Core paths. They **cannot** verify a physical depth camera, robot motion/estop, homeowner bridge, independently provisioned sensor, or certified safety interlock. Full-product blockers were preserved verbatim in `known_limitations`.
- B2-Env remaining **52 TESTING**: `windows_local` **45** and `hyperv_docker` **7**. Group indices remain the frozen 57/7/7 partition to preserve original geographic acceptance scope; `B2_env_acceptance` separately records 12/7 signed-off narrow v1 and 52 outstanding.
- Overall A=9, B1=20, B2-Owner=17, B2-Env accepted-v1=19 => **COMPLETED=65 ELIGIBLE=65 TESTING=52**. Under no circumstances is simulated MQTT or an unsigned pytest JSON file a real hardware certificate or a Gateway tool-authorization token.
- Owner-merged integration evidence: PR #159 to `main` as `5e51d3f50b53f482e14e3d1d73a375d08e6e9eb7`, 2572 Core PASS/14 SKIP, 13/13 GitHub workflows PASS on source head `7beeb4a7c95e6b571fddeae95ef5b802b624cd8f`; new PR must independently pass current CI before merge.

### One command: real pytest execution, **unsigned software-only** JSON report

After Owner manually merges this follow-up PR and updates `main`:

```powershell
cd D:\AURA\JAS
& ".\core\.venv\Scripts\python.exe" ".\core\scripts\b2_postmerge_check.py" --repo-root "." --tests-only --run-pytest --evidence-out "D:\AURA\Trust\b2-env-tests.json"
```

This runs the **remaining 52 features' deduplicated 50 focused tests** with `pytest -q --tb=short`, audits the 117-feature source pins and canonical release manifest, and atomically writes SHA-256 test-file digests, exact Git HEAD, pytest exit code/summary and explicit `hardware_verified=false` into an **unsigned** JSON record outside the repository. A failed test or failed source/ledger lock gives `BLOCKED`. To narrow tests: add `--group windows_local` (45 features) or `--group hyperv_docker` (7). These are **software regression tests only**; real Windows session, Ubuntu broker and physical hardware acceptance still require existing independently signed security receipts and separate Owner acceptance.

## 2026-11-19 — Final bounded-v1 Owner release bookkeeping (NOT hardware certification)

- GitHub base merged main `2efa8bb44a08a7930dae956bc337c10b3691c359`; existing source CI `8e6e9a90998f5dee7b3c18a4de849180a4bd5a52`: 2576 passed, 14 skipped, 12/12 workflows success.
- Owner reported local Windows SHA-256 release-lock PASS for 441 sources, Windows focus 41 runnable files / 643 PASS, and locally runnable Hyper-V/Docker focus 6 files / 55 PASS. These reports are **not available for independent inspection in this PR**, are unsigned and are explicitly NOT hardware/OS-broker attestations.
- Exceptions: `test_ffmpeg_video_gateway.py` (#78), `test_tesseract_ocr_gateway.py` (#80), `test_ambient_signal.py` (#20) lacked Windows binaries or microphone driver; `test_docker_terminal_mcp.py` (#27), `test_governed_command_sequences.py` (#33) intentionally failed closed without a separately attested Unix broker. All five were exercised in Linux CI; none is falsely recorded as a local PASS. Full limitations remain in each feature's `known_limitations`.
- Owner approved only **source-regression bounded-v1** completion for 45 remaining Windows-scoped and 7 remaining Hyper-V/Docker-scoped features, on top of 46 earlier and 19 previously bounded software/simulation approvals. **117 COMPLETED / 117 ELIGIBLE / 0 TESTING / 0 NOT_STARTED** means the frozen scoped acceptance contract only, **not** live deployment, real shell/sensor/robot control, independent hardware signoff, credential ownership or a new MCP Gateway permission.
- Full archived original focus inventory (71 B2-Env features, 64 focused test files) remains addressable for regression even when no features remain `TESTING`. All original full-product gaps and environment blockers were moved to `known_limitations`; Owner and permission activation remains disabled except under pre-existing explicit policies.
- Cross-platform lock: `.gitattributes` now applies `* text=auto eol=lf` with pre-existing explicit `*.bat` / `*.cmd` CRLF overrides retained. Release lock must be regenerated once and CI validated against this exact Git tree before PR merge.
