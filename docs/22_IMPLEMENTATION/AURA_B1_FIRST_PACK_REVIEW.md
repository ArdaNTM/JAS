# B1 — First Software Acceptance Pack (10 features)

**Evidence anchor:** unified Draft PR #158 commit `fb7c9a4f3c892972fc6450cc1b7d3412257dc055`; authoritative source index: PR #65. No source modifications or test reruns were needed for this **review**. Real CI at the pinned head: 7/7 workflow runs PASS; 1494 PASS / 10 SKIP Core; PostgreSQL/MinIO 8 PASS; unified 10 PASS + A/B audit 8 PASS; source Release Lock 312 files PASS.

**Meaning:** code path exists != complete feature. These ten are prioritized review candidates, **not acceptance-certified**. Existing principal/permission boundaries and PR #64 seal are unchanged. The tracked `acceptance=NOT_VERIFIED` and substantive missing-components must be preserved.

| Priority | ID | Feature | Source on #158 | Pinned focused test on #158 | Concrete next acceptance gap |
|---:|---:|---|---|---|---|
| 1 | #8 | Hafıza çelişkilerini tespit etme | YES | `test_memory_conflict_candidates.py` YES | Owner-authorized correction flow; temporal and source-confidence checks; UI and independent human review |
| 2 | #38 | Akademik araştırma | YES | `test_academic_citations.py` YES | Actual authorized Crossref/OpenAlex retrieval and DOI/publisher provenance; don't treat metadata reconciliation as verification |
| 3 | #42 | Araştırma hafızası | YES | `test_research_archive.py` YES | Authenticated archive browse, encrypted persistence and key rotation, backup sync |
| 4 | #53 | Dokümantasyon üretimi | YES | `test_python_code_insight.py` YES | Authenticated Git source fetch, signed/versioned publication/preview, human editorial approval |
| 5 | #35 | Gelişmiş web araştırması | YES | `test_gateway_multiquery_research.py` YES | Audit live egress: DNS rebinding, SSRF, redirects, response limits, owner policies, real provider terms |
| 6 | #43 | Derin araştırma modu | YES | `test_research_dossier.py` YES | Unresolved parent PR #112, real governed model planning and independent source verification/synthesis |
| 7 | #10 | Uzun vadeli hedef ve planlama | YES | `test_goal_planning.py` **MISSING** | Reconcile focused test from pinned PR #97; approved persistent goal/priority ledger, signed progress/receipt and deadline feedback |
| 8 | #12 | Geçmiş hatalardan öğrenme | YES | `test_repeat_failure_reviews.py` **MISSING** | Reconcile regression from PR #79; scoped durable history, longitudinal evaluation and approved adoption |
| 9 | #36 | Kaynak doğrulama | YES | `test_research_source_evidence.py` **MISSING** | Reconcile regression from PR #69; genuine source fetch, independent publisher/date integrity, harden network/redirect safety |
| 10 | #37 | Çok kaynaklı karşılaştırma | YES | `test_cross_capability_comparison.py` **MISSING** | Reconcile regression from PR #78; reconcile PR #77/#78 overlap, signed independent source identities and Gateway UI |

**Verification methodology:** each named source and test file was fetched directly from `fb7c9a4` (GitHub blob lookup). `MISSING` means the explicitly referenced test file was not present in this unified tree; it does **not** prove the capability has no regression coverage elsewhere. Do not invent test execution results for absent files.

## Package exit gates

1. Restore or reconcile the four missing source-specific tests from their indexed PRs; preserve expected error/deny cases and run only focused tests during development.
2. Implement full remaining feature-specific software functionality, not a replacement stub or unauthenticated façade.
3. Run negative authorization and prompt-injection tests against real Kernel → Registries → PermissionEngine → MCP Gateway → providers, with live PostgreSQL where applicable.
4. Independent security/license/privacy review and feature-specific Owner acceptance; no external provider truth, network authorization or signed identity inferred from a CI fixture.
5. Only then change each feature's ledger to `assessment=VERIFIED`, `security_review=PASS`, `acceptance=PASS`, clear actual blockers, and promote to `COMPLETED` at an exact green unified commit.

No PR merged, no main modifications, and PR #64 F2.7 security boundary remains untouched.
