# AURA convergence candidate — not a production approval

Base: PR #53, commit 0f02be25810756eef5c0d6a894eb3f9646dc7a4c
Cherry-picked source content from PR #51 (312bb5455f4cc047d9d50f815abce4e96cd8e114) and stacked PR #52/#54 (581693bccb391cf7b25bc511b11cb2dfc403f7a2).

## Included in this candidate
- Existing read-only Evolution Review HUD + separate owner WebAuthn control plane from PR #53.
- Multi-display Spatial HUD, model-estimated ScreenRead overlays and Gateway-governed Wikimedia media search from PR #51.
- Opt-in PCM AudioWorklet, streaming voice, sherpa-onnx and Kokoro provisioned tools from PR #54 (includes PR #52).
- Conflict resolutions in Core composition, shared App and API, plus reconstructed SHA-256 release-lock inventory.
- Additional lock coverage for Electron main/preload and PCM worklet files.

## Outstanding release blockers
- Audit high/critical npm findings in aura-ui and core/frontend; do not suppress, force-install or claim green.
- Integrated Windows/Linux E2E, microphone/overlay native acceptance, GPU/ASR performance and hardware WebAuthn proof.
- OSWorld/LangGraph multi-agent computer-use evaluation and explicit capability/policy consent matrix; NOT enabled here.
- Trusted attestor runner and issuer verification, OS principal isolation and key lifecycle acceptance.
- No autonomous activation of tools, code, system permissions or packages.

## Required checks (fail closed)
From core: uv sync --frozen --group dev; uv run --frozen python -m pytest -q; uv run --frozen python scripts/verify_final_lock.py.
From aura-ui: npm ci; npm run build; npm audit --audit-level=high.
From core/frontend: npm ci; npm run build; npm audit --audit-level=high.
Run Windows launcher, owner ACL and native HUD/speech tests, then check git status --porcelain.

**Draft integration only; leave main and the source PRs unchanged.**
