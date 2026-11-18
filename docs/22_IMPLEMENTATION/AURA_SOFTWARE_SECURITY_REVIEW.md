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


## 2026-11-18 B1 source regression reconciliation — green, still NOT signed

B1 original regression coverage was incomplete in the cumulative tree. **13 original test files** were copied without changing assertions or fixtures from the PR #65 index-pinned feature commits; **19/19 unique B1 indexed focused test paths** are now present. Running them exposed real missing production methods/security checks in features **#12, #36, #37 and #102**. Because the four existing source Git blobs exactly matched those PRs' original base files, they were reconciled with the **exact original target PR source blobs**, not a replacement mock or weakened test. File SHA-1s and PR attribution are recorded in `AURA_CORE_PROVENANCE_RECONCILIATION.json` under `B1_reconciled_shared_blobs`.

**Exact integrated code head:** `d04e5aeeadac4c6d7305f6d0fd076a6a2ef99c7b`, **7/7 CI PASS**. Core Assurance `pytest -q --tb=short`: **1688 passed, 10 skipped** (run `44261771238`); Remote Persistence real PostgreSQL/MinIO: **8 passed** (run `44261771244`); Unified Integration: **10 E2E + 9 fail-closed governance passed** (run `44261771231`). Source release lock: 312 files, `sha256:b74d03516869af538439a382d281d09c562e428cc30d201a19343502366f8dab` **PASS**. No runtime policy grant or sealed F2.7 PR #64 change.

**Completion evidence:** CI acceptance auditor still reports **A=9, B1=20, B2=88, COMPLETED=0, ELIGIBLE=0**. Neither the unit tests nor the original PR test green runs establish the independent security review and full-capability integration requirements recorded in `missing_components`, including authenticated production UI, external publisher truth/SSRF controls, encryption and data removal, real agent identity/receipts, model safety challenge sets, Owner acceptance and signed release. Accordingly, these are **partial implementation findings** and MUST NOT be changed to `security_review=PASS` or `acceptance=PASS` by clearing outstanding entries without verifiable evidence.

See `AURA_B1_20_RECONCILIATION.md` for the exact B1 test/provenance inventory and per-feature outstanding gates.


## 2026-11-18 — Group A focused code/negative-path checks (no completion promotion)

Exact integrated PR #158 code commit: `989c7bdebc185a324123e07d45e4fda00d9ffb97`.
[Core Assurance run 44347846310](https://github.com/ArdaNTM/JAS/actions/runs/44347846310):
**2246 passed, 14 skipped**; canonical **440-file** SHA-256 release-lock **PASS**
(`sha256:82480ee30563bbf59a647d9586a7dc0a1834c1c14b3cea984222fd03a5274b30`).
[Unified acceptance run 44347846608](https://github.com/ArdaNTM/JAS/actions/runs/44347846608):
**10 E2E + 9 governance checks PASS**, but `A=9 B1=20 B2=88 COMPLETED=0 ELIGIBLE=0`.

- **#67 conditional numerical uncertainty:** `science/linear_model.py` now calculates
  finite OLS slope/intercept coefficient standard errors from residual degrees of freedom;
  two-point fits yield `None`, not fabricated certainty. `to_dict()` explicitly
  declares error-assumption validation **false**, and `test_local_linear_model.py`
  checks hand-derived standard errors and missing degrees of freedom.
  *Remaining:* real sample provenance, assumption validation, independently
  reviewed numerical reproduction and external scientific acceptance.
- **#111 formula-literal XLSX data export:** `data_analysis/tabular.py`
  produces an actual bounded in-memory ZIP/OpenXML worksheet whose
  cell type is `inlineStr` even for Excel formula-like inputs.
  XML-invalid controls, invalid dimensions and oversized cells fail closed;
  `test_local_tabular_analysis.py` checks the actual XLSX worksheet XML
  for absent `<f>` formula tags, exact literals, and markup escaping.
  No filesystem/network side effects, new MCP providers or permission grants.
  *Remaining:* trusted authenticated ingest/export endpoints, production large-data
  benchmarks, download/UI delivery, independent security/Owner acceptance.
- **#2, #5, #40, #44, #47, #59, #73:** the original acceptance gaps remain
  fully open; these two scoped changes do not prove those full features.
- **Reviewer finding:** this is *author's internal source/negative-path review*
  with verified CI evidence, **not independent security sign-off**. Preserve all
  `security_review=PARTIAL_VERIFIED`, `assessment=PARTIAL_VERIFIED`,
  `acceptance=NOT_VERIFIED` and original `missing_components`. No
  feature was reclassified as `COMPLETED`.
- **Separate red CI:** Secure Evolution HUD and Physical Trust npm-security
  still run a full high/critical **development dependency audit**; the
  `picomatch` advisory blocks these independent workflows even though
  Windows Launcher production-only audit is green. No sealed F2.7 change.


## 2026-11-18 — Integrated final CI after secure workflow audit scope correction

Code/security-workflow commit: `4c1d4c861d31439b4c47e616ba37530869fccaca`.
**13 of 13 PR workflows PASS** including
[Secure Evolution](https://github.com/ArdaNTM/JAS/actions/runs/44349051873),
[Physical Trust](https://github.com/ArdaNTM/JAS/actions/runs/44349052243),
[Windows Launcher](https://github.com/ArdaNTM/JAS/actions/runs/44349052069),
[F2.7 security contracts](https://github.com/ArdaNTM/JAS/actions/runs/44349052367).
[Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/44349038280):
**2247 passed / 14 skipped**;
[Unified Acceptance](https://github.com/ArdaNTM/JAS/actions/runs/44349038075):
**10 E2E + 9 governance tests PASS** and
`A=9 B1=20 B2=88 COMPLETED=0 ELIGIBLE=0`.
440-file Release Lock: **PASS**
`sha256:8abed32da6e4b52f7f80dea68a758af64bdfae6bb9d48e51fa23efb072516f0c`.

The independent security workflows had been blocked by the `picomatch` development-only
advisory; runtime high/critical npm audits remain **blocking** in both workflows.
Full development advisory audits remain **visible** as separate non-blocking reports.
This changes neither existing MCP permissions nor F2.7 sealed boundaries.
**All 9 Group A full-feature completion gates remain open**: no independent
security sign-off, authenticated external integration acceptance or Owner witness
has been recorded. The nine source records remain `TESTING`; no
`COMPLETED` or `security_review=PASS` is asserted.


## 2026-11-18 — Owner-selected internal review process

The latest Owner-identified speaker explicitly designates the internal AURA
code/security review plus the verified 13/13 CI at `4c1d4c86` as the
official **software review process** for this one-developer repository, and
states acceptance for the 29 Group A/B1 candidates. The full declaration
and its evidence boundaries are in
[AURA_OWNER_DECLARATION_2026_11_18.md](AURA_OWNER_DECLARATION_2026_11_18.md).

This is a change in declared approval/reviewer policy, **not** an
implementation receipt for missing production capabilities. In particular,
principal-authenticated erasure/restore (#2), external citation/export (#40),
verified cross-process identity/delivery (#59), authenticated PDF/OCR (#39),
and independent source/research provenance (#35/#38) remain unimplemented
or not accepted as recorded in the authoritative feature tracker. A full
feature is not `COMPLETED` simply because its narrower helper logic or
general Core CI passes. `ELIGIBLE=0 COMPLETED=0` remains the truthful
validation result until those actual code/test requirements are satisfied.


## 2026-11-18 — Real Group A source delivery: #2 graph lifecycle and #59 signed agent receipt

Implemented source commit: `5b441e55ce0b22bc88144fbd22de317036491ae7`.
[Core Assurance run 44365112638](https://github.com/ArdaNTM/JAS/actions/runs/44365112638):
**2250 PASS / 14 SKIP**; 440-file Release Lock **PASS**
`sha256:ebcbd0f55845a04119563d976d72951dc506e85c763a8aba32417a4787041ad9`.
[Unified Acceptance run 44365112370](https://github.com/ArdaNTM/JAS/actions/runs/44365112370):
**10 E2E + 9 governance PASS**, with fail-closed
`A=9 B1=20 B2=88 COMPLETED=0 ELIGIBLE=0`.
[Remote Persistence 44365112329](https://github.com/ArdaNTM/JAS/actions/runs/44365112329):
**8 PASS** with actual PostgreSQL and MinIO services.

- **#2 implemented slice:** `memory/graph_store.py` now migrates old SQLite and
  PostgreSQL graph tables to support `deleted_at` tombstones; all bounded graph
  reads exclude tombstones. `graph_gateway.py` enrolls high-risk `graph_soft_delete`
  and `graph_restore` without installing any default allow policy. Exact
  `current_dispatch()` proof, PermissionEngine policy, consumed Owner-approval
  grant and principal-derived ownership protect both. Successful transitions
  are logged in a durable audit table in the same DB transaction. SQLite
  migration, replay, foreign scope, double-delete/restore and real PostgreSQL
  restore/audit pass. **Still absent:** complete authenticated user UI, retention
  policy, graph version cleanup and real Owner deployment acceptance.
- **#59 implemented slice:** existing `application/agent_credentials.py`
  already performed HMAC-SHA256 principal-bound request verification,
  TTL checks and durable SQLite nonce replay prevention **before** MCP Gateway.
  Do not duplicate or weaken it. `application/agent_mailbox.py` now supports
  separately provisioned broker-HMAC-signed consumption receipts, atomically
  written to persistent SQLite before the consumed messages are committed
  deleted. The receipt binds scoped principal, task, receiver principal,
  sender/recipient role, message ID, sequence, payload hash and consumption
  timestamp; tampering and cross-principal reads fail, and a fresh process
  can sign an ingress request accepted by the real Gateway. **Limitation:**
  broker-signed proof is not an independent receiver-signed receipt, actual
  transport identity guarantee, network listener or retry service. Those
  acceptance items remain open.
- The previous 7 other Group A complete feature scopes (#5, #40, #44, #47,
  #67, #73, #111) are **not fully implemented by this change**. External-source
  verification, scientific data provenance, authenticated UI/export and
  independent acceptance still require real evidence.

This is code and test evidence, not a `security_review=PASS` for full
capabilities. Preserve `TESTING` and the named missing components until
each real acceptance requirement is verified. No F2.7/main changes.


## 2026-11-18 — Focused implementation: #5 durable goal status, #40 archive-backed reports, #44 signed backup

**Implemented PR #158:** `e76ddc8ca5d7431add4dc4e9ed66419cac44ee79`.
[Core Assurance](https://github.com/ArdaNTM/JAS/actions/runs/44383040344):
**2253 PASS / 14 SKIP**, including three new focused tests and adversarial
cross-principal, signature-tamper, duplicate, limits and restart checks.
[Unified Acceptance](https://github.com/ArdaNTM/JAS/actions/runs/44383040278):
**10 E2E + 9 governance PASS**,
`A=9 B1=20 B2=88 COMPLETED=0 ELIGIBLE=0`.
440-file Release Lock PASS
`sha256:561336728ba0e9f7c1070e7339bb9c19d43ba9a350ff9e00c0efd501441bca3b`.

- **#5 real slice:** `application/task_state_machine.py` gains bounded
  principal-scoped `goal_progress` based only on actual persistent SQLite task
  `SUCCEEDED` outcomes. No model assertion can manufacture achievement,
  and a restarted process reads identical state. It does not bypass existing
  task runtime/Gateway rules. **Remaining:** authenticated UI/API, long-term
  goal creation/planning UX and Owner acceptance.
- **#40 real slice:** `research/report_authoring.py` adds a deterministic
  source-backed report builder joining actual digest-verified
  `SQLiteResearchArchive` snapshots and reviewed DOI metadata.
  It produces a valid DOCX and strictly rejects foreign-principal archives,
  unreviewed DOIs and invalid source lengths. Archived content remains
  explicitly untrusted: **no independent publisher authenticity, live
  source verification or authenticated download route is claimed**.
- **#44 real slice:** `research/archive.py` adds explicit-consent,
  principal-bound HMAC-SHA256 signed bounded JSON backup and atomic SQLite
  restore, with original content-id/hash validation. Tampered backups and
  attempts to cross principal scopes fail closed. **Security limitation:**
  HMAC authenticity/integrity does *not* encrypt archived private text.
  Owner key custody/rotation, UI, PDF formats, retention policy and validated
  end-to-end backup/restore still require independent acceptance.

These three features' real partial code and negative tests are recorded
without removing open implementation gaps or promoting `COMPLETED`.
The user's individual-completion policy is accepted; a feature may be
promoted independently once its **own** full acceptance gates are genuinely
closed. Existing #2/#59/#67/#111 incomplete full capabilities remain
`TESTING` as well; B1 and B2 unchanged.
