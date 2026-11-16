# Governed read-only GitHub pull request status — feature #54 (partial)

This slice adds `aura_core.application.governed_github_pr.GovernedJASPullRequestReader`, an exact-repository, read-only facade over the **existing** AURA MCP Gateway and Core PermissionEngine. It cannot use a GitHub SDK, arbitrary HTTP requests, credentials, repo mutations, branch pushes, issue edits, PR creation/closing or merges. The only repo target is the authoritative `ArdaNTM/JAS`.

## Security contract
- Trusted composition must bind a separately **authenticated** principal in the constructor. No public read call accepts an arbitrary principal or repository name.
- `read(pr_number)` validates an exact integer 1..1,000,000, then constructs `MCPGatewayRequest` with capability/operation `github.pull_request.read`, risk `LOW`, exact scope `github/ArdaNTM/JAS/pulls/<number>`, tool `get_pull_request` and fixed owner/repo arguments.
- The existing MCP Gateway handles registered capability/provider resolution and PermissionEngine authorization. DENY/DEFER/REQUIRE_APPROVAL is **not** a read grant. The module performs no direct provider execution or implicit registration of policy/capabilities.
- On ALLOW, accepts only bounded structured PR metadata that matches the requested repo/PR; validates 40-character SHA, enum state, draft/merged booleans, safe base reference, bounded title. Returns an immutable `PullRequestStatus(trust='UNTRUSTED_PROVIDER_METADATA', read_only=True)` with no body/credentials, no untrusted URLs or raw tool error text.
- A provider result is still **untrusted**; this layer is not independent GitHub identity/commit authenticity attestation or Owner authorization. The caller must not use returned data to bypass the governance/review and merge policy.

## Tests
`cd core && uv run pytest -q tests/test_governed_github_pr.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

Tests use real Service/Capability/Provider registries, `PermissionEngine`, `MCPGateway` and a fake, networkless registered MCP provider. They prove explicit ALLOW, exact scoped denial, default-deny before provider execution, malformed metadata, wrong repo, invalid PR number/identity, no write method and sanitized provider errors.

## Missing acceptance
- No actual registered GitHub MCP provider or live OAuth/token proof is installed by this PR. Production discovery/bootstrap, PAT/OAuth rotation, GitHub rate limits, human Owner identity, zero-write policy enforcement, real remote evidence and PR management UI remain unverified.
- This is read-only PR **status** metadata, not full GitHub management. No merges or pushes must be automated. Feature #54 stays TESTING/PARTIAL_VERIFIED after exact-head Core/Persistence/Release Lock CI, never COMPLETED without real authorization and Owner acceptance.
- No new dependency or license. Main pinned; existing unmerged branches not edited.
