# Real before/after visual task evidence under AURA Core — feature #84 (partial)

**Stacked on Draft PR #137** for the existing registered local Ollama/Qwen-VL image-understanding MCP tool. This module uses a **real Pillow image decoder/normalized RGB pixel-difference engine** plus two independently authorized Core/MCP Gateway local-model descriptions. Its purpose is **observed visual evidence**, explicitly **not** proving task success, physical reality, ownership or permission to click, move, unlock or control any device.

## Security / deterministic Core registration

1. Trusted composition explicitly registers `LocalPixelChangeComparator` as Core `ServiceRegistry`/`CapabilityRegistry` capability `vision.task.verify`, risk MEDIUM. No `PermissionEngine` policy is added automatically. The verifier binds an independently authenticated principal to the **same PermissionEngine as the existing governed local Ollama Gateway reader**.
2. `verify(before=..., after=..., baseline_confirmed=True, after_confirmed=True, expected_observation=...)` requires explicit consent for **both** captures, a bounded expected observation and an independent `PermissionEngine` ALLOW for `vision.task.verify` / `vision/task/compare-only` **before any Pillow decode or model inference**.
3. Real Pillow opens only bounded PNG/JPEG/WebP bytes from `BytesIO` (no paths, external URLs or network). Input is bounded by the existing 8MiB signature gate; image headers are validated for max 4096 dimension and max 3 million pixels **before decoding** to RGB. Images are reduced to at most 320x320 and compared with `ImageChops.difference` and `ImageStat` to calculate normalized [0..1] mean absolute RGB difference.
4. Classification is restricted to `VISUALLY_SIMILAR` (very low delta), `OBSERVED_DIFFERENCE` (strong delta), or `UNCERTAIN_CHANGE` (intermediate). These classes show pixel change only; even strong difference is **not** evidence that the intended action succeeded.
5. The verifier independently invokes **two** `GovernedImageUnderstanding.describe` requests (baseline and after) using the preexisting local Ollama MCP Gateway, each requiring its own explicit Core permission. Model output is `UNTRUSTED` text. After asynchronous inference it **rechecks the compare permission** before emitting immutable `VisualTaskEvidence`.
6. The output always has `task_success_verified=False`, `human_review_required=True`, `authorized_actuation=False`, and `trust='UNTRUSTED_VISUAL_TASK_EVIDENCE'`. No raw images, coordinates or text go to EventBus; only metadata classification and mandatory human review are published.

## Evidence commands

`cd core && uv run pytest -q tests/test_visual_task_verification.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests run actual on-memory PNG creation and Pillow RGB delta calculations, real Core Service/Capability registries and PermissionEngine, the registered MCP Gateway and full local Ollama HTTP/JSON path using `httpx.MockTransport`. They cover positive changed/similar/uncertain images; independent model policy, default-deny before decode, both consent flags, malformed/oversized/mismatched captures, malformed expected observation, hallucinated command text remaining untrusted, metadata-only EventBus, wrong principal/policy engine and no implicit capability allow. If Pillow is not available, tests skip and production usage fails closed rather than claiming live functionality.

## Required real acceptance

- This is **not** semantic task completion verification, a calibrated visual recognition benchmark or proof of causation. Lighting/camera placement/compression can produce false changes and visual similarity can hide real actions. Owner must review before accepting success or allowing any follow-up action.
- No screen/camera capture, automation, physical robot, screenshot provenance attestation, user session owner proof or independent semantic object detector calibration in this slice. Integrating #79 detector, #80 OCR, #83 camera, #136 cross-PR runtime, trusted Owner capture UI and machine/user evaluation remains outstanding.
- Pillow/OpenCV native library provenance and image parser fuzzing/resource confinement, real Qwen-VL model weights and Windows desktop performance require hardware acceptance.
- Feature #84 remains **TESTING / PARTIAL_VERIFIED** only after exact-head Core Assurance/Persistence/Final Release Lock CI; no `COMPLETED` claim or automatic PR merge. Core retains existing deterministic Kernel, registries, PermissionEngine, EventBus and MCP Gateway authority.
