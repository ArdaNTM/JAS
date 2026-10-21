# AURA learning architecture: bounded autonomy toward Ultimate JARVIS

## Research basis

- Shinn et al., **Reflexion: Language Agents with Verbal Reinforcement Learning** (2023), https://arxiv.org/abs/2303.11366. Use environment feedback and textual reflection stored in episodic memory; this does not require model-weight updates.
- Wang et al., **Voyager: An Open-Ended Embodied Agent with Large Language Models** (2023), https://arxiv.org/abs/2305.16291. Combine exploration/curriculum, executable skill library, and iterative improvement from environment feedback.
- Park et al., **Generative Agents: Interactive Simulacra of Human Behavior** (2023), https://arxiv.org/abs/2304.03442. Record observations, synthesize higher-level reflections, and retrieve relevant memories for later planning.
- Packer et al., **MemGPT: Towards LLMs as Operating Systems** (2023), https://arxiv.org/abs/2310.08560. Manage a bounded context window over multiple memory tiers.
- Yang et al., **SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering** (NeurIPS 2024), https://arxiv.org/abs/2405.15793. A well-designed, constrained agent-computer interface is part of agent capability, not an incidental detail.

These papers support architectural patterns, not a claim of general intelligence or guaranteed self-improvement. Benchmark outcomes are task-specific and should not be read as evidence that AURA will attain equivalent results.

## Implemented in this increment

- `core/src/aura_core/application/reflexion.py` provides a bounded Reflexion-style orchestration primitive.
- `core/src/aura_core/application/reflexion_inference.py` adapts the provider-neutral `InferenceService.infer(InferenceRequest)` contract into a model-backed draft reviser. It bounds tokens and output, treats sandbox diagnostics as untrusted data, exposes no tools, and rejects fenced/oversized output. Wire it as the `revise` callback to `ReflexionExperimentLoop`; sandbox authorization and independent verification remain separate required dependencies.
- `core/src/aura_core/application/persona_policy.py` defines configurable style, language, humor, initiative threshold, quiet hours, opt-in, and daily suggestion budgets. It returns presentation guidance and a pure initiative gate; it is not an authorization mechanism.
- Each experiment attempt constructs a distinct job and passes through the sandbox adapter with authorization checked again for that attempt.
- `ExperimentBudget` caps retries to at most three and bounds total wall-clock budget.
- Failed execution/verifier feedback is stored as untrusted episodic data. It is diagnostic input, never policy or permission.
- A successful run is not automatically trusted: a separate verifier must return true before a skill candidate is written.
- `ProceduralSkillLibrary` persists candidates with principal/task scope, evidence, and a `pending_review` status. This increment does not auto-approve or auto-execute stored skills.
- Tests cover retry bounds, authorization denial, untrusted lesson persistence, and review-gated skill proposals.

## Deliberately not claimed yet

- The Reflexion primitive is not yet connected to a live model-backed revision callback or exposed as an end-user endpoint. The host application must supply a revision function, an independent verifier, and an authorizer backed by the Permission Engine. Do not provide a callback that bypasses the MCP Gateway for actual tool calls.
- The procedural skill library currently stores proposals; it is not yet a general capability registry and must not be treated as executable authority.
- Background reflection now proposes lexical links plus heuristic repeated-lesson and possible-contradiction candidates, with source-memory IDs, stable deduplication, explicit untrusted status, and review-required metadata. This is a transparent heuristic—not model-confirmed semantic truth. Confidence calibration, retention/forgetting, and full review/decision APIs remain future work.
- Dynamic persona is implemented as a configurable policy object, but has not been wired into every response-generation path or persisted through a settings API yet. Callers must apply `system_style_prompt()` as presentation-only guidance and use `may_suggest_initiative()` only to gate suggestions. Never use persona to authorize action.
- This code has been committed to the feature branch, but the new tests have not been executed in the repository environment in this session.

## Integration notes and limitations

- `POST /api/autonomy/reflexion` now wires the configured `InferenceService` into the model-backed revision adapter and runs bounded attempts through `AsyncWorkCoordinator`, a fresh Permission Engine decision per sandbox attempt, and the isolated Docker runner. It requires `expected_stdout` for independent exact-output verification; without that acceptance criterion it cannot promote a skill candidate. Model output is untrusted and all proposed skills remain pending review.
- The persona policy is appended to the main `/api/assistant/respond` system prompt as presentation-only guidance. `GET/PUT /api/jarvis/persona` exposes local settings; updates are process-lifetime only (not durable yet). Initiative policy may propose a next step, never execute it by itself.
- The new test file covers model adapter contract, bounds, persona gating, and heuristic consolidation. Tests/builds must be run against the final branch head before treating this increment as verified.

## API integration

- `POST /api/autonomy/reflexion`: local-client-only; requires the Permission Engine to be available and allow the high-risk `sandbox.python.execute` capability for each attempt. Uses the configured inference provider/model, bounded retry and time budgets, isolated Docker, and exact expected-stdout verification. No MCP tools are exposed to the reviser or sandbox. The endpoint reports `mcp_tool_execution_performed: false` and separately indicates whether sandbox code ran; sandbox execution is not the same as an MCP tool invocation.
- `GET /api/jarvis/persona` and `PUT /api/jarvis/persona`: local-only style/initiative preferences. Initiative remains disabled by default; the persona policy never replaces authorization.

## Recommended next phases

1. **Strengthen experiment verification:** add structured test-suite/acceptance-check support beyond exact expected stdout, and preserve per-attempt authorization audit records.
2. **Skill lifecycle:** add review/approve/reject APIs, immutable versioning, provenance, dependency declarations, regression tests, revocation, and invocation through registered capabilities only.
3. **Memory consolidation:** produce reviewable lesson candidates from task outcomes and repeated evidence. Keep source episode references; do not elevate a lesson to a trusted system instruction.
4. **Proactive autonomy:** add an opt-in scheduler with user-defined goals, quiet hours, budget, cancellation, and per-capability policy checks. It should propose or execute only actions already authorized by policy.
5. **Persona:** persist settings durably and connect initiative suggestions to user-reviewed event/goal workflows, with factuality, safety, privacy, quiet hours, budgets, and approval rules taking precedence.
6. **Evaluation:** use task-specific regression suites, held-out tasks, repeated trials, cost/latency measures, false-success rates, permission-denial tests, and adversarial prompt-injection cases. No learned skill should be promoted based only on a model's self-assessment.

## Security invariants

- JAS remains architecture/version-governance source; AURA Core remains the deterministic Kernel with service/capability/provider registries, Permission Engine, and EventBus.
- Every real MCP tool invocation remains behind MCP Gateway authorization.
- Model output, sandbox output, memory text, reflections, and skill candidates are untrusted data.
- No automatic privilege escalation, arbitrary host execution, network-enabled sandbox, or implicit skill promotion.
- A user opt-in, task budget, and cancellation path are required for proactive background work.
