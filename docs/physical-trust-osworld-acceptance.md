# AURA Stage D — Physical Trust / Network Egress / Trusted Promotion

This is an opt-in, **review-only** integration on top of Stage C and PR #57.
Kernel, PermissionEngine, Service/Capability/Provider registries, EventBus,
MCP Gateway and immutable release-lock rules are unchanged.

## Physical acceptance

The new module \`aura_core.acceptance.hardware_gate\` consumes independently
Ed25519-signed, canonical records for:
- actual WebAuthn UV, signed exact-origin and replay/duplicate rejection;
- Nirvana Voice first-audio p50/p95 with at least 30 physical microphone samples;
- barge-in p50/p95 with at least 30 interruption samples;
- mixed-DPI two-monitor layout, display hotplug, negative coordinates, hit testing;
- persisted emergency stop and no post-kill dispatch.

Default illustrative thresholds are 100 ms p95 first-audio, 150 ms p95
barge-in, 250 ms p95 emergency stop; these are **limits**, not measurements.
An operator must provision and audit a physical hardware evidence signer outside
AURA; Core receives only public keys. WebAuthn UV may be verified with PIN,
and does not necessarily prove face or fingerprint biometric authentication.
CI uses synthetic signed test fixtures; never report those as physical proof.

## Network egress contract

\`aura_core.network_egress.policy\` supplies an authenticated, bounded
loopback HTTPS CONNECT proxy that resolves once, rejects any non-global DNS
answer, dials the explicitly pinned public IP and checks the socket peer.
Browser Chromium verifies original hostname TLS/SNI through the tunnel.
Service Workers, HTTP non-GET/HEAD, popups and WebSockets remain blocked in the
Stage C Playwright adapter. Browser opt-in now fails closed unless both the
proxy URL and strong token are configured.

**This proxy is NOT a firewall.** A separate disposable user+VM network
namespace must block every direct browser outbound connection (IPv4, IPv6,
DNS, UDP, QUIC, WebRTC) except the authenticated localhost proxy, and restrict
the proxy's own outbound traffic to TCP/443 to public IPs. Test the firewall
with deliberately blocked direct connections and DNS-rebinding fixtures.
\`AURA_STAGE_C_EGRESS_FIREWALL_CONFIRMED=1\` and
\`AURA_EGRESS_FIREWALL_CONFIRMED=1\` express operator preconditions but do not
prove them. Never assert production egress security from only an environment
flag.

Example operator-only setup in a disposable VM:

\`\`\`powershell
$env:AURA_EGRESS_FIREWALL_CONFIRMED = "1"  # only AFTER independent firewall verification
$env:AURA_EGRESS_PROXY_HOSTS = "example.org"
$env:AURA_EGRESS_PROXY_TOKEN = "<256-bit random hexadecimal secret>"
uv run --frozen python scripts/start_pinned_egress_proxy.py --port 8769

# In the separately configured AURA VM shell:
$env:AURA_STAGE_C_EGRESS_ISOLATED = "1"
$env:AURA_STAGE_C_EGRESS_FIREWALL_CONFIRMED = "1"
$env:AURA_STAGE_C_EGRESS_PROXY_URL = "http://127.0.0.1:8769"
$env:AURA_STAGE_C_EGRESS_PROXY_TOKEN = "<same secret>"
$env:AURA_STAGE_C_BROWSER_ORIGINS = "https://example.org"
\`\`\`

Never put proxy secrets in source, GitHub CI logs, shell arguments or HUD.

## Owner receipt bridge

\`aura_core.evolution.trusted_promotion.TrustedPromotionBridge\` only
activates a **preinstalled** healthy MCP capability. It checks:
- quarantined guarded source SHA256 and exact reviewed SkillBinding;
- durable independent signed sandbox attestation (specific runner/image/tests);
- registry's *exact* pinned attestation verifier and durable Owner receipt
  consumer identity;
- operation-bound, single-use signed WebAuthn Owner receipt;
- existing PermissionEngine policy at time of receipt consumption.

No model or HUD creates a receipt, imports Python, rewrites
\`release-manifest.final.json\`, runs \`generate_final_lock.py\`, edits
Kernel/Security or registers a new MCP provider. A signed receipt is produced
only by the separate owner service after actual WebAuthn validation.
The bridge returns a \`MCPGatewayRequest\` for execution rather than calling
a provider directly.

## OSWorld-V2.1 real VM gate

The existing \`scripts/osworld_v2_lab.py\` still returns **DRY_RUN_ONLY**.
Nothing in this PR fabricates official benchmark scores. Real evaluation
requires pinned \`osworld-v2.1\` code, assets, task classes, website mocks
and VM image, the independent evaluator, a disposable host and network
firewall verification. Task budgets and trajectory should be recorded and
verified through the MCP Gateway. No VM is provisioned in GitHub CI.

## Reproducible tests

\`\`\`powershell
cd D:\AURA\JAS-physical-trust-test\core
uv sync --frozen --group dev
uv run --frozen python -m pytest -q tests/test_physical_trust_bridges.py
uv run --frozen python -m pytest -q
uv run --frozen python scripts/osworld_v2_lab.py
uv run --frozen python scripts/hardware_stage_c_acceptance.py
uv run --frozen python scripts/verify_final_lock.py
\`\`\`

The independent hardware/VM acceptance remains BLOCKED until physically
collected signed evidence and OSWorld official artifacts are supplied.
