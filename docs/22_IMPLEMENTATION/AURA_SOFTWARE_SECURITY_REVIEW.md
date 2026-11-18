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
