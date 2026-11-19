# Unified integration acceptance inventory

Status: **INTEGRATION / NOT OWNER-ACCEPTED**.

Base: immutable main b1ffe6f534ced0d329dae273a4b949a634cb8bfa.

Canonical cumulative history: PR #150 → #151 → #152, which already aggregates 56 commits and 114 changed paths from its ancestry. This branch was created from main and safely fast-forwarded to #152, never force-pushed. The F2.7 PR #64 sealed security branch was neither merged nor modified.

Additional direct source transplants from the authoritative PR #65 tracker: pack PRs #153–#156, opt-in scoped-memory PR #157, and all *previously absent* tracked core/src paths with their ledger-pinned commits. Governance docs and validator derive from PR #65. There are no duplicate Kernel, PermissionEngine or Gateway implementations.

## Important limits and conflicts

1. **Source-path coverage is not equivalent to Git merge.** An indexed path may have patches in multiple unmerged PRs; existing overlapping paths (main.py, gateway.py, episodic_memory.py, hierarchical_memory.py, full_duplex_session.py, permissions.py, etc.) were not blindly overwritten.
2. A PR's tests or documentation outside the tracker are not necessarily copied. This integration must not be treated as equivalent to merging all 84 unique feature PRs.
3. Exact source inventory and release digest must be computed on this branch after transplants; previous branch-specific manifests do not apply.
4. Cross-module import smoke, real SQLite+Gateway approval tests, protected terminal task suite and full Core regression are engineering acceptance only. No live Windows desktop, root broker, NTFS ACL, Docker security boundary, camera, GPU/3D or physical robot proof is claimed.
5. No production self-modification, default Owner/robot/shell grants or automatic merge. PR #64 is excluded pending independent live attestation and Owner release review.
6. PostgreSQL/MinIO CI service tests do not establish migration, durability/DR under real production credentials or physical acceptance.

## Outstanding review gate

An Owner must select authoritative versions of overlapping modules, conduct source/commit-lineage review across all unmerged PRs, run one combined source inventory and test suite, validate end-to-end provider and storage behavior on actual hardware, and sign the production release. Record feature-specific evidence before any COMPLETED state. At this stage, unmerged review PRs and partial hardware tests remain blockers.
