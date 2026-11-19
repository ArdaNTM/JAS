# AURA B2-Owner 17-feature bounded v1 acceptance — 2026-11-19

**Scope:** Original *technical_goal* only for 17 offline/permission-preserving primitives. No claim of full product, hardware, autonomous action or production acceptance.

**Owner integration evidence:** PR #64 merged to main `e9c68dd1269e42df1731eac4d4b8acbfa9675ca7`; PR #158 merged to main `b09ad74c49ebe1d73e2bb79524c8c8006e2ca40f`. Explicit Owner request authorizes B2-Owner bounded v1 review. PR #65 regression/hardening source `2ca63ca3c7892fa481e844ffd87e45f580bfd56f`, [Core Assurance 44450746726](https://github.com/ArdaNTM/JAS/actions/runs/44450746726) 2390 PASS/14 SKIP, canonical 440 Release Lock PASS. This is not a signed physical witness.

**Security boundary:** modules operate on local bounded, already-authorized in-memory inputs. Only authorized executions pass the existing MCP Gateway; restored original negative regressions uncovered seven fail-open Swarm cases, fixed at 2ca63ca3c7892fa481e844ffd87e45f580bfd56f. Full-product deficits are preserved verbatim in each feature's `known_limitations`.

| ID | Bounded v1 technical goal | Integrated source | Original pinned focused test |
|---:|---|---|---|
| 34 | Produce all-or-nothing exact-hash text operation previews and reversibility observations without touching files. | `core/src/aura_core/application/text_change_preview.py` | `core/tests/test_text_change_preview.py` |
| 46 | Find bounded static Python code review candidates without importing or executing inspected code. | `core/src/aura_core/application/offline_code_quality.py` | `core/tests/test_offline_code_quality.py` |
| 50 | Generate real runnable pytest cases from explicitly supplied JSON-safe function input/output contracts. | `core/src/aura_core/application/offline_code_quality.py` | `core/tests/test_offline_code_quality.py` |
| 58 | Validate the entire specialist swarm plan before any MCP tool dispatch. | `core/src/aura_core/application/swarm_orchestration.py` | `core/tests/test_swarm_plan_admission.py` |
| 61 | Bound specialist proposal concurrency with asyncio TaskGroup and controlled admission. | `core/src/aura_core/application/subsystem_pack2.py` | `tests/test_subsystem_pack2.py` |
| 64 | Adapt existing specialist-profile proposals to deterministic registered-provider health changes. | `core/src/aura_core/application/specialist_selection.py` | `tests/test_specialist_selection.py` |
| 68 | Numerically integrate bounded 1D mass-spring-damper motion via fourth-order Runge-Kutta. | `core/src/aura_core/application/physics_simulation.py` | `core/tests/test_physics_simulation.py` |
| 70 | Construct closed outward-oriented parametric box and cylinder triangle meshes in millimetre coordinates. | `core/src/aura_core/application/parametric_mesh.py` | `core/tests/test_parametric_mesh.py` |
| 71 | Evaluate a constrained analytical engineering model without physical actuation or tool privileges. | `core/src/aura_core/application/physics_simulation.py` | `core/tests/test_physics_simulation.py` |
| 72 | Deterministically allocate balanced simulated control/treatment unit labels with bounded sample counts. | `core/src/aura_core/application/experiment_design.py` | `core/tests/test_experiment_design.py` |
| 74 | Produce deterministic small watertight prototype shapes and in-memory binary STL. | `core/src/aura_core/application/parametric_mesh.py` | `core/tests/test_parametric_mesh.py` |
| 75 | Execute deterministic bounded local experiment batches using the existing safe-expression evaluator with SHA256 evidence. | `core/src/aura_core/application/subsystem_pack2.py` | `tests/test_subsystem_pack2.py` |
| 108 | Inspect bounded, previously authorized RFC822/MIME bytes as plain-text-only read-only previews. | `core/src/aura_core/application/offline_email.py` | `core/tests/test_offline_email_preview.py` |
| 109 | Parse already-authorized ICS VEVENT data into bounded UTC-aware read-only schedule observations. | `core/src/aura_core/application/ics_calendar.py` | `core/tests/test_offline_ics_calendar.py` |
| 110 | Inspect bounded PNG/GIF/WAV file headers and reject declared MIME mismatch without decoding media. | `core/src/aura_core/filesystem/media_header.py` | `core/tests/test_media_header_inspection.py` |
| 114 | Implement local bounded triangular mesh topology validation and binary STL serialization. | `core/src/aura_core/application/parametric_mesh.py` | `core/tests/test_parametric_mesh.py` |
| 117 | Render a bounded static Markdown summary of authorized scoped Swarm events without raw payloads. | `core/src/aura_core/application/action_history.py` | `core/tests/test_action_history_report.py` |

**Next stage:** Only B2-Env (71) remains TESTING. Run `core/scripts/b2_postmerge_check.py` after manually merging #65, on the Owner's actual Windows + Hyper-V Ubuntu + Docker lab with independent signed hardware receipts. The runner is a read-only gate, not an acceptance signer.
