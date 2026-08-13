# JARVIS Architecture Specification (JAS)

---

Document ID:
JAS-0407

Document Name:
CONTEXT MANAGER

Version:
1.0.0

Status:
APPROVED

Classification:
KERNEL

Depends On:

- PROJECT_VISION
- CORE_PRINCIPLES
- SYSTEM_REQUIREMENTS
- GLOBAL_ARCHITECTURE
- KERNEL_ARCHITECTURE
- KERNEL_COMPONENT_MODEL
- KERNEL_LIFECYCLE
- EVENT_BUS
- SERVICE_REGISTRY
- CAPABILITY_REGISTRY
- ADR-0001
- ADR-0002
- ADR-0003
- ADR-0004

---

# 1. Purpose

The Context Manager is responsible for maintaining all runtime context inside JARVIS.

It provides a consistent execution context for every request, task, event, agent and capability invocation.

---

# 2. Objectives

The Context Manager SHALL provide:

- execution context
- request context
- session context
- user context
- task context
- agent context
- security context
- trace context

---

# 3. Context Definition

A Context represents all information required to correctly execute an operation.

A Context SHALL NOT represent long-term memory.

Long-term knowledge belongs to the Memory subsystem.

---

# 4. Context Scope

The Context Manager SHALL maintain:

Request Context

Task Context

Conversation Context

Execution Context

Agent Context

Plugin Context

MCP Context

Security Context

Future versions MAY introduce additional scopes.

---

# 5. Context Contents

A Context MAY contain:

Context ID

Session ID

Correlation ID

Parent Context

Creation Time

Expiration Time

Origin

Current User

Current Agent

Current Capability

Permissions

Priority

Metadata

---

# 6. Context Lifecycle

Every Context SHALL follow:

Created

↓

Active

↓

Updated

↓

Completed

↓

Archived

↓

Disposed

---

# 7. Context Propagation

Child operations SHALL inherit their parent context unless explicitly overridden.

Context propagation SHALL preserve:

- session identity
- correlation identifiers
- security information
- execution scope

---

# 8. Isolation

Contexts SHALL remain isolated.

No running task may directly modify another task's context.

Shared mutable context is prohibited.

---

# 9. Context Resolution

When multiple context sources exist, priority SHALL be:

Security

↓

Session

↓

Request

↓

Task

↓

Agent

↓

Capability

↓

Metadata

---

# 10. Context Expiration

Expired contexts SHALL become unavailable for execution.

Expired contexts MAY be archived for diagnostics.

---

# 11. Thread Safety

The Context Manager SHALL support concurrent execution.

Context operations SHALL remain thread-safe.

No global mutable context SHALL exist.

---

# 12. Event Integration

The Event Bus SHALL attach Context IDs to every event whenever applicable.

This enables end-to-end traceability.

---

# 13. Security

Security context SHALL remain immutable during execution unless explicitly updated by the Permission Engine.

Sensitive context fields SHALL be protected.

---

# 14. Performance Requirements

The Context Manager SHALL provide:

constant-time context lookup where practical

minimal allocation overhead

efficient propagation

safe concurrent access

---

# 15. Future Evolution

Future versions MAY support:

distributed context propagation

cross-device sessions

persistent execution contexts

checkpoint restoration

runtime snapshots

---

# 16. Compliance Requirements

Every executable operation SHALL execute inside a valid Context.

Subsystems SHALL NOT create private context systems.

Context propagation SHALL use Kernel interfaces only.

---

# 17. Success Criteria

The Context Manager is complete when:

every execution has a Context

context propagation is deterministic

contexts remain isolated

security information is preserved

traceability is maintained

---

END OF DOCUMENT