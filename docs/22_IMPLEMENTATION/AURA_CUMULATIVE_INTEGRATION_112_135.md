# Cumulative AURA integration review — PR #112–#135

**Status:** verification branch only; NO source merge into main, NO Owner production acceptance, NO capability marked COMPLETED.

## Exact included feature PR heads

| PRs | Module group | Integration strategy |
| --- | --- | --- |
| #112, #114 | Gateway research + dossier | Added in dependency order; unchanged tool authorization |
| #116–#119 | Filesystem, memory, Core integrity, knowledge | Preserved existing Core PermissionEngine and deny-only guarding |
| #120, #121, #131 | Generation-safe full-duplex speech, wake phrase and prosody | **Manually reconciled** #120 and #131 modifications to `application/full_duplex_session.py`; added advisory prosody events only while the original session+generation is still valid |
| #122–#124 | Local TTS metadata routing, health status, PCM signal | Preserved optional bounded composition; no new permissions |
| #125–#126 | Monitor geometry and HUD layout | Assembled both stacked dependencies; no direct window/screen control |
| #127–#130 | GitHub read, home inventory and HA state, skill proposals | Imported exact reviewed source files; no direct tool invocation bypassing MCP Gateway |
| #132–#135 | Desktop foreground, speaker detection, governed mouse/keyboard, Piper offline voice | Imported testable source + model adapters, kept exact native and Owner constraints; #135 fixed release inventory excludes `core/scripts` per canonical generator |

Closed duplicate PR #113/#115 are **not** included. This review branch is based on pinned `main` `b1ffe6f534ced0d329dae273a4b949a634cb8bfa`; it does not implicitly contain older unmerged PR #64–#111 and therefore **cannot yet prove full 117-feature integration**. Earlier PRs and their merge/feature dependencies still need independent reconciliation before full acceptance.

## Source lock and proof

The combined `release-manifest.final.json` now inventories **253 exact source files** selected by the canonical `core/scripts/generate_final_lock.py` rules (`core/src`, `aura-ui/src`, package/lockfiles). Scripts/tests/docs stay outside the production source digest as specified by repository governance. The full list was compared against the exact current branch Git tree and has zero missing/extraneous paths.

CI must execute `cd core && uv run pytest -q`, `cd core && uv run python scripts/verify_final_lock.py`, and Remote Persistence; a branch-level PASS is not equivalent to production hardware or a merged release. Four new cross-module tests exercise real SQLite principal isolation, Core PermissionEngine+MCPGateway reading Home inventory then HA entity state, authenticated monitor EventBus->HUD geometry flow, and real WAV/prosody DSP bound to the generation-safe speech manager. Hardware, real signed credentials and live microphone/Piper execution remain separate evidence gaps.

## Trust boundaries

- Kernel, ServiceRegistry, CapabilityRegistry, ProviderRegistry, PermissionEngine and EventBus remain authoritative. Tool execution always passes MCP Gateway authorization.
- Owner identity and consent must be authenticated by the existing application composition. Mere metadata/event hints never grant authority.
- Any future actual privileged robot, computer, camera, external provider or file modification must get separately reviewed higher-risk capability policy and real Owner approval.
- This is a **Draft** integration PR and no contained feature is promoted to COMPLETED. All old individual feature PRs remain open and unmerged.
