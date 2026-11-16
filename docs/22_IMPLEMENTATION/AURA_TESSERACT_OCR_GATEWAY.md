# Local Tesseract OCR under existing AURA MCP Gateway — feature #80 (partial)

**Dependency:** stacked on Draft PR #137 (#77) for validated PNG/JPEG/WebP data boundaries and the existing local-only vision utilities. This PR implements a **real offline OCR subprocess** using an installed open-source Tesseract engine (`/usr/bin/tesseract` on Linux or a trusted, explicitly configured absolute executable path on Windows). The engine reads only explicitly consented image bytes through standard input and returns UTF-8 text via standard output. No cloud API, new package, model weight download, shell string interpolation or OS device control.

## Authority boundaries

- Trusted application composition explicitly calls `register_local_tesseract_ocr` against existing `ServiceRegistry`, `ProviderRegistry`, `CapabilityRegistry`; registers capability/operation `vision.ocr.extract`, tool `extract_image_text`, risk MEDIUM and fixed scope `vision/consented/ocr`. **No implicit PermissionEngine grant**.
- `GovernedOCRReader` binds a separately authenticated principal, requires `capture_confirmed=True` and a validated bounded (max 8 MiB) image. It issues an ordinary `MCPGatewayRequest`; only exact ALLOW from the existing Kernel PermissionEngine is dispatchable. `REQUIRE_APPROVAL` without independent consumed approval is not ALLOW.
- The provider checks `current_dispatch` and exact capability/tool/risk before any subprocess launch, even if called directly. No user-controlled shell path, argument switches, arbitrary language, filename or URL is accepted; only `eng`, `tur`, or `eng+tur` language codes and a fixed `--psm 6` profile.
- Execution uses `asyncio.create_subprocess_exec` (no shell), Tesseract `stdin`/`stdout`, sanitized environment and redirected stderr. A bounded timeout terminates the process and waits for it to exit. Nonzero exit, missing binary, oversized output and malformed responses fail with generic public errors that do not reveal OCR text, environment variables or paths.
- Return `OCREvidence(trust='UNTRUSTED_OCR_TEXT', physical_action=False)` and SHA-256 of input image, without raw image persistence. OCR text—including malicious instructions embedded in screenshots—remains **data**, never an Owner instruction, tool permission or executable workflow.

## CI and real engine validation

`cd core && uv run pytest -q tests/test_tesseract_ocr_gateway.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use real Core Service/Capability/Provider registries, PermissionEngine and MCP Gateway; a controlled subprocess transport for deterministic positive/negative cases verifies exact command args, no-consent/default-deny/approval-required, direct-call denial, malicious language and image rejection, timeouts, process-kill, overflow, and no data promotion. An **optional live test** performs actual Tesseract OCR on an in-memory generated high-contrast PNG if the runner has `tesseract`, English tessdata and Pillow/font available; otherwise it is explicitly skipped rather than claimed as real hardware acceptance.

## Unverified full acceptance

- Tesseract executable and language data must be installed locally and licensed/deployed correctly on target OS; Turkish `tur` language pack is not guaranteed. Windows absolute executable, code-signature/ACL provenance, tampering, sandbox policy, native performance and all real image decoder edge cases need independent acceptance.
- Existing image signature routing checks are not full pixel/file/decompression-bomb validation. Do not OCR untrusted massive images without additional hardened image decoding and resource limits in production.
- No live screen/camera/Owner UI or model accuracy report. This PR **does not** implement video frame extraction, object recognition or physical actions.
- Feature #80 stays `TESTING / PARTIAL_VERIFIED` after exact-head CI, **not COMPLETED**. No auto-merge; PR #137 must be independently Owner-approved before stacking this branch into production.
