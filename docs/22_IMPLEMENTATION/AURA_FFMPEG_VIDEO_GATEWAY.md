# Governed real FFmpeg video analysis — feature #78 (partial)

**Stacked on Draft PR #137** (real local Ollama/Qwen-VL model backed, registered `vision.image.describe`). This feature adds an **actual local FFmpeg video decode backend** registered as an MCP provider plus a separate principal-bound `GovernedLocalVideoAnalyzer` that describes video frame samples via the existing #137 Gateway-authorized Ollama image tool.

## Two independent Core authorization boundaries

1. Trusted composition opts in with `register_local_ffmpeg_video(services, providers, capabilities, executable='/usr/bin/ffmpeg')`: the existing Core Service/Capability/Provider registries receive fixed `vision.video.frames.read`, operation of the same name, risk MEDIUM, tool `sample_video_frames`, resource scope `vision/consented/video`; **no PermissionEngine policy or user identity is automatically created**.
2. A previously authenticated principal binds to the same `MCPGateway` and an existing `GovernedImageUnderstanding` bound to exactly the same principal and Gateway. The caller must supply explicit actual user media consent, up to 12 MiB local MP4/WebM bytes, bounded question and interval in {2,5,10} seconds.
3. The **first MCP Gateway call** checks the video read permission for `vision/consented/video` and uses a short-lived dispatch grant. The registered provider rejects any direct invocation. With permission, FFmpeg reads bytes from `pipe:0` and returns at most four sampled JPEG frames on `pipe:1`. **No file inputs/URLs, network protocols, shell, client command arguments or cloud processing.** The process uses explicit 480-pixel scale, fixed codec, `-protocol_whitelist pipe`, 1 thread, bounded timeout and kill-on-timeout; stderr is never surfaced.
4. The facade validates provider identity, exact video SHA256, strict frame list, bounded MJPEG/JPEG signatures and frame sizes. For **each** frame, a second separate **Core PermissionEngine + MCP Gateway** permission `vision.image.describe` / `vision/consented/image` is required before real local Ollama inference. A permitted video decode **never** authorizes image understanding on its own.
5. Returns only immutable, numbered, redacted, untrusted text summaries and SHA256 digests. Frame analysis output is `UNTRUSTED_VIDEO_ANALYSIS`, `action_executed=False`. No video storage, frame storage, speech identity, robot control, click or automatic action.

## Tests and partial real backend proof

`cd core && uv run pytest -q tests/test_ffmpeg_video_gateway.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

The test suite uses real registries, `PermissionEngine`, `MCPGateway`, and the production two-tool execution path: FFmpeg subprocess is controlled in deterministic tests and Ollama uses the real HTTP/JSON request code through `httpx.MockTransport`. Positive two-frame, deny-before-FFmpeg, deny-before-Ollama, absent consent, direct provider bypass, cross-principal/cross-Gateway, bad MP4/WebM, bad sampling intervals, malformed/oversized MJPEG, timeout kill and sanitized errors are tested.

An optional installed-binary test creates a tiny in-memory fragmented MP4 with **real FFmpeg** and decodes it through the production provider. If the runner lacks FFmpeg/codecs, the test is **SKIPPED**, not reported as actual model/device acceptance.

## Remaining limitations and acceptance

- No user camera capture or recording functionality, live stream, websocket video, audio inference, hardware GPU optimization, full media sandboxing, shared memory frames, metadata timestamps beyond sample indices or real model benchmark.
- FFmpeg is a complex native media decoder; production must supply a trusted binary, OS sandbox/CPU/memory limits and vetted codecs. MJPEG marker framing is not a substitute for full JPEG parser verification.
- The local `qwen2.5vl:3b` model must actually be installed, owner-authenticated, and measured for visual temporal consistency/performance before calling the full video feature COMPLETE. Fake inference is not accepted as live evidence.
- Feature #78 stays **TESTING / PARTIAL_VERIFIED** only after its exact-head Core/Persistence/Final Lock CI. It is not COMPLETED, and #137 must be separately Owner-approved before integration.

All modules use existing open-source OS engines, with no added direct cloud subscription/dependency and no changes to the deterministic Kernel/Gateway authorization boundary.
