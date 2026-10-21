# Batch 11 — Ultimate JARVIS Orchestration

## Goal

Join existing AURA capabilities through an observable, bounded orchestration layer without turning the model into an authority. JAS remains the architecture/version-governance source. AURA remains provider-agnostic and capability-driven; the deterministic Kernel, registries, Permission Engine, EventBus, and MCP Gateway remain authoritative boundaries.

## Staged architecture

1. **Event-driven proactivity (first slice).** An opt-in coordinator subscribes only to allow-listed Kernel events. Events are wake-up signals, not instructions. It may invoke only the existing idle reflection daemon, which performs bounded, principal-scoped memory recall and persists deduplicated review-required proposals. Duplicate events, concurrent cycles, and repeated wakeups are bounded; errors and cycle counters are observable. Stop removes subscriptions.
2. **Autonomous task loop.** Add a persisted operation state machine (queued → planning → awaiting/authorized → experimenting → verifying → completed/failed/cancelled), a bounded DAG planner, deadlines and cancellation, per-step event traces, and an operator-visible status API. Every capability execution must be re-authorized at execution time and routed through AgentTaskService → AgentExecutor → MCPGateway → Permission Engine. Sandbox experiments stay isolated and separately authorized. Model output, tool output, memory, screenshots, and transcripts are untrusted data.
3. **Learning and skill proposals.** Reflexion retries remain capped and verifier-driven. Only verified candidates may be proposed; skills remain pending_review until explicit human approval. No autonomous permission changes, silent skill promotion, or unreviewed code execution.
4. **Multimodal full-duplex.** Introduce provider-neutral audio-stream and vision capabilities, bounded frame sampling, VAD/interruption events, cancellable TTS playback, and a session state machine (listening/thinking/speaking/interrupted). Screen capture must be explicitly enabled and scoped; screenshots and transcripts never grant permissions. Tool actions still use the Gateway.
5. **Operations and governance.** Expose queue depth, cycle/task status, cancellation, audit correlation IDs, rate limits, quiet hours, resource budgets, and fail-closed behavior. JAS version locks and ADRs govern provider and runtime compatibility.

## Security invariants

- Provider/model choice is an implementation detail; Ollama/Qwen3 is a local inference baseline, not AURA itself.
- An EventBus event can wake a pre-approved workflow but cannot supply authority or arbitrary executable instructions.
- No event handler calls a provider tool directly. Real tool execution goes through MCP Gateway and Permission Engine.
- Background thinking may read bounded, principal-scoped memories and write review-required proposals only.
- Every autonomous loop has an explicit opt-in, allow-listed event types, bounded retries/work, cooldown, cancellation/shutdown, and observable outcomes.
- User approval remains required for skill promotion and any high-impact or irreversible action.

## First implementation slice

EventDrivenOrchestrationCoordinator subscribes to a small explicit event allow-list and invokes only IdleMemoryReflectionDaemon.run_once(). It is disabled by default, deduplicates recently seen event IDs, serializes cycles, applies cooldown, contains reflection errors, and exposes a status snapshot. It does not create task plans, call inference, or execute tools. API lifecycle wiring and the task-loop state machine are subsequent increments.
