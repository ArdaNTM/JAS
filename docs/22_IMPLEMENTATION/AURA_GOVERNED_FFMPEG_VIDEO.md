# Governed offline video analysis — feature #78 (partial)

This PR is stacked on Draft PR #137, which registers a **real** loopback Ollama/Qwen-VL image-description model behind the existing AURA MCP Gateway. Feature #78 adds a separate **real offline FFmpeg executable** for extracting up to four sampled video frames into one bounded 2×2 PNG contact sheet, then independently authorizes the image model to describe the sheet. It is not a raw video stream, cloud API, camera device, autonomous tracking or a tool permission.

## Production execution contract

1. Trusted AURA Core composition explicitly registers `LocalFFmpegVideoMCP` through **existing** ServiceRegistry, ProviderRegistry and CapabilityRegistry, under capability/operation `vision.video.frames`, tool `video_contact_sheet`, risk MEDIUM, scope `vision/consented/video`. No default permission or identity is created.
2. `GovernedVideoUnderstanding` binds an authenticated Core principal to the same MCP Gateway for both required operations. Public calls require explicit `capture_confirmed=True`, 64 bytes..12 MiB MP4 (`ftyp` signature) or WebM (EBML signature) data, and no arbitrary path, URL, container protocol or command options.
3. Gateway invokes the FFmpeg provider only after separate PermissionEngine ALLOW and a current short-lived dispatch grant. FFmpeg uses `asyncio.create_subprocess_exec` with fixed argv, **pipe-only protocol whitelist**, fixed demuxer, `-t 4`, fps 1, 320×180 letterbox, tile 2×2 and a single PNG output. Inputs travel only through stdin, output via stdout; stderr redirected, minimal environment, bounded time and image size; timeout kills and waits for the subprocess. No shell=True, user-controlled filepath or network access.
4. The PNG contact sheet is SHA-256 bound to the original video and receives `UNTRUSTED_DECODED_VIDEO_FRAMES`; output integrity is checked before calling `GovernedImageUnderstanding` with the **same principal and Gateway**. A *second* PermissionEngine ALLOW under `vision.image.describe` and `vision/consented/image` is mandatory before the actual local Qwen-VL model HTTP operation.
5. The final evidence contains only a bounded text summary and image/video SHA-256 digests, `UNTRUSTED_VIDEO_MODEL_OUTPUT`, `interactive_action_authorized=False`. No raw video or frames are persisted in the feature and no Owner action, computer control, identity inference or file write follows automatically.

## Verification and limits

`cd core && uv run pytest -q tests/test_governed_ffmpeg_video.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use real Core registries/PermissionEngine/MCPGateway, actual production subprocess argument and HTTP model serialization with controlled local transports, positive/negative separate permissions, consent, wrong principal, false container signatures, empty/malformed output, direct-provider bypass and process timeout kill. A conditional smoke test launches an **actual installed FFmpeg binary** to encode/decode locally generated white MP4 frames without cloud/media downloads, otherwise explicitly skips for missing binary/codecs.

Outstanding for COMPLETED: real installed FFmpeg/codec and Qwen-VL weights on target hardware, secure executable provenance, OS process sandbox/resource limits and media decoder hardening, real camera/video timestamps and frame ordering, calibrated temporal analysis, streaming/WebSocket transport, user privacy/Owner consent, and real CPU/GPU latency measurement. Four sampled frames of a short clip do **not** constitute reliable full-video understanding. Real model/CLI acceptance has not been demonstrated merely by mocked external transports.

No new Python dependency. Both #137 and this PR remain Draft/unmerged. Feature #78 may become only `TESTING/PARTIAL_VERIFIED` on exact-head CI PASS; never COMPLETED without full acceptance.
