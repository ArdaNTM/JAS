# 35 — EXTERNAL INTEGRATION AND MCP GOVERNANCE ARCHITECTURE

**Project:** AURA / JAS  
**Document Class:** Approved Stack Architecture Specification  
**Document ID:** 35  
**Status:** APPROVED  
**Authority:** JAS Architecture Governance  
**Scope:** External Integrations, MCP Providers, External Tools and Services  
**Depends On:**  
- 07_MCP
- 08_PLUGINS
- 16_SECURITY
- 17_BOOTSTRAP
- 19_APPROVED_STACK
- 26_VERSION_LOCK
- 27_MANIFEST
- 28_BOOTSTRAP
- 29_SYSTEM_VERIFICATION
- 30_JARVIS_CORE_ARCHITECTURE
- 31_AGENT_RUNTIME_AND_EXECUTION_ARCHITECTURE
- 32_CAPABILITY_AND_PERMISSION_ARCHITECTURE
- 33_[previous governance specification]
- 34_POLICY_CONTRACT_AND_AUTHORIZATION_SCHEMA

---

## 1. PURPOSE

This document defines the governance architecture used by AURA for interaction with external systems.

External systems include, but are not limited to:

- MCP servers
- external APIs
- browser automation providers
- filesystem providers
- Git providers
- GitHub services
- Docker services
- databases
- cloud services
- communication platforms
- email systems
- calendar systems
- search providers
- local operating-system services
- third-party plugins exposing external capabilities
- remote execution services

The purpose of this architecture is to ensure that AURA can interact with external systems while maintaining:

1. explicit authorization,
2. capability isolation,
3. least-privilege access,
4. provider trust,
5. execution policy enforcement,
6. credential protection,
7. auditability,
8. version compatibility,
9. revocation,
10. failure containment,
11. deterministic governance.

External integrations MUST NOT bypass the AURA authorization architecture.

---

# 2. GOVERNING PRINCIPLE

AURA MUST treat every external integration as an untrusted or conditionally trusted capability provider.

The fact that a provider is technically available MUST NOT imply that an agent may execute its operations.

The execution chain MUST conceptually follow:

```text
Agent
  ↓
Intent
  ↓
Capability Request
  ↓
Authorization Policy
  ↓
Provider Selection
  ↓
Operation Admission
  ↓
Execution Context
  ↓
External Provider
  ↓
Result Validation
  ↓
Audit / Provenance
  ↓
Agent
```

No external operation may skip the authorization and admission stages.

---

# 3. EXTERNAL INTEGRATION MODEL

Every external integration MUST be represented as an integration object.

A conceptual integration object contains:

```text
Integration
├── identity
├── provider
├── protocol
├── capabilities
├── operations
├── trust
├── permissions
├── credentials
├── constraints
├── compatibility
├── lifecycle
├── health
├── audit
└── revocation
```

The integration object is the governance boundary between AURA and the external system.

---

# 4. INTEGRATION IDENTITY

Every registered integration MUST have a stable identity.

The identity MUST include, where applicable:

- integration identifier,
- provider identifier,
- protocol,
- implementation identity,
- version,
- source,
- registration timestamp,
- integrity information,
- trust state.

Example:

```yaml
integration:
  id: github.mcp
  provider: github
  protocol: mcp
  version: pinned
  trust_state: verified
```

The identity MUST be independent of the agent requesting the integration.

---

# 5. PROVIDER MODEL

A provider is the concrete system responsible for exposing external capabilities.

Providers may be:

- local,
- remote,
- containerized,
- process-based,
- network-based,
- plugin-backed,
- MCP-based,
- API-backed.

A provider MUST have a lifecycle.

```text
DISCOVERED
    ↓
REGISTERED
    ↓
VERIFIED
    ↓
ADMITTED
    ↓
ACTIVE
    ↓
SUSPENDED
    ↓
REVOKED
```

A provider in `REVOKED` state MUST NOT execute operations.

---

# 6. MCP PROVIDERS

MCP providers are treated as external capability providers.

AURA MUST NOT assume that an MCP server is trusted merely because it conforms to the MCP protocol.

MCP protocol compliance establishes interoperability.

It does not establish authorization.

Therefore:

```text
MCP Compliance ≠ AURA Trust
```

An MCP provider MUST independently pass AURA's registration, compatibility, security and authorization requirements.

---

# 7. PROVIDER REGISTRATION

Before becoming executable, an external provider MUST be registered.

Registration MUST establish:

- provider identity,
- protocol,
- source,
- version,
- capabilities,
- operations,
- required permissions,
- required credentials,
- resource requirements,
- security classification,
- compatibility status.

Registration MUST NOT automatically grant execution privileges.

---

# 8. PROVIDER VERIFICATION

Providers MUST undergo verification before admission.

Verification MAY include:

- identity verification,
- source verification,
- integrity verification,
- version verification,
- manifest verification,
- dependency verification,
- capability inspection,
- permission inspection,
- network requirement inspection,
- credential requirement inspection,
- sandbox compatibility,
- security policy compatibility.

Verification status MUST be recorded.

---

# 9. TRUST MODEL

AURA MUST maintain an explicit provider trust state.

A conceptual trust model is:

```text
UNKNOWN
   ↓
DISCOVERED
   ↓
INSPECTED
   ↓
VERIFIED
   ↓
TRUSTED
```

Trust MUST NOT be inferred from provider popularity alone.

Trust MAY be reduced or revoked if:

- integrity changes,
- version changes,
- behavior violates policy,
- unexpected capabilities appear,
- security requirements change,
- credentials are compromised,
- compatibility is lost.

---

# 10. CAPABILITY DISCOVERY

AURA MAY discover capabilities exposed by an external provider.

Discovered capabilities MUST be treated as metadata until admitted.

The discovery process MUST NOT automatically authorize execution.

Conceptually:

```text
Discovery
   ↓
Capability Description
   ↓
Policy Evaluation
   ↓
Admission
   ↓
Execution Availability
```

This prevents dynamic discovery from becoming implicit privilege escalation.

---

# 11. OPERATION DISCOVERY

Each provider operation MUST be individually identifiable.

An operation SHOULD contain:

```text
operation_id
provider_id
capability_id
input_schema
output_schema
required_permissions
risk_class
resource_requirements
network_requirements
credential_requirements
```

Operations MUST be evaluated independently where their security impact differs.

For example:

```text
github.read_repository
```

and

```text
github.delete_repository
```

MUST NOT inherit identical authorization merely because both belong to the same provider.

---

# 12. CAPABILITY-TO-PERMISSION BINDING

Every executable external capability MUST resolve to one or more permissions.

Conceptually:

```text
Capability
    ↓
Operation
    ↓
Permission Set
    ↓
Policy
    ↓
Decision
```

An operation without a valid permission mapping MUST be denied.

---

# 13. LEAST PRIVILEGE

External integrations MUST operate under least privilege.

A provider MUST receive only the permissions required for the current operation.

AURA SHOULD prefer:

```text
operation-scoped permission
```

over:

```text
provider-wide permission
```

and:

```text
task-scoped credential
```

over:

```text
permanent unrestricted credential
```

---

# 14. AGENT ACCESS

Agents MUST NOT directly obtain unrestricted external-provider access.

Agents request capabilities through the AURA execution architecture.

The agent therefore requests:

```text
"I need capability X for task Y."
```

rather than:

```text
"Give me unrestricted access to provider Z."
```

The authorization engine determines whether the request is permitted.

---

# 15. USER AUTHORIZATION

Operations requiring explicit user authorization MUST be interruptible before execution.

Examples may include:

- sending an email,
- deleting data,
- purchasing an item,
- modifying external accounts,
- publishing content,
- executing destructive commands,
- changing system configuration,
- granting persistent permissions.

The authorization state MUST be explicit.

Possible states:

```text
NOT_REQUIRED
REQUIRED
APPROVED
DENIED
EXPIRED
REVOKED
```

---

# 16. HIGH-RISK OPERATIONS

External operations SHOULD be assigned risk classifications.

Example:

```text
LOW
MEDIUM
HIGH
CRITICAL
```

Typical characteristics:

### LOW

Read-only, non-sensitive operations.

### MEDIUM

Operations modifying non-critical local or external state.

### HIGH

Operations involving sensitive information, credentials, external communication or important system state.

### CRITICAL

Operations involving destructive actions, privileged execution, irreversible changes or significant security impact.

Risk classification MUST influence authorization requirements.

---

# 17. DESTRUCTIVE OPERATIONS

Destructive operations MUST NOT be implicitly authorized.

Examples include:

- deletion,
- credential revocation,
- account modification,
- repository destruction,
- database destruction,
- bulk file deletion,
- infrastructure destruction.

AURA SHOULD require explicit confirmation when policy defines the operation as destructive.

---

# 18. CREDENTIAL GOVERNANCE

External credentials MUST be separated from agent reasoning state.

Credentials MUST NOT be treated as ordinary context.

The architecture MUST prevent credentials from being unnecessarily exposed to:

- agents,
- prompts,
- logs,
- memory,
- model context,
- generated artifacts.

Credential access MUST be mediated by the security layer.

---

# 19. SECRET INJECTION

Where possible, credentials SHOULD be injected only at execution time.

Conceptually:

```text
Agent
  ↓
Authorized Operation
  ↓
Credential Broker
  ↓
External Provider
```

The agent SHOULD receive the result of an authenticated operation rather than the underlying secret.

---

# 20. CREDENTIAL SCOPE

Credentials SHOULD be scoped according to:

- provider,
- operation,
- resource,
- task,
- lifetime.

Long-lived unrestricted credentials SHOULD be avoided.

Credential scope MUST be compatible with the permission model defined in document 34.

---

# 21. NETWORK GOVERNANCE

External integrations requiring network access MUST declare their network requirements.

A provider SHOULD specify:

```text
network_required
allowed_domains
allowed_protocols
allowed_ports
proxy_requirements
```

Network access MUST be constrained where the runtime supports such controls.

---

# 22. DATA FLOW GOVERNANCE

AURA MUST consider the direction of data movement.

Important flows include:

```text
AURA → External Provider
External Provider → AURA
Agent → External Provider
External Provider → Agent
External Provider → Memory
```

Sensitive data MUST NOT be transmitted externally unless permitted by policy.

---

# 23. DATA CLASSIFICATION

External data transfers SHOULD respect AURA data classifications.

Conceptual classes:

```text
PUBLIC
INTERNAL
SENSITIVE
SECRET
RESTRICTED
```

Policy MAY prohibit particular classes from being transmitted to particular providers.

Example:

```text
SECRET → external provider = DENY
```

unless explicitly authorized by a stronger policy.

---

# 24. MCP SESSION GOVERNANCE

MCP sessions MUST have an explicit lifecycle.

```text
CREATED
  ↓
AUTHENTICATED
  ↓
AUTHORIZED
  ↓
ACTIVE
  ↓
IDLE
  ↓
CLOSED
```

Sessions MUST NOT remain active indefinitely without policy justification.

---

# 25. MCP CONNECTION GOVERNANCE

Connections MUST be associated with:

- provider identity,
- session identity,
- authorization context,
- execution context,
- lifecycle state.

A connection MUST NOT become a permanent authorization channel.

---

# 26. TOOL ADMISSION

An external tool MUST pass admission before becoming executable.

Admission SHOULD evaluate:

1. provider trust,
2. operation identity,
3. permission requirements,
4. risk classification,
5. compatibility,
6. credential requirements,
7. execution environment,
8. policy constraints.

Conceptually:

```text
Tool Discovered
      ↓
Tool Inspected
      ↓
Tool Verified
      ↓
Policy Evaluation
      ↓
ADMIT / DENY
```

---

# 27. DYNAMIC TOOLS

Dynamically discovered tools MUST NOT bypass static governance.

If a provider exposes a new operation after registration:

```text
Existing Provider
       ↓
New Operation
       ↓
Re-evaluation
       ↓
Admission
```

The newly discovered operation MUST NOT automatically inherit execution authorization.

---

# 28. TOOL SCHEMA VALIDATION

External tool input MUST be validated before execution.

Validation SHOULD include:

- schema validation,
- type validation,
- required-field validation,
- range validation,
- path validation,
- resource validation,
- policy validation.

Malformed or policy-invalid input MUST be rejected before reaching the provider.

---

# 29. OUTPUT VALIDATION

External provider output MUST be treated as external data.

AURA MUST NOT assume that external output is trustworthy instructions.

External output MAY contain:

- data,
- errors,
- instructions,
- malicious content,
- prompt injection,
- unexpected structures.

Therefore:

```text
External Output ≠ Trusted Instruction
```

Output MUST pass through the appropriate validation and interpretation layer before influencing agent execution.

---

# 30. PROMPT-INJECTION RESISTANCE

External providers and external content MUST be considered potential prompt-injection sources.

Examples include:

- webpages,
- emails,
- documents,
- repository files,
- issue descriptions,
- API responses,
- MCP tool results.

External content MUST NOT automatically override:

- system policy,
- security policy,
- user authorization,
- execution constraints.

---

# 31. PROVIDER ISOLATION

Where technically feasible, external providers SHOULD execute within an isolated environment.

Possible isolation mechanisms include:

- containers,
- process isolation,
- restricted filesystem access,
- restricted network access,
- separate credentials,
- resource quotas.

Isolation level MUST correspond to provider risk.

---

# 32. RESOURCE GOVERNANCE

External providers MUST be subject to resource constraints where appropriate.

Resources may include:

- CPU,
- memory,
- GPU,
- disk,
- network,
- execution time,
- subprocess count.

A provider MUST NOT be permitted to consume unlimited resources merely because an agent requested it.

---

# 33. TIMEOUTS

External operations MUST support execution time limits where technically feasible.

Timeout behavior SHOULD be:

```text
Running
  ↓
Timeout
  ↓
Cancellation
  ↓
Cleanup
  ↓
Result = TIMEOUT
```

A timeout MUST NOT leave uncontrolled execution behind.

---

# 34. FAILURE CONTAINMENT

Provider failure MUST remain isolated from the AURA kernel whenever possible.

Provider failures include:

- crashes,
- unavailable services,
- malformed responses,
- authentication failure,
- network failure,
- protocol errors,
- timeout,
- resource exhaustion.

Failure MUST be represented as a controlled execution result.

---

# 35. RETRY POLICY

Retries MUST be policy-controlled.

AURA MUST distinguish between:

```text
safe-to-retry
```

and:

```text
unsafe-to-retry
```

Read operations may often be retried.

Non-idempotent operations MUST NOT be blindly retried.

---

# 36. IDEMPOTENCY

External operations SHOULD declare whether they are idempotent.

Example:

```yaml
operation:
  id: github.read_repository
  idempotent: true
```

versus:

```yaml
operation:
  id: github.create_release
  idempotent: false
```

Retry behavior MUST respect this property.

---

# 37. REVOCATION

AURA MUST support provider and capability revocation.

Revocation MAY occur because of:

- security incidents,
- provider compromise,
- credential compromise,
- integrity mismatch,
- policy changes,
- incompatibility,
- user request.

Revocation MUST take precedence over normal execution authorization.

---

# 38. EMERGENCY DISABLE

The system MUST support emergency disabling of an integration.

Conceptually:

```text
Provider
   ↓
EMERGENCY DISABLE
   ↓
All new operations DENIED
   ↓
Active operations handled according to shutdown policy
```

Emergency disable SHOULD be available without modifying the provider itself.

---

# 39. AUDITABILITY

Every externally meaningful operation SHOULD produce an audit record.

The audit record SHOULD include:

```text
timestamp
agent_id
task_id
execution_id
provider_id
operation_id
capability_id
authorization_decision
risk_class
result_state
error_state
resource_usage
```

Secrets MUST NOT be written into audit logs.

---

# 40. PROVENANCE

External results SHOULD maintain provenance information.

Provenance SHOULD allow AURA to determine:

```text
Where did this data come from?
Which provider produced it?
Which operation produced it?
Under which execution context?
When was it obtained?
```

This is important for research, memory, debugging and security.

---

# 41. EXTERNAL DATA → MEMORY

External data MUST NOT automatically become persistent memory.

The memory layer MUST apply its own admission and classification rules.

Conceptually:

```text
External Result
      ↓
Validation
      ↓
Provenance
      ↓
Memory Policy
      ↓
Persist / Reject
```

This prevents arbitrary external content from contaminating persistent memory.

---

# 42. VERSION GOVERNANCE

External providers MUST be compatible with the locked AURA environment.

Relevant version dimensions include:

- provider version,
- protocol version,
- API version,
- SDK version,
- runtime version,
- dependency versions.

Version decisions MUST follow the Version Lock architecture.

A provider MUST NOT silently upgrade itself outside the defined update policy.

---

# 43. COMPATIBILITY

Before activation, an external integration MUST satisfy required compatibility constraints.

Compatibility MAY include:

```text
OS
Runtime
Python
Node
MCP
API
Dependency
Container
GPU
Security
Credential
```

An incompatible provider MUST NOT be activated merely because installation succeeded.

---

# 44. MANIFEST INTEGRATION

External integrations MUST be represented in the AURA manifest when they form part of the controlled runtime.

The manifest SHOULD establish:

- identity,
- version,
- source,
- integrity,
- dependencies,
- execution mode,
- required permissions,
- compatibility constraints.

The manifest therefore defines what is expected.

The runtime verification system determines what is actually present.

---

# 45. BOOTSTRAP INTEGRATION

Bootstrap MUST distinguish between:

```text
installed
```

and:

```text
verified and admitted
```

An external provider may be installed but remain inactive until verification and authorization succeed.

Conceptually:

```text
Bootstrap
   ↓
Discover
   ↓
Verify
   ↓
Register
   ↓
Authorize
   ↓
Activate
```

---

# 46. HEALTH MONITORING

Active external providers SHOULD expose health information where technically possible.

Health states MAY include:

```text
HEALTHY
DEGRADED
UNAVAILABLE
FAILED
QUARANTINED
REVOKED
```

Health failure SHOULD influence provider selection.

---

# 47. PROVIDER SELECTION

When multiple providers can perform the same capability, AURA MAY select between them.

Selection SHOULD consider:

- authorization,
- trust,
- health,
- compatibility,
- latency,
- resource cost,
- capability completeness,
- reliability,
- policy.

The cheapest or fastest provider MUST NOT automatically win if it violates a stronger policy constraint.

---

# 48. FALLBACK PROVIDERS

Fallback providers MAY be configured.

Fallback selection MUST preserve the original security requirements.

Example:

```text
Primary Provider
      ↓
Failure
      ↓
Fallback Provider
      ↓
Same Required Policy
```

Fallback MUST NOT be used to circumvent authorization.

---

# 49. EXTERNAL INTEGRATION LIFECYCLE

The complete lifecycle is:

```text
DISCOVERY
    ↓
REGISTRATION
    ↓
INSPECTION
    ↓
VERIFICATION
    ↓
COMPATIBILITY CHECK
    ↓
POLICY EVALUATION
    ↓
ADMISSION
    ↓
ACTIVATION
    ↓
EXECUTION
    ↓
MONITORING
    ↓
UPDATE / REVALIDATION
    ↓
SUSPENSION / REVOCATION
```

Every transition MUST be governed.

---

# 50. POLICY PRECEDENCE

When policies conflict, the stronger security restriction MUST prevail.

Conceptually:

```text
Emergency Security Policy
        >
System Security Policy
        >
Authorization Policy
        >
Capability Policy
        >
Provider Policy
        >
Agent Request
```

An agent request MUST never override a higher-level restriction.

---

# 51. PLUGIN INTERACTION

Plugins exposing external capabilities MUST use the same governance principles.

A plugin MUST NOT create an uncontrolled path around MCP or the authorization engine.

The conceptual relationship is:

```text
Plugin
   ↓
Capability
   ↓
Authorization
   ↓
External Integration
   ↓
Provider
```

---

# 52. BROWSER INTEGRATION

Browser automation is treated as an external interaction surface.

Browser capabilities MUST be subject to:

- domain restrictions,
- navigation policies,
- download policies,
- credential policies,
- file upload policies,
- external communication policies,
- destructive action policies.

A browser agent MUST NOT automatically receive unrestricted access to the user's authenticated sessions.

---

# 53. FILESYSTEM INTEGRATION

Filesystem providers MUST operate within explicit path boundaries.

Policies SHOULD define:

```text
allowed_paths
denied_paths
read_allowed
write_allowed
delete_allowed
execute_allowed
```

System-critical directories SHOULD remain protected.

---

# 54. CODE AND TERMINAL INTEGRATION

Code execution and terminal providers MUST be treated as high-risk capabilities.

They SHOULD operate under:

- command restrictions,
- working-directory restrictions,
- environment restrictions,
- network restrictions,
- process limits,
- timeout limits,
- resource quotas.

The agent MUST NOT receive unrestricted operating-system authority by default.

---

# 55. DATABASE INTEGRATION

Database integrations MUST distinguish between:

```text
READ
WRITE
UPDATE
DELETE
SCHEMA
ADMIN
```

permissions.

Read-only access SHOULD be the default for research and inspection tasks.

Destructive database operations MUST require stronger authorization.

---

# 56. COMMUNICATION INTEGRATIONS

Email, messaging and notification providers MUST distinguish between:

```text
READ
DRAFT
SEND
DELETE
MODIFY
ADMIN
```

The ability to read communication MUST NOT automatically imply permission to send communication.

---

# 57. EXTERNAL SERVICE ACTIONS

Actions affecting third-party systems MUST be considered state-changing operations.

Examples:

- publishing,
- purchasing,
- booking,
- sending,
- deleting,
- modifying,
- deploying.

These operations SHOULD receive stronger policy evaluation than read-only operations.

---

# 58. HUMAN-IN-THE-LOOP

Human authorization MUST remain available for operations whose risk exceeds the autonomous execution threshold.

The system SHOULD provide enough information for an informed decision:

```text
requested action
target
provider
risk
data involved
expected effect
reversibility
```

The confirmation MUST apply to the actual operation being executed.

---

# 59. AUTHORIZATION EXPIRATION

External authorization SHOULD have a defined lifetime.

Authorization MAY expire:

- after one operation,
- after one task,
- after a session,
- after a defined period,
- when context changes.

Expired authorization MUST be re-evaluated.

---

# 60. CONTEXT BINDING

Authorization SHOULD be bound to execution context.

Relevant context includes:

- user,
- agent,
- task,
- mission,
- provider,
- capability,
- target,
- risk class.

Authorization granted for one context MUST NOT automatically transfer to unrelated contexts.

---

# 61. CROSS-AGENT ACCESS

One agent MUST NOT automatically inherit another agent's external permissions.

Permission sharing MUST be explicit.

Example:

```text
Research Agent
    ↓
READ_WEB

Coding Agent
    ↓
REPOSITORY_WRITE
```

The coding agent MUST NOT automatically inherit research-agent credentials or permissions.

---

# 62. CROSS-SYSTEM BOUNDARIES

AURA MUST maintain explicit trust boundaries between:

```text
AURA Kernel
Agents
Plugins
MCP Providers
External Services
Internet
User Data
```

Crossing a trust boundary MUST be represented by an explicit execution decision.

---

# 63. SECURITY DEFAULT

The default external integration state MUST be:

```text
DENY
```

until the required conditions for execution are satisfied.

The architecture follows:

```text
Default Deny
+
Explicit Admission
+
Least Privilege
+
Auditable Execution
+
Revocable Authorization
```

---

# 64. FAIL-CLOSED BEHAVIOR

If the authorization state cannot be determined reliably, the operation MUST fail closed.

Examples:

- missing policy,
- unavailable authorization engine,
- unknown provider identity,
- invalid capability mapping,
- integrity mismatch,
- expired credential,
- incompatible version.

The correct result is:

```text
DENY
```

rather than an implicit allow.

---

# 65. GOVERNANCE INVARIANTS

The following invariants MUST remain true:

### INV-01
No external operation executes without authorization.

### INV-02
Provider discovery does not imply provider trust.

### INV-03
MCP compliance does not imply execution authorization.

### INV-04
Agent capability does not imply unrestricted provider access.

### INV-05
Credentials are not ordinary agent context.

### INV-06
Dynamic tools cannot bypass admission.

### INV-07
External output cannot override higher-level policy.

### INV-08
Revocation overrides normal authorization.

### INV-09
Unknown authorization state results in denial.

### INV-10
Version drift cannot silently bypass the locked environment.

### INV-11
External data cannot automatically become persistent memory.

### INV-12
Fallback providers must preserve security requirements.

---

# 66. REQUIRED EXECUTION CONTRACT

Every governed external operation MUST conceptually satisfy:

```text
Identity
+
Capability
+
Permission
+
Policy
+
Provider Trust
+
Compatibility
+
Execution Context
+
Credential Validity
+
Resource Constraints
+
Auditability
```

If a mandatory condition fails, execution MUST be denied or safely terminated.

---

# 67. REFERENCE EXECUTION FLOW

The canonical flow is:

```text
┌──────────────────────┐
│        AGENT         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   CAPABILITY REQUEST │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ AUTHORIZATION ENGINE │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ PROVIDER ADMISSION   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ OPERATION VALIDATION │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ CREDENTIAL BROKER    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ EXTERNAL PROVIDER    │
│ MCP / API / SERVICE  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ RESULT VALIDATION    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ AUDIT + PROVENANCE   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│        AGENT         │
└──────────────────────┘
```

---

# 68. ARCHITECTURAL BOUNDARY

This document governs **how AURA controls external integrations**.

It does not redefine:

- the MCP protocol itself,
- individual MCP server implementations,
- agent architecture,
- memory architecture,
- browser architecture,
- plugin implementation details,
- provider-specific APIs.

Those systems remain governed by their respective architecture documents.

This document establishes the governance boundary connecting them.

---

# 69. RELATIONSHIP TO DOCUMENT 34

Document 34 defines the authorization and policy contract.

This document applies that contract to external integration surfaces.

The relationship is:

```text
34
Policy / Authorization Contract
            │
            ▼
35
External Integration Governance
            │
      ┌─────┼─────┐
      ▼     ▼     ▼
     MCP   APIs  Plugins
      │     │     │
      └─────┼─────┘
            ▼
       External World
```

Therefore document 35 MUST NOT introduce an independent authorization system.

It consumes the authorization contract defined previously.

---

# 70. RELATIONSHIP TO VERSION LOCK

External integrations are subject to the Version Lock system.

Version Lock determines:

```text
WHAT VERSION
WHAT SOURCE
WHAT ARTIFACT
WHAT INTEGRITY
WHAT COMPATIBILITY
```

This document determines:

```text
WHO MAY USE IT
WHAT MAY BE EXECUTED
UNDER WHICH POLICY
WITH WHICH PERMISSIONS
```

Therefore:

```text
VERSION LOCK
     +
SECURITY / AUTHORIZATION
     =
CONTROLLED EXTERNAL INTEGRATION
```

---

# 71. RELATIONSHIP TO MANIFEST

The manifest describes the expected external integration environment.

The governance layer determines whether each integration may become operational.

Therefore:

```text
Manifest
   ↓
Expected Integration
   ↓
Verification
   ↓
Governance
   ↓
Activation
```

An integration appearing in the manifest MUST NOT automatically receive unrestricted runtime permissions.

---

# 72. RELATIONSHIP TO BOOTSTRAP

Bootstrap is responsible for establishing the runtime.

External integration governance determines whether a discovered provider may become active.

Therefore bootstrap MUST preserve the distinction:

```text
Installed
≠
Verified
≠
Trusted
≠
Authorized
≠
Active
```

These states MUST remain independently representable.

---

# 73. RELATIONSHIP TO SYSTEM VERIFICATION

System verification MUST validate that external integrations conform to their declared state.

Verification SHOULD detect:

- missing providers,
- unexpected providers,
- version drift,
- integrity mismatch,
- unauthorized capabilities,
- invalid configuration,
- broken dependencies,
- revoked providers.

Verification failure MUST prevent unsafe activation where required.

---

# 74. FINAL ARCHITECTURAL DECISION

AURA SHALL use a **governed external integration model** in which:

1. all external providers have explicit identities,
2. provider discovery does not imply trust,
3. MCP servers are treated as capability providers,
4. capabilities map to explicit permissions,
5. external operations require authorization,
6. credentials remain outside ordinary agent context,
7. high-risk operations receive stronger controls,
8. dynamic capabilities undergo admission,
9. external output is treated as untrusted data,
10. external integrations are version-controlled,
11. provider health affects selection,
12. revocation is authoritative,
13. failures are contained,
14. all significant operations are auditable,
15. unknown authorization states fail closed.

The architecture therefore establishes:

```text
AURA
  ↓
Controlled Capability Boundary
  ↓
Governed External Integrations
  ↓
MCP / APIs / Plugins / Services
  ↓
External World
```

AURA does not grant agents unrestricted access to the external world.

AURA grants agents **policy-governed capabilities** through controlled execution boundaries.

---

# 75. ACCEPTANCE CRITERIA

Document 35 is considered architecturally satisfied when the eventual implementation can demonstrate:

- provider registration,
- provider verification,
- provider trust state,
- capability discovery,
- operation admission,
- permission enforcement,
- credential isolation,
- network policy enforcement where supported,
- risk classification,
- user authorization where required,
- timeout handling,
- failure containment,
- provider revocation,
- audit records,
- provenance,
- version-lock integration,
- manifest integration,
- bootstrap integration,
- system-verification integration,
- fail-closed behavior.

No external integration is considered production-ready solely because its installation succeeds.

---

# 76. STATUS

**Document:** 35  
**Status:** APPROVED FOR IMPLEMENTATION  
**Architectural Role:** External Integration Governance  
**Primary Dependency:** Document 34 — Policy Contract and Authorization Schema  
**Downstream Dependencies:** Manifest, Bootstrap, Runtime Integration, System Verification  
**Implementation Phase:** AURA Runtime Construction