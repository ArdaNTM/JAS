# AURA 117: Group A software acceptance and source-security review

**Scope:** engineering review of source and CI evidence at unified Draft PR #158; **not** an independent security sign-off or Owner production acceptance. Canonical release boundary remains the existing Kernel, Registries, PermissionEngine, EventBus and MCP Gateway. No changes to F2.7 PR #64, `main`, runtime permission grants or encrypted store trust root.

## Evidence and classification

* Exact tracked grouping: [AURA_ACCEPTANCE_GROUPS.json](AURA_ACCEPTANCE_GROUPS.json): A = 9 candidates; B = 108 live/Owner/external acceptance gated. This classification reflects the **complete feature capability**, not a narrower helper function.
* Actual source provenance for five shared security-critical modules: [AURA_CORE_PROVENANCE_RECONCILIATION.json](AURA_CORE_PROVENANCE_RECONCILIATION.json), including verified Git blob hashes and divergent PR evidence.
* CI evidence on PR #158 before the audit changes: `0eccc2195401d29b91b5cc14a115f86c7341ef24`, Core Assurance 1333 passed, 9 skipped; Core Release Lock 304 source entries PASS; Remote Persistence, Windows launcher, HUD/Three.js build and unified E2E workflows PASS.
* Completion state is determined by the authoritative PR #65 ledger. Exact GitHub CI is engineering regression evidence, **not** a replacement for unverified feature-specific criteria.

## Group A source and security findings

| Feature | Verified software slice on unified tree | Outstanding acceptance / risk |
| --- | --- | --- |
| #2 Graph | `SQLiteGraphStore` / `PostgreSQLGraphStore` use principal-scoped parameterized queries and bounded depth. | No authorized user-facing erasure lifecycle, relation/version cleanup or independent live PG erasure acceptance. |
| #5 Tasks | SQLite `TaskStateMachine` has explicit task transitions, scoped retrieval and EventBus emissions. | Missing authenticated UI/API, durable user goal priorities and Owner-reviewed task completion. |
| #40 Reports | `research/citations.py` reconciles structured citation metadata with no tool execution. | Not an end-to-end cited report generator; document export and independent source-provenance review absent. |
| #44 Archive | SQLite archive requires explicit `consented`, checks `AuthorizationDecision.ALLOW`, bounds content and scopes reads/deletes. | Passing a response-like object is **not** cryptographic Gateway dispatch evidence; must wire the trusted response lifecycle and retention/backup/PDF format handling. |
| #47 Architecture | `code_insight.py` parses Python AST into data-only reports. | Authorized repository retrieval, cross-language graph, independent security adjudication and Owner UI absent. |
| #59 Agent IPC | `ScopedAgentMailbox` bounds sender/recipient data and tracks replay IDs, but is in-memory and explicitly marks sender_authenticated=False. | No authenticated agent identities, durable transport/retries or signed receiver receipts. **Cannot claim real agent communication is completed.** |
| #67 Math | Local finite sample analysis and simple linear regression with no tool authority. | Validated uncertainty, real research provenance and independent numerical reproducibility not shown. |
| #73 Scientific analysis | Offline descriptive statistics and linear fitting available. | Authenticated research dataset ingestion, experimental methodology/validation and report integration absent. |
| #111 Data analysis | `data_analysis/tabular.py` parses local bounded CSV and computes numeric/grouped summaries. | Authenticated file ingestion, large-scale streaming, sanitized export and Owner-facing UX absent. |

### Shared-path reconciliation findings

1. Canonical `main.py` Git blob is **exact** PR #152, with #150 and #151 in the ancestor chain. PR #146 and #147 also are ancestors; their older file bytes differ, which is expected and **not** proof of a conflict.
2. PR #135 `main.py`, PR #66 `episodic_memory.py` and PR #68 `hierarchical_memory.py` refs are **diverged** from PR #158 and have different corresponding blobs. Their unique patches and tests require explicit three-way reconciliation/acceptance.
3. `permissions.py` matches PR #118 **file blob** but PR #118's branch graph diverges: this does not certify its other commits. `gateway.py` matches PR #127. `episodic_memory.py` matches PR #117 and #157.
4. These spot checks cannot prove **all** features from PRs #66–#157 are functionally integrated. Unlisted PR-specific tests, source changes and indirect dependencies remain open review items.
5. No `COMPLETED` transition is justified until **each** feature-specific `missing_components`, `blockers`, `security_review`, `license_review`, `hardware_review` and independent `acceptance` record passes the feature tracker validator. Do not remove real blockers to make CI green.

## What remains necessary

- Preserve original PR heads; reconcile only proven modifications after code review. Do not force-update baseline or merge automatically.
- For A: build missing authenticated software routes, implement actual algorithms/flows promised by each feature, add positive/negative E2E with real SQLite/PG & Gateway authorization, perform independent security/license assessment, supply exact-head release-lock and UI integration evidence.
- For B: retain `TESTING` and require relevant physical device, Windows/NTFS/SCM, Docker daemon, production external-provider, verified Owner identity or manual release merge acceptance.
- The dedicated `scripts/audit_aura_117_completion.py` fails closed on forged group assignment, synthetic `COMPLETED`, missing evidence, or a change to the canonical five security source blobs. Passing this audit is **necessary but not sufficient** for release.


## 2026-11-18 bounded remediation tranche — new code, not production acceptance

All changes are on Draft PR #158, with F2.7 PR #64 security files untouched. The following components are **real, opt-in, bounded implementations**, but no application-wide Owner approval or independent product acceptance is inferred:

| Tracker ID | Newly integrated engineering capability | Remaining missing acceptance |
|---|---|---|
| #2 | Existing SQLite + PostgreSQL graph store gains `delete_fact`; `GovernedGraphMCP` binds principal to real Gateway dispatch; high-risk delete requires single-use SQLite approval. Live PostgreSQL CI test exercises genuine Postgres and Gateway. | Trusted authenticated HTTP/Owner delete UI and full graph relation cleanup, production data retention/erasure policy and independent review. |
| #5 | Versioned SQLite `TaskPriorityLedger` checks real TaskStateMachine owner and optimistic CAS; `GovernedTaskPriorityMCP` has zero implicit policies. | Production authenticated user task UI/API and accepted long-term planning UX; priority setting is not autonomous task execution. |
| #40 | Deterministic `SourcedReport` with provenance hash, references, real DOCX and Markdown rendering and safe OOXML text. | Cryptographically trusted publisher identity, independently verified citations, full source-backed narrative generation, approved delivery/download. |
| #44 | SQLite archive gains scoped metadata browse, retention prune, payload hash checks and async real Gateway fetch façade. | Fetch response from a bare Python argument is NOT authoritative; trusted ingress plus SSRF/redirect controls, retention/backup, PDF support and Owner privacy acceptance outstanding. |
| #47 | Read-only Python AST and bounded multi-file Python/Java/Kotlin/TS dependency inventory behind opt-in Gateway. | Java/Kotlin/TS extraction is explicitly lexical, **not compiler validated**; no real authenticated Git repository fetch or independent security verdict/UI. |
| #59 | Scoped agent mailbox actually persisted in SQLite; roster-bound Gateway MCP, HMAC-SHA256 keyed agent ingress, durable SQLite nonce replay protection, signed request/approval reference, single-use consumed approval for mailbox delete. | Keys are test-provisioned in CI, not live Owner-held credentials; no deployed agent process identities, actual cross-process delivery worker, verified action receipts or independent identity audit. |
| #67 | Deterministic OLS slope/intercept covariance errors and optional clearly labeled **asymptotic** normal interval (n>=30), finite-input guards, source digest. | Assumptions (iid/Gaussian/homoscedastic) **not validated**, no independent scientific reproducibility review or trusted empirical dataset. |
| #73 | Bounded experimental CSV parser, group comparison, OLS diagnostic uncertainty and data + calculation SHA-256 report identifiers. | Experiment design approval, independent dataset authenticity, scientifically validated methodology and user-facing report workflow. |
| #111 | Gateway-only CSV ingestion, local bounded arithmetic, literal-safe XLSX bytes, deterministic checksum, 500k-row bounded stream numeric aggregations. | Authorized production file upload/ingestion pipeline, front-end downloadable export and genuine large-volume benchmark/Owner acceptance. |

## Security review status and limits

- All new MCP adapters rely on **existing Kernel/Service/Capability/Provider registries, PermissionEngine, EventBus and MCPGateway**, and install **no ALLOW** policy or Owner privilege. Direct provider calls without the current Gateway dispatch grant fail closed. This is implementation-level negative-path review, not externally signed security assurance.
- HMAC key custody and application HTTP principal authentication remain deployer responsibilities. `AuthenticatedAgentGateway` verifies HMAC, timestamp and nonce before constructing `MCPGatewayRequest`. It does not certify physical device identity, TPM/NTFS integrity or human approver authentication.
- Existing `SQLiteApprovalStore.decide` is not an identity provider. A test approver identity does **not** count as signed Owner consent.
- Real PostgreSQL graph tests run only in GitHub Remote Persistence's actual postgres:16 service. Local Core CI skips them when `AURA_TEST_DATABASE_URL` is absent; this distinction is reported honestly.
- Historical PRs #66 and #68 are incorporated as their exact source Git blob variants; #135, #146 and #147 opt-in endpoint/source/test paths are already present as cumulative ancestors. See `AURA_CORE_PROVENANCE_RECONCILIATION.json`.
- **No Group A record should be marked COMPLETED solely because these tests pass.** Each original full-capability missing component, independent security review, relevant production authorization/Owner acceptance and final CI must be proven separately.


## CI verification at exact commit fb7c9a4 — engineering green, acceptance not signed

Verified GitHub Actions commit: `fb7c9a4f3c892972fc6450cc1b7d3412257dc055` (Draft PR #158). Seven workflows succeeded. Core Assurance: **1494 passed, 10 skipped** (run 44252417059). Remote Persistence on GitHub PostgreSQL/MinIO services: **8 passed** (run 44252416999). Unified E2E: **10 passed**, fail-closed A/B ledger: **8 passed**, final 312-file SHA256 Release Lock PASS (run 44252416980). Other Memory/Auth E2E, two subsystem assurance and Windows launcher workflows: PASS.

The *same* first-party ledger audit reports **A=9 / B1=20 / B2=88 / COMPLETED=0 / ELIGIBLE=0**. Verified GitHub review submissions: **no submitted reviews** on either Draft PR #158 or tracker PR #65. This does not prove independent security approval, signed Owner authorization or delivery/retention. Prior outstanding acceptance columns in this review remain open, including authenticated production key custody and real cross-process agent receipts (#59), publisher verification (#40), security-verified source retrieval (#47), assumption validation (#67), production user export/UX (#111), and GDPR erasure/backup lifecycle (#2/#44). No `security_review=PASS` or `acceptance=PASS` should be recorded without supporting independent evidence.

B1 first ten review candidates and source/test gaps: [AURA_B1_FIRST_PACK_REVIEW.md](AURA_B1_FIRST_PACK_REVIEW.md). The first B1 package is planning/review only; it is not eligible for automatic `COMPLETED` transitions.
