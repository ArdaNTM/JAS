# AURA engineering blockers

Updated 2026-11-15; evidence is repository inspection and user-supplied host logs, not independently verified host attestation.

- **F2.7 PR #64:** Draft; broker-owned VM lifecycle, signed isolation receipt, live SCM approval, and physical-host validation are not complete. Do not merge or activate.
- **117-feature assessment:** Existing code implements parts of several categories, but no comprehensive per-feature acceptance inventory has been demonstrated. Do not call unassessed features absent or complete.
- **Tools/hardware:** Dedicated physical robots, laboratory hardware, cameras and external keys cannot be claimed tested from CI.
- **External service/license audit:** Individual dependency/model licenses and cloud free-tier claims require review before selection.
- **Trust boundary:** Existing JAS Kernel/PermissionEngine/MCP Gateway and Owner approval must not be bypassed.

## Shared release-manifest merge consideration

Feature PRs #66, #67 and #68–#75 independently modify `release-manifest.final.json` because JAS requires a complete deterministic source inventory. Their *runtime code paths* are distinct, but their aggregate release-lock manifests cannot all be merged unchanged. Do **not** ignore conflicts, take "ours/theirs" indiscriminately, or bypass `verify_final_lock.py`.

After **explicit Owner merge approval**, integrate in dependency order, rebase each still-open feature branch on the new target and regenerate/review its manifest, then rerun Core, integration, security and release-lock checks. This is a known governance dependency, not a claim that code conflicts have been resolved. F2.7 #64 retains its independent Draft/review gate.

## Additional review dependencies — PRs #76–#83

- PR #77 and #78 both contribute feature #37 at distinct levels (independent source claims vs registered provider outputs); decide whether both are needed before any merge. Do not add duplicate execution authority.
- PR #76–#83 each re-lock independent main-baseline source inventories; aggregate release manifests **must be regenerated in integration order after explicit Owner merge approval**. Do not take an arbitrary side of conflicts.
- Offline feed parsing and citation normalization do **not** authenticate external sources or grant network access. Repeated-failure, diagnostics and telemetry summaries do **not** authorize execution or prove improvement.
- All affected features remain TESTING; no real security/Owner acceptance.

## Further integration blockers for PRs #84–#86

- Vocabulary review #84 needs authenticated principal/Owner boundaries before exposure; `confirmed=True` is not authorization and SQLite is unencrypted.
- Swarm admission #85 validates all steps before calls, but does not substitute for PermissionEngine/Owner authorization, verified outcomes or rollback for authorized partially executed plans.
- Context hardening #86 does not guarantee injection-free model behavior; hostile input testing requires actual model/tool-routing conditions.
- These branches each have separately generated Final Release Lock manifests; integration must recompute and retest after explicit merge approval.

## DOCX extraction acceptance and release-lock integration

- #87 is text-only and receives preauthorized bytes, but does not itself authenticate a principal. Do not expose it as a direct unapproved filesystem/MCP tool.
- PDF/OCR, external linked content, tracked changes, complex DOCX layout, full document-corpus testing and end-to-end UI are outstanding.
- #87 modifies the separately calculated complete release manifest; integration with the other independent PRs requires review, regenerated manifest, and a fresh CI run after explicit Owner merge approval.
