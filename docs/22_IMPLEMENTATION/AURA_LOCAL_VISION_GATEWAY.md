# Real local Ollama image understanding behind MCP Gateway — feature #77 (partial)

This PR introduces **actual local model inference** for image description using the existing `aura_core.providers.local_vision.LocalOllamaVisionProvider` (Ollama `/api/chat` with image bytes and `qwen2.5vl:3b` by default), but only behind a registered Core Service/Capability/Provider and the existing `MCPGateway` authorization boundary. It is not a mock-only implementation: the production path sends a real HTTP POST to a loopback Ollama daemon, optionally replaced by `httpx.MockTransport` only in deterministic CI.

## Security, registration and runtime flow

1. Trusted application composition invokes `register_local_ollama_vision(services, providers, capabilities, model, base_url)` **opt-in** after constructing the authoritative registries. It registers one MCP-compatible provider ID `vision.ollama.local`, capability/operation `vision.image.describe`, tool `describe_image`, risk MEDIUM. No default PermissionEngine ALLOW policy or Owner identity is created. Duplicate registration fails closed.
2. An independently authenticated principal constructs `GovernedImageUnderstanding(gateway, authenticated_principal_id=...)` and calls `describe(image, prompt, capture_confirmed=True)` only after an explicit actual image/screen/camera consent. The facade validates 16 bytes..8 MiB of PNG/JPEG/WebP magic and a short bounded prompt, then issues a normal `MCPGatewayRequest` scoped to `vision/consented/image`.
3. Existing Kernel `CapabilityRegistry` and `PermissionEngine` must return explicit ALLOW. `DENY`, `REQUIRE_APPROVAL` without consumed approval, invalid capability/tool schema, or absent registration never enters the model. Provider implementation **also checks short-lived `current_dispatch()`**; direct `call_tool` outside `MCPGateway` is denied.
4. The provider only connects to an explicit **HTTP loopback** Ollama URL (default `127.0.0.1:11434`), with no proxy/env trust in the underlying `LocalOllamaVisionProvider`. No remote/cloud API, no credentials or automatic model download. Image text and model responses remain `UNTRUSTED_LOCAL_MODEL_OUTPUT`, never Core policy, Owner action or instructions. Only image hash and bounded description are returned; no image payload stored or sent through EventBus.
5. The caller rechecks exact provider identity, SHA-256 of input image, bounded description and untrusted marker before returning an immutable evidence object. Transport errors are sanitized without secrets or raw image bytes.

## Verification

`cd core && uv run pytest -q tests/test_ollama_vision_mcp.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests instantiate real ServiceRegistry, CapabilityRegistry, ProviderRegistry, PermissionEngine, MCPGateway and production HTTP transport/JSON serialization (`httpx.MockTransport` to simulate the local Ollama daemon only in CI). Cases cover authorized full call, default/explicit denial, approval-required, absence of capture consent, direct-provider bypass, image/prompt bounds, external URL/SSRF attempts, malformed/failed model response, duplicate provider and untrusted prompt-injection output.

## Real on-device acceptance still outstanding

- Install/start Ollama with **licensed local Qwen-VL weights**, verify model readiness, GPU/memory pressure, real image decoding, end-to-end user consent and owner session, and test on-screen/camera integration. No live model daemon was available in CI.
- PNG/JPEG/WebP signatures are minimum routing checks, not full image parser/security guarantees. Model input parser, decompression-bomb limits, image redaction, privacy and human content safety should be independently reviewed for untrusted captures.
- Feature #77 is **TESTING/PARTIAL_VERIFIED** only after exact-head Core/Persistence/Final Release Lock CI, not `COMPLETED`. Real authenticated UI, performance measurements, model license, hardware and video/real-time frame lifecycle remain separate work.
- The implementation does not make Ollama the AURA Core. Core remains deterministic and provider-agnostic. All actual model invocation remains behind the separately authorized MCP Gateway.
