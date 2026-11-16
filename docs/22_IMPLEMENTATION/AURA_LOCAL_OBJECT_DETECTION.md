# Governed local vision object detection hypotheses — feature #79 (partial)

This feature depends on Draft PR #137's **real local Ollama/Qwen-VL HTTP inference** registered as `vision.image.describe` behind the existing MCP Gateway. `GovernedLocalObjectDetector` consumes **only** a `GovernedImageUnderstanding` instance bound by trusted composition to an authenticated principal. It requests a bounded JSON object list from the on-device vision model and validates the returned normalized rectangular boxes.

## Runtime

- Local model pipeline: confirmed image bytes -> `GovernedImageUnderstanding.describe(...)` -> **Kernel PermissionEngine ALLOW** -> **MCPGateway.invoke** -> registered `LocalOllamaVisionMCP.call_tool` with current dispatch grant -> Ollama loopback `/api/chat` -> bounded UNTRUSTED output.
- `local_object_detection.py` parses a strict 8,000-character JSON object with up to 16 entries. Every object must have only a concise printable generic name and four finite normalized coordinates (`x1 < x2`, `y1 < y2`), no inverted or duplicate boxes or extra executable fields. Results sorted deterministically, immutable and labeled `UNTRUSTED_MODEL_LOCATION`.
- `ObjectDetectionEvidence.safe_for_automated_input=False` is deliberate: model-generated coordinates, even geometrically valid, are **not** verified pixel-level detections and must never automatically move a pointer, click, unlock doors, identify persons, or invoke tools.
- No second vision provider, implicit policy, model download, screen capture API, user identity extraction, file writes or external network.

## Verification

`cd core && uv run pytest -q tests/test_local_object_detection.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests run real AURA Service/Capability/Provider registries, PermissionEngine, MCPGateway and production Ollama request/JSON serialization through `httpx.MockTransport` to simulate the loopback daemon in CI. Positive two-object boxes, genuinely empty detection, DENY before inference, no consent, malformed/inverted/oversized model JSON, prompt injection and non-actionable output are covered.

## Required acceptance

- The model's boxes are **unverified hypotheses**, not independently calibrated confidence, ground-truth geometric detections or stable UI coordinates. Real Qwen-VL model weights, real image decoding/benchmark datasets, precision/recall, multi-monitor transforms, Owner privacy, native camera/screen consent and latency on target hardware have not been measured.
- Additional independent visual verification and high-risk approval are mandatory for robotic/computer-control use. #79 is **TESTING/PARTIAL_VERIFIED** after exact-head CI, not COMPLETED.
- No new package/model license; uses existing locally configured #137 provider.
