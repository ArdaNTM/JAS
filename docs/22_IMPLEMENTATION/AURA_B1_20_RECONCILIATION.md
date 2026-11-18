# B1 20-feature pinned source regression reconciliation

Baseline: PR #158 head at 9a558745; original PR #65 feature index. This assessment restores **13 distinct originally missing focused test files** from their **tracker-pinned exact commits**; 20 B1 features have **19 distinct indexed test paths** (some features share the same test). No full feature completion or independent security approval is inferred from test presence or green unit CI.

## 20 feature acceptance inventory

| Feature | Focused tests (Core relative) | Open full-capability gaps | Status |
|---|---|---|---|
| #8 Hafıza çelişkilerini tespit etme | `tests/test_memory_conflict_candidates.py` | Human-approved correction workflow; Temporal/source-confidence reasoning; UI review and independent acceptance | TESTING / NOT_VERIFIED |
| #10 Uzun vadeli hedef ve planlama | `tests/test_goal_planning.py` | Owner-approved persistent goals and scoped progress record; Independent task completion receipts; Deadline/resource planning and real execution feedback | TESTING / NOT_VERIFIED |
| #12 Geçmiş hatalardan öğrenme | `tests/test_repeat_failure_reviews.py` | Per-principal durable outcome isolation; Longitudinal evidence of improved task outcomes; Approved improvement integration | TESTING / NOT_VERIFIED |
| #21 Konuşma geçmişi | `tests/test_offline_conversation_review.py` | Authenticated persistent conversation journal; Encryption, retention, backup/privacy erasure lifecycle; End-to-end user controls and device sync | TESTING / NOT_VERIFIED |
| #35 Gelişmiş web araştırması | `tests/test_gateway_multiquery_research.py` | Hardened live research network/SSRF/redirect provider; Owner-authorized external search and fetch safety; Source credibility and production end-to-end verification | TESTING / NOT_VERIFIED |
| #36 Kaynak doğrulama | `tests/test_research_source_evidence.py` | Independent page fetch and content verification; Publisher/date trust checks; DNS and redirect egress enforcement | TESTING / NOT_VERIFIED |
| #37 Çok kaynaklı karşılaştırma | `tests/test_cross_capability_comparison.py` | Consolidate PR #77 and #78 boundaries without duplicate runtime authority; Prove independent publication identity; Integrate under authorized research Gateway + review UX | TESTING / NOT_VERIFIED |
| #38 Akademik araştırma | `tests/test_academic_citations.py` | Authorized OpenAlex/Crossref retrieval integration; DOI verification and provenance/recency; Full academic discovery acceptance | TESTING / NOT_VERIFIED |
| #39 PDF ve belge analizi | `tests/test_docx_extractor.py` | PDF processing; OCR/rendered layout analysis; Authorized file pipeline and UI | TESTING / NOT_VERIFIED |
| #41 Yeni gelişmeleri takip etme | `tests/test_research_feed_monitor.py` | Principal-scoped persisted feed snapshots; Explicitly approved scheduler/notifications; Live transport and publisher attestation | TESTING / NOT_VERIFIED |
| #42 Araştırma hafızası | `tests/test_research_archive.py` | Authenticated source archive UI; Encryption and key rotation; Remote/backup synchronization | TESTING / NOT_VERIFIED |
| #43 Derin araştırma modu | `tests/test_research_dossier.py`, `tests/test_gateway_multiquery_research.py` | Governed model planning and re-query decisions; Real source trust and contradiction verification; Approved production review and synthesis workflow | TESTING / NOT_VERIFIED |
| #52 Sürümleme ve geri alma | `tests/test_text_change_preview.py` | Actual Git version/branch management and conflict resolution; PermissionEngine/MCP-governed persistent writes; Atomic rollback, verified restore and signed Owner acceptance | TESTING / NOT_VERIFIED |
| #53 Dokümantasyon üretimi | `tests/test_python_code_insight.py` | Authenticated repo integration; Versioned documentation publication/preview; Reference diagrams and human editorial review | TESTING / NOT_VERIFIED |
| #62 Görev koordinasyonu | `tests/test_goal_planning.py` | Authenticated agent assignment and scheduling; MCP/PermissionEngine-authorized execution integration; Real cancellation/recovery and coordination acceptance | TESTING / NOT_VERIFIED |
| #65 Hipotez üretimi | `tests/test_experiment_design.py` | Grounded literature, provenance, measured scientific novelty; Scientific validation and independent subject matter review | TESTING / NOT_VERIFIED |
| #66 Literatür taraması | `tests/test_scientific_evidence_triage.py` | Authorized live bibliographic/full-text retrieval; Qualitative and methodology screening, peer review; Independent citation authentication and researcher acceptance | TESTING / NOT_VERIFIED |
| #76 Bilimsel keşif hafızası | `tests/test_scientific_journal.py` | Verified scientific publisher and experiment provenance; Actual independent discovery validation and review; Encrypted durable memory, deletion, duplication and audit recovery | TESTING / NOT_VERIFIED |
| #102 Prompt injection koruması | `tests/test_untrusted_context_bounds.py` | Adversarial model/tool evaluation; Gateway argument taint testing; Multilingual prompt injection evaluation | TESTING / NOT_VERIFIED |
| #112 Rapor ve sunum üretimi | `tests/test_offline_xlsx_report.py` | Authorized report export route and UX; Additional DOCX/PDF/PPTX renderers and templates; Cross-client and production owner acceptance | TESTING / NOT_VERIFIED |

## Newly restored original tests (no source rewrite)

| Test path | Index-pinned original commit |
|---|---|
| `core/tests/test_goal_planning.py` | `1e2980c164575f7e5f366920a816176cec783d06` |
| `core/tests/test_repeat_failure_reviews.py` | `277f8f1416366f9b2bca3fca0d6e2f26e1a95724` |
| `core/tests/test_offline_conversation_review.py` | `f77b68f25c1615831b039541891bf28ee4c86834` |
| `core/tests/test_research_source_evidence.py` | `c8d2b859b9adc70ae135543fb16c5a8ecdadcca9` |
| `core/tests/test_cross_capability_comparison.py` | `2ddbcc1eff0e43a15fa7e9a0d55198503287f111` |
| `core/tests/test_docx_extractor.py` | `97d39e6c5736bcf3dc0fe232aaf20a0f5848ef3c` |
| `core/tests/test_research_feed_monitor.py` | `d6f4a25b68e7e48745a4b8c3849fdd0252926db4` |
| `core/tests/test_text_change_preview.py` | `a01f8512232b9ab6dd739ef00825c4352eb332f8` |
| `core/tests/test_experiment_design.py` | `e7b08362dad84727d33a405065b860e80af25977` |
| `core/tests/test_scientific_evidence_triage.py` | `1c04ffb4bc585d56d9517014b449e57e6ad6cc8a` |
| `core/tests/test_scientific_journal.py` | `0c65a0409616f8adeca7f50eb6544de4b69d343e` |
| `core/tests/test_untrusted_context_bounds.py` | `a4a156b42ae8f8ecfa7aff37604386f05f170dd1` |
| `core/tests/test_offline_xlsx_report.py` | `02f0ab2f242135b873e667710fe6ac29d4a198dc` |

CI-only regression evidence does not prove publisher identity, model prompt injection resistance under real model/provider, live HTTP/SSRF control, Owner-approved tool execution or real retention/backup. In particular, #35, #36, #38, #39, #41, #43, #66 and #112 still require external/real environment behavior even though they are provisionally B1 candidates; these are not safe to mark COMPLETED merely because the offline source is present.

All twenty records retain their authoritative PR #65 missing_components and blockers, `acceptance=NOT_VERIFIED`, and `security_review` without independent sign-off. The source lock records runtime source files, not separate regression test files. Any future COMPLETED requires validation of feature-specific real operation and independent review, with the unchanged MCP Gateway authorization boundary. No PR is merged automatically.
