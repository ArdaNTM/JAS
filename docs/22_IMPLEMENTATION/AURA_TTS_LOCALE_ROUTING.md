# Language-aware local speech provider routing preview — feature #19 (partial)

`core/src/aura_core/tts/language_route.py` performs a **read-only** locale/provider compatibility check using existing AURA Core `CapabilityRegistry` and MCP `ProviderRegistry`. No new provider is registered and no tool invoked. Actual TTS execution remains exclusively `MCPGateway.invoke` with the existing `PermissionEngine` decision and separate Owner/session authorization.

## Current bounded behavior
- Support explicit `tr`, `tr-TR` only for configured `tts.piper`; `en`, `en-US`, `en-GB` only for configured `tts.kokoro`. These are conservative *configuration mappings*, not claims that all downloaded voice models or locales are available.
- Inspect the existing authoritative `speech.synthesize` capability resolution, its exact provider ID, VOICE category, MCP provider type and `synthesize` tool binding; compare to the locale-intended provider.
- Reject unknown/malformed locales, missing/unhealthy/unavailable capability/provider, and any mismatch between language target and **the Gateway's actual chosen provider**. No fallback to another language or unauthorized model download.
- Return only an immutable `LanguageRoutePreview(guarantee='METADATA_ONLY_NOT_AUTHORIZED')`; the preview is **not** a signing credential, authorization, task approval or lease. A later Gateway call must recheck provider health, capability selection, schema and PermissionEngine because the registries may change.

## Tests
`cd core && uv run pytest -q tests/test_tts_language_route.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use actual ServiceRegistry, CapabilityRegistry and ProviderRegistry with dummy provider instances that throw if executed; cover Turkish/English locale selection, missing/failed providers, unavailable capability, injected/malformed locale, priority conflict and exact tool name. No real voice weights/audio synthesis is claimed.

## Missing full acceptance
- This is route **preview**, not automatic bilingual full-duplex conversation. The current bootstrap config chooses one provider at a time; simultaneous multi-provider registration, language detection from live STT, automatic speech output, output language quality, audio device and user-controlled switching remain unverified.
- The existing `FullDuplexSessionManager` includes a hardcoded Turkish STT configuration; this PR does not change it or the current MCP Gateway dispatch/PermissionEngine boundary.
- Real Piper/Kokoro model availability, license validation, latency, voice provenance, Owner acceptance and production UI are untested. Feature #19 must remain TESTING/PARTIAL_VERIFIED (not COMPLETED) after exact-head CI.
- No added library, model/API dependency or license.
