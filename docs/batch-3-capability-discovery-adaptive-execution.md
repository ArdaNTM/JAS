# Batch 3: capability discovery, adaptive execution, proactive events

This batch adds composable Kernel-side primitives. It deliberately does not claim unrestricted self-modifying code or autonomous general intelligence.

## Dynamic capability discovery

`aura_core.application.capability_discovery.DynamicCapabilityDiscovery` accepts manifests from providers that are already connected by the host. It validates provider/tool identifiers, semantic versions, schema type and manifest size, then records proposals. A proposal is not a registered capability until an explicit approval call is made.

Approval registers metadata through the existing `CapabilityRegistry`. It does not install packages, import Python modules, connect an arbitrary endpoint, grant permission, or dispatch a tool. The host must still register/validate the provider, map the approved tool to a supported operation, and rely on `MCPGateway` + `PermissionEngine` for each execution. New provider code should be isolated and versioned, not downloaded and executed from discovery metadata.

## Bounded adaptive execution

`AdaptiveExecutionController` is a deterministic recovery policy. It allows at most one replan by default, stops immediately when authorization is denied, never retries a side-effecting failure automatically, and stops when the recovery budget is exhausted. It returns a decision; the orchestrator must submit any permitted follow-up as a new governed task through `AgentTaskService`.

## Proactive event observation

`ProactiveEventObserver` converts a small allow-list of Kernel events into reviewable suggestions. It does not execute actions, trust arbitrary event payloads as instructions, or poll external services. A future scheduler/connector can feed validated events into the Kernel EventBus; any resulting tool action must still require a task, policy evaluation and Gateway dispatch.

## Memory and context

AURA already has an optional `ChatMemory` path in the API. Enablement remains controlled by `AURA_CHAT_MEMORY_ENABLED=1`. Before treating memory as durable user profile, add explicit retention/deletion controls, scope isolation, provenance, TTL and tests for prompt-injection-resistant retrieval. This batch does not silently persist new personal facts.

## Suggested next integration steps

1. Wire a host-owned `DynamicCapabilityDiscovery` instance to MCP provider lifecycle events, keeping proposals pending until approval.
2. Expose proposal/approval APIs only after an authenticated principal/permission policy is defined.
3. Let the orchestrator consume `AdaptiveExecutionController` decisions while persisting a bounded execution trace; never let an LLM directly alter gateway policy.
4. Add a scheduled event source with explicit opt-in, deduplication, rate limits and a review queue before proactive notifications.
5. Add memory lifecycle APIs and user-visible retention controls before enabling durable memory by default.
