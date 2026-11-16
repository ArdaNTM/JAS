# Real before/after visual task evidence under AURA Core — feature #84 (partial)

**Stacked on Draft PR #137** for the existing registered local Ollama/Qwen-VL image-understanding MCP tool. This module uses a **real bounded standard-library PNG decoder** (CRC-checked zlib scanlines and all PNG filters), with optional Pillow JPEG/WebP support, plus normalized RGB pixel difference and two independently authorized Core/MCP Gateway local-model descriptions. Its purpose is **observed visual evidence**, explicitly **not** proving task success, physical reality, ownership or permission to click, move, unlock or control any device.

## Security / deterministic Core registration

1. Trusted composition explicitly registers `LocalPixelChangeComparator` as Core `ServiceRegistry`/`CapabilityRegistry` capability `vision.task.verify`, risk MEDIUM. No `PermissionEngine` policy is added automatically. The verifier binds an independently authenticated principal to the **same PermissionEngine as the existing governed local Ollama Gateway reader**.
2. `verify(before=..., after=..., baseline_confirmed=True, after_confirmed=True, expected_observation=...)` requires explicit consent for **both** captures, a bounded expected observation and an independent `PermissionEngine` ALLOW for `vision.task.verify` / `vision/task/compare-only` **before any Pillow decode or model inference**.
3. The common 8-bit non-interlaced RGB/gray/RGBA **PNG path uses a real Python-standard-library pixel decoder**: validates PNG chunk CRCs, bounds decompression before allocating, applies PNG scanline filters, and downscales pixel samples to at most 320x320. JPEG/WebP fall back to optional Pillow `BytesIO` decoding. No filesystem/media URL is accepted. The 8MiB signature gate, 4096-side and 3-million-pixel bounds precede full decode; normalized [0..1] RGB mean absolute difference is computed over actual decoded pixels.
4. Classification is restricted to `VISUALLY_SIMILAR` (very low delta), `OBSERVED_DIFFERENCE` (strong delta), or `UNCERTAIN_CHANGE` (intermediate). These classes show pixel change only; even strong difference is **not** evidence that the intended action succeeded.
5. The verifier independently invokes **two** `GovernedImageUnderstanding.describe` requests (baseline and after) using the preexisting local Ollama MCP Gateway, each requiring its own explicit Core permission. Model output is `UNTRUSTED` text. After asynchronous inference it **rechecks the compare permission** before emitting immutable `VisualTaskEvidence`.
6. The output always has `task_success_verified=False`, `human_review_required=True`, `authorized_actuation=False`, and `trust='UNTRUSTED_VISUAL_TASK_EVIDENCE'`. No raw images, coordinates or text go to EventBus; only metadata classification and mandatory human review are published.

## Evidence commands

`cd core && uv run pytest -q tests/test_visual_task_verification.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests create **real CRC-correct PNG image bytes with Python's standard library** and execute the actual PNG filters/zlib decoder plus RGB pixel comparisons on CI **without Pillow installed**, as well as real Core Service/Capability registries and PermissionEngine, the registered MCP Gateway and full local Ollama HTTP/JSON path using `httpx.MockTransport`. They cover positive changed/similar/uncertain images; independent model policy, default-deny before decode, both consent flags, malformed/oversized/mismatched captures, malformed expected observation, hallucinated command text remaining untrusted, metadata-only EventBus, wrong principal/policy engine and no implicit capability allow. The PNG comparison tests do **not skip** for absent Pillow. JPEG/WebP use Pillow when present; missing optional Pillow fails closed only for those formats and remains a documented deployment limitation.

## Required real acceptance

- This is **not** semantic task completion verification, a calibrated visual recognition benchmark or proof of causation. Lighting/camera placement/compression can produce false changes and visual similarity can hide real actions. Owner must review before accepting success or allowing any follow-up action.
- No screen/camera capture, automation, physical robot, screenshot provenance attestation, user session owner proof or independent semantic object detector calibration in this slice. Integrating #79 detector, #80 OCR, #83 camera, #136 cross-PR runtime, trusted Owner capture UI and machine/user evaluation remains outstanding.
- PNG zlib decoder fuzzing/resource confinement, optional Pillow JPEG/WebP provenance, real Qwen-VL model weights and Windows desktop performance require hardware acceptance.
- Feature #84 remains **TESTING / PARTIAL_VERIFIED** only after exact-head Core Assurance/Persistence/Final Release Lock CI; no `COMPLETED` claim or automatic PR merge. Core retains existing deterministic Kernel, registries, PermissionEngine, EventBus and MCP Gateway authority.
