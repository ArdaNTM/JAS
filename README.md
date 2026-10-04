# JARVIS Architecture Specification (JAS)

Official architecture specification and implementation repository for the JARVIS / AURA system.

This repository contains:

- the JAS architecture and version-governance source of truth;
- AURA Core implementation under `core/`;
- AURA desktop/web UI under `aura-ui/`;
- acquisition, ADR, documentation, templates, and version-lock material;
- deterministic release-lock artifacts.

## Architecture

JAS remains the architecture and version-governance authority.

AURA Core provides the deterministic execution foundation:

`Kernel → ServiceRegistry / CapabilityRegistry / ProviderRegistry → PermissionEngine → MCP Gateway → Provider`

Provider implementations are not allowed to bypass the capability and authorization boundary.

The local inference baseline is Ollama with the locked Qwen3 configuration defined by the JAS version-lock documents.

## Repository layout

- `core/` — AURA Core runtime, APIs, security, MCP, agent execution, tests, and release tooling.
- `aura-ui/` — AURA React/Vite/Electron user interface.
- `docs/` — architecture and approved-stack documentation.
- `version_lock/` — version-lock and release-governance source material.
- `acquisition/` — host and acquisition evidence.
- `adr/` — architecture decision records.
- `release-manifest.final.json` — deterministic SHA-256 release lock for the selected implementation files.

## Validation

The implementation is validated by the Core Python test suite, frontend production build, and release-lock verification scripts.

The release lock covers the implementation files selected by `core/scripts/generate_final_lock.py`. Generated caches, virtual environments, dependency installation directories, build output, and backup artifacts are excluded.

## Status

The repository contains implementation code. Real-world infrastructure/provider validation remains separate from deterministic source-level validation; live PostgreSQL/Qdrant, Ollama inference, browser/voice/vision/computer providers, and final environment-specific deployment checks must be validated on the target host before claiming full production deployment readiness.
