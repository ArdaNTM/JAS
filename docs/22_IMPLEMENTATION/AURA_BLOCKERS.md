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

## New partial feature limits for #88 and #89

- PR #88 only analyzes already-authorized Python source text; AST callsite matches are heuristic and do not prove a system safe. No GitHub management rights, publishing, self-editing or autonomous fixes granted.
- PR #89 only processes already-authorized UTC/all-day calendar text. Recurrence/TZID/VALARM/attachments fail closed, so do not present it as a full calendar or enable automatic reminders.
- Both have separate release manifest states generated against old `main`. Regenerate combined manifests and rerun all assurance gates after explicit Owner merge approval.

## PR #90–#92 acceptance and architecture gaps

- #90 SHA-256 manifest detects corruption only: no independent signature, encryption, authenticated identity receipt, durable isolated storage or restore drill. Do not use it as production secret backup.
- #91 hypotheses are templates from user-specified assumptions; simulated allocations are not ethical approval, real participant enrollment or validated scientific findings.
- #92 RK4 toy-model output is a numerical approximation, not a calibrated/safety-certified physics/engineering solver. Hardware/physical/convergence verification remains false.
- As with the earlier independent PRs, integrating these separately generated release manifests requires sequential reconciliation and full CI after explicit Owner review. Never merge automatically.

## PR #93–#94 trust boundaries

- #93 email MIME parser does not read an actual inbox, authorize recipients or actions, authenticate senders, execute HTML, scan malware, or open attachments.
- #94 PNG/GIF/WAV header validation is not full-file structural validity nor render safety; no parser may treat a recognized header as authorization.
- Both branches have independent main-baseline release digests. Integration must recalculate the combined manifest, run full tests and obtain Owner approval before merge.

## Further PR #95–#96 integration limits

- #95 event observations are untrusted; Gateway decision replies are not independent tool execution/Owner approval receipts. A one-shot Markdown report is NOT automatic reporting/scheduling.
- #96 STL is deterministic closed geometry but is not material/printable/structurally certified. No production printer/robot control is enabled.
- Both add their own release-manifest changes against a common main; integration must reconcile source inventory and re-run locks/tests sequentially after explicit Owner approval.

## PR #97 acceptance gap

- A topological plan is not an execution authorization. Claimed completed nodes are not signed outcome receipts. Independent verification, principal-scoped persistence, Owner decisions and actual task dispatch are required.
- The PR has an independent complete Final Release Lock manifest against old `main`; combined integration must recalculate and re-test after Owner-approved merge order.

## New reviewable PRs #98–#101: outstanding production gates

- #98 speaker labels are not authenticated identities and `remember:` text is never Owner-approved or persisted. Volatile erasure is not persistent/backups erasure.
- #99 role identifiers are caller-supplied, not signed agents; data-only in-process queue does not provide cross-process delivery or permission.
- #100 DOI shape does not establish actual published source authenticity; material property ranges are unverified claims and no physical material suitability proof exists.
- #101 patch/undo transactions only calculate in-memory content; they do not read/write files, perform Git operations, guarantee atomic disk rollback or grant Owner authority.
- Every PR has its own Final Release Lock manifest. An actual integration sequence must reconcile source inventory and re-run full CI under explicit Owner approval; #64 remains Draft.

## New scoped implementation gaps — PRs #102–#104

- #102 really stores local SQLite notes but has plaintext storage, unverified DOI/speaker source, no authenticated Owner receipt, no WAL/backup erasure, no independent scientific discovery acceptance.
- #103 calculates latency between untrusted in-memory KernelEvents; no trusted clock or proof of actual tool success/performance certification.
- #104 generates runnable pytest code from user-supplied contracts; test execution must pass authenticated Owner/Gateway and isolated sandbox approval. CI runs only known controlled test modules; no automatic fixes, repository edits or deployment are enabled.
- Each branch has a separate complete Release Lock manifest; reconciliation and fresh full CI are mandatory after explicit review and any eventual merges.

## PR #105 remaining trust boundaries

- Specialist profiles are caller-supplied, not authenticated identities. The registry validates provider registration/availability, **not** authorization. Actual task execution still needs Owner/PermissionEngine/MCP Gateway checks.
- This does not create or evolve new skills, agents or registered capabilities, nor permit privileged actions. Features #57/#64 remain partial.
- Its own Final Release Lock manifest differs from other open PRs; any combined merge requires reconciled inventory, fresh full CI and explicit security/Owner acceptance.

## PR #106: independent audit checkpoint integration gaps

- #107 checkpoint bytes are HMAC-authenticated only when the verifier controls a **separate** secret; no secure external key custody, WORM write-ahead audit store, trusted producer identity or complete Gateway event capture exists in this PR.
- Local ledger is mutable and in-memory. Missing-event attacks before signing and joint compromise of signer+ledger are not solved by this slice. Scope digests are not authorization.
- The PR carries a main-baseline complete source lock; reconcile all manifests and rerun combined CI only after explicit Owner-approved merge order. No automatic merging; no full acceptance.
