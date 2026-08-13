# 13 — MCP AND EXTERNAL INTEGRATION STACK

**Document ID:** JAS-AS-13  
**Document:** `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED STACK SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  
**Primary Protocol:** Model Context Protocol (MCP)  
**Current MCP Specification Target:** `2026-07-28`  
**Depends On:** JAS v1, `00_APPROVED_STACK_OVERVIEW.md`, `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`, `04_AGENT_ORCHESTRATION_STACK.md`, `11_BACKEND_STACK.md`, `12_PLUGIN_AND_EXTENSION_STACK.md`  
**Related Documents:** `14_SECURITY_STACK.md`, `15_DEVOPS_AND_DEPLOYMENT_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`, `20_APPROVED_MCP_SERVERS.md`, `21_APPROVED_SOFTWARE_MATRIX.md`, `22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md`, `23_LICENSE_AND_COMPLIANCE.md`, `24_VERSION_SUPPORT_POLICY.md`, `25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, System Verification, JARVIS Core

---

# 1. PURPOSE

This document defines the approved architecture, protocol strategy, security model, lifecycle, technology direction and governance rules for external integrations in JARVIS.

The primary purpose of this layer is to allow JARVIS to interact with external systems without tightly coupling JARVIS Core to every external service.

The fundamental architecture is:

```text
JARVIS
   ↓
External Integration Layer
   ↓
Protocol / Adapter
   ↓
External Capability Provider
   ↓
External System
```

---

# 2. CORE DECISION

**Model Context Protocol (MCP) is the primary standardized external capability protocol for JARVIS v1.**

MCP will be used where an external capability can reasonably be exposed through the MCP protocol.

---

# 3. MCP IS NOT JARVIS

MCP is not:

```text
JARVIS Core
```

MCP is not:

```text
Agent Orchestrator
```

MCP is not:

```text
Plugin System
```

MCP is not:

```text
Security Policy Engine
```

MCP is not:

```text
Memory System
```

MCP is an interoperability layer.

---

# 4. MCP ROLE

MCP provides a standardized interface between JARVIS and external capability providers.

Conceptually:

```text
JARVIS
   ↓
MCP Client
   ↓
MCP Server
   ↓
External System
```

---

# 5. PLUGIN VS MCP

The distinction established in `12_PLUGIN_AND_EXTENSION_STACK.md` remains mandatory.

### Plugin

```text
JARVIS
   ↓
Plugin Manager
   ↓
JARVIS-native Plugin
```

### MCP

```text
JARVIS
   ↓
MCP Client
   ↓
External MCP Server
```

Therefore:

```text
PLUGIN ≠ MCP
```

---

# 6. WHEN TO USE A PLUGIN

A Plugin is preferred when:

```text
The functionality is JARVIS-native
The extension needs deep JARVIS lifecycle integration
The extension should use the JARVIS Plugin SDK
The extension is part of the JARVIS application ecosystem
```

---

# 7. WHEN TO USE MCP

MCP is preferred when:

```text
The capability is external
The provider already exposes MCP
The integration should remain protocol-oriented
The capability may be shared by multiple AI clients
The integration should remain decoupled from JARVIS internals
```

---

# 8. WHEN NOT TO USE MCP

MCP should not be introduced merely because it exists.

If a simple internal service API is more appropriate:

```text
JARVIS Service
```

should remain the preferred mechanism.

---

# 9. INTERNAL API VS MCP

```text
Internal JARVIS Functionality
        ↓
Service/API

External Capability
        ↓
MCP
```

---

# 10. MCP CLIENT

JARVIS v1 will contain an MCP Client subsystem.

Responsibilities:

```text
Server Discovery
Connection
Protocol Negotiation
Capability Discovery
Tool Discovery
Resource Discovery
Prompt Discovery
Task Handling
Authorization
Request Execution
Result Validation
Error Handling
Observability
Lifecycle
```

---

# 11. MCP SERVER

An MCP Server is an external capability provider.

Examples:

```text
GitHub
Filesystem
Database
Calendar
Documentation
Browser
Cloud Service
Development Tool
Research Service
```

---

# 12. MCP SERVER TRUST

An MCP server must never be trusted merely because it implements MCP.

```text
MCP-compatible
    ≠
Trusted
```

---

# 13. TRUST MODEL

Trust must be evaluated independently of protocol compatibility.

```text
Protocol Compatibility
        +
Identity
        +
Integrity
        +
Security
        +
Permissions
        +
Policy
```

---

# 14. MCP CAPABILITY TYPES

JARVIS must support the MCP capability model appropriate to the supported specification.

Primary categories include:

```text
Tools
Resources
Prompts
```

Additional protocol/extension capabilities may be supported according to the locked MCP specification.

---

# 15. TOOLS

MCP Tools represent callable operations.

Conceptually:

```text
Agent
 ↓
MCP Client
 ↓
MCP Tool
 ↓
External Action
```

---

# 16. RESOURCES

MCP Resources represent externally provided data/context.

Conceptually:

```text
External System
 ↓
MCP Resource
 ↓
JARVIS
 ↓
Context / Agent / User
```

---

# 17. PROMPTS

MCP Prompts may provide reusable prompt templates from an MCP server.

However:

```text
MCP Prompt
    ≠
JARVIS System Prompt
```

---

# 18. PROMPT TRUST

MCP-provided prompts must be treated as external content.

They cannot override:

```text
JAS
Security Policy
System Instructions
User Permissions
```

---

# 19. MCP EXTENSIONS

JARVIS should support MCP extensions where they provide clear architectural value.

The MCP project now has a formal extensions framework.

Extensions must be explicitly evaluated rather than automatically enabled. 

---

# 20. TASKS

Long-running MCP operations may use the MCP Tasks extension where appropriate.

Tasks are treated as an MCP extension rather than as an assumption about every MCP tool.

---

# 21. MCP APPS

MCP Apps / server-provided UI capabilities may eventually be supported.

Status:

```text
CONDITIONAL / FUTURE
```

They require separate frontend security evaluation.

---

# 22. DEPRECATED FEATURES

JARVIS should not build new architecture around MCP features that are officially deprecated in the selected specification.

The `2026-07-28` specification explicitly deprecates:

```text
Roots
Sampling
Logging
Legacy HTTP+SSE transport
```

for new implementations. 

---

# 23. MCP VERSION POLICY

JARVIS will explicitly pin the MCP protocol specification version.

Conceptually:

```text
MCP Protocol
    ↓
2026-07-28
```

Exact SDK package versions belong to Version Lock.

---

# 24. VERSION LOCK

Version Lock will eventually define:

```text
MCP Specification
MCP Client SDK
MCP Server SDKs
Supporting Libraries
```

with exact versions.

---

# 25. SDK LANGUAGE

The primary JARVIS MCP client implementation should use:

```text
Python
```

because Python is the primary JARVIS backend/runtime language.

---

# 26. TYPESCRIPT MCP

TypeScript remains an approved supporting ecosystem where frontend/Node integrations benefit from it.

Status:

```text
CONDITIONAL / APPROVED FOR SPECIFIC USE
```

depending on the integration.

---

# 27. MULTI-LANGUAGE MCP

MCP itself is language-neutral.

JARVIS must not make external MCP server language a requirement.

---

# 28. MCP CLIENT ARCHITECTURE

```text
                     JARVIS
                        │
                  MCP Gateway
                        │
                 MCP Client Pool
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
      MCP Server A  MCP Server B  MCP Server C
          │             │             │
          ▼             ▼             ▼
       GitHub        Calendar       Database
```

---

# 29. MCP GATEWAY

JARVIS should use an MCP Gateway/Manager abstraction between agents and raw MCP connections.

Responsibilities:

```text
Server Registry
Connection Management
Capability Catalog
Authorization
Routing
Rate Limiting
Observability
Caching
Policy
```

---

# 30. AGENTS MUST NOT CONNECT DIRECTLY

Agents should not independently create arbitrary MCP connections.

Prohibited:

```text
Agent
 ↓
Raw MCP Connection
```

Preferred:

```text
Agent
 ↓
MCP Gateway
 ↓
MCP Client
 ↓
MCP Server
```

---

# 31. MCP SERVER REGISTRY

JARVIS maintains an internal registry of configured MCP servers.

Metadata should include:

```text
Server ID
Name
Version
Endpoint
Transport
Trust State
Authorization
Capabilities
Permissions
Owner
Source
Status
```

---

# 32. SERVER ID

Each configured MCP server receives a stable JARVIS-local identifier.

Example:

```text
github.primary
calendar.personal
filesystem.local
```

---

# 33. SERVER ID VS MCP SERVER NAME

The local JARVIS server ID is separate from the server's advertised MCP identity.

---

# 34. SERVER DISCOVERY

Discovery may occur through:

```text
Configured Server
Official Registry
Local Configuration
Approved Deployment Manifest
Enterprise Registry
```

---

# 35. DISCOVERY DOES NOT EQUAL TRUST

A discovered server must remain untrusted until validated.

---

# 36. OFFICIAL MCP REGISTRY

The official MCP ecosystem now provides a registry for discovering MCP servers.

JARVIS may use the official registry as a discovery source, but registry presence must not automatically imply JARVIS approval. citeturn0search11

---

# 37. APPROVED MCP REGISTRY

JARVIS should maintain its own approval layer.

Conceptually:

```text
Official MCP Registry
        ↓
JARVIS Evaluation
        ↓
Approved MCP Registry
```

---

# 38. APPROVED MCP SERVER

A server becomes Approved only after:

```text
Security Review
License Review
Compatibility Review
Capability Review
Testing
Maintenance Review
```

---

# 39. CONDITIONAL MCP SERVER

A server may be:

```text
CONDITIONALLY APPROVED
```

with restrictions such as:

```text
Read-only
Local-only
No credential access
No destructive tools
Limited network
```

---

# 40. EXPERIMENTAL MCP SERVER

Experimental servers may be used only in controlled environments.

---

# 41. REJECTED MCP SERVER

Rejected servers cannot enter the Approved environment.

---

# 42. REVOKED MCP SERVER

An approved server may later be revoked.

Reasons:

```text
Security Vulnerability
Malicious Behavior
License Issue
Abandonment
Breaking Changes
Compromise
```

---

# 43. MCP SERVER LIFECYCLE

```text
DISCOVERED
    ↓
EVALUATING
    ↓
APPROVED / CONDITIONAL / EXPERIMENTAL / REJECTED
    ↓
CONFIGURED
    ↓
AUTHORIZED
    ↓
CONNECTED
    ↓
HEALTHY
    ↓
DEGRADED / FAILED
    ↓
DISABLED / REVOKED
```

---

# 44. TRANSPORT

The primary remote MCP transport direction for JARVIS v1 is:

```text
Streamable HTTP / current MCP HTTP transport
```

according to the locked MCP specification.

---

# 45. STDIO

STDIO remains appropriate for local MCP servers where supported.

Typical architecture:

```text
JARVIS
 ↓
Process Launcher
 ↓
MCP Server Process
```

---

# 46. LOCAL STDIO USE CASE

STDIO is especially useful for:

```text
Local Tools
Local Filesystem
Development Tools
Local Databases
Local Utilities
```

---

# 47. REMOTE HTTP USE CASE

HTTP-based MCP is preferred for:

```text
Remote Services
Cloud Integrations
Shared Services
Horizontally Scaled MCP Servers
```

---

# 48. LEGACY HTTP+SSE

New JARVIS architecture must not depend on the legacy HTTP+SSE transport.

It is deprecated in the current specification.

---

# 49. STATELESS MCP

The current MCP specification uses a stateless protocol core.

JARVIS must therefore not design its core MCP gateway around mandatory protocol-level sessions. citeturn0search0

---

# 50. APPLICATION STATE VS PROTOCOL STATE

Important distinction:

```text
MCP Protocol
    ↓
Stateless

JARVIS Application
    ↓
May maintain state
```

---

# 51. JARVIS MCP STATE

JARVIS may maintain:

```text
Server Configuration
Authorization State
Tool Catalog Cache
Resource Catalog Cache
Health State
Task State
Usage Metrics
```

without treating these as mandatory MCP protocol sessions.

---

# 52. LOAD BALANCING

The stateless MCP model permits remote servers to operate behind ordinary load balancing where their application architecture supports it. citeturn0search0

JARVIS should prefer infrastructure-compatible deployments.

---

# 53. HEADER-BASED ROUTING

The current specification supports MCP HTTP routing information in headers.

JARVIS gateways may use this for:

```text
Routing
Authorization
Metering
Observability
```

where appropriate. citeturn0search0

---

# 54. CAPABILITY DISCOVERY

JARVIS should discover the capabilities of each MCP server before allowing agents to use them.

---

# 55. TOOL CATALOG

The MCP Gateway should maintain a catalog of available tools.

Example:

```text
github.search
github.issue.create
calendar.list
calendar.create
```

---

# 56. TOOL NAMESPACE

JARVIS should namespace external MCP tools.

Example:

```text
mcp.github.search
mcp.calendar.create
```

This avoids collisions with:

```text
plugin.*
core.*
```

---

# 57. TOOL COLLISION

Two MCP servers may expose identical tool names.

The JARVIS namespace must prevent ambiguity.

---

# 58. TOOL SELECTION

Agents should select MCP tools through the centralized Tool/Capability Registry.

---

# 59. TOOL REGISTRY

The registry should contain:

```text
Tool ID
MCP Server
Description
Input Schema
Output Schema
Risk
Permissions
Availability
Version
```

---

# 60. TOOL SCHEMAS

JARVIS must validate tool arguments against the declared schema.

---

# 61. INPUT VALIDATION

Before an MCP tool call:

```text
Agent Output
 ↓
Schema Validation
 ↓
Policy Validation
 ↓
Permission Validation
 ↓
MCP Call
```

---

# 62. OUTPUT VALIDATION

MCP results must be validated before entering:

```text
Agent Context
Memory
UI
```

---

# 63. UNTRUSTED RESULT

An MCP result is external data.

Therefore:

```text
MCP Result
    ≠
Trusted Instruction
```

---

# 64. PROMPT INJECTION

MCP resources/tool results may contain prompt injection.

JARVIS must treat external text as untrusted content.

---

# 65. INSTRUCTION SEPARATION

External data must not automatically become system instructions.

---

# 66. TOOL DESCRIPTION INJECTION

Tool descriptions themselves may be untrusted.

A malicious MCP server could attempt to influence agent behavior through descriptions.

---

# 67. TOOL TRUST

Tool trust must be established by server approval and capability policy, not by tool description alone.

---

# 68. TOOL RISK CLASSIFICATION

Every MCP tool should receive a risk classification.

```text
LOW
MEDIUM
HIGH
CRITICAL
```

---

# 69. READ-ONLY TOOL

Examples:

```text
github.search
calendar.list
filesystem.read
database.query
```

may be classified as low/medium depending on data sensitivity.

---

# 70. MUTATING TOOL

Examples:

```text
github.issue.create
calendar.create
database.write
filesystem.write
```

require higher policy scrutiny.

---

# 71. DESTRUCTIVE TOOL

Examples:

```text
filesystem.delete
database.drop
account.delete
```

should be classified as high/critical.

---

# 72. TOOL ANNOTATIONS

Where supported, MCP tool annotations may help communicate behavioral characteristics such as read-only, destructive or idempotent behavior.

Annotations are hints, not a substitute for security policy.

---

# 73. ANNOTATIONS ≠ SECURITY

A tool saying:

```text
readOnlyHint: true
```

does not prove it is actually read-only.

---

# 74. SERVER TRUST + TOOL TRUST

Security evaluation should operate at both levels:

```text
MCP Server Trust
+
Tool Risk
```

---

# 75. PERMISSION MODEL

MCP capabilities integrate with the same central JARVIS permission model used for plugins.

---

# 76. MCP CAPABILITY

Conceptually:

```text
mcp.github.read
mcp.github.write
mcp.calendar.read
mcp.calendar.write
```

---

# 77. DEFAULT DENY

Undeclared MCP capabilities are denied by default.

---

# 78. LEAST PRIVILEGE

MCP servers receive only required permissions.

---

# 79. SERVER PERMISSION

A server may expose many tools, but JARVIS may enable only a subset.

---

# 80. TOOL PERMISSION

Permissions can be applied at tool level.

---

# 81. RESOURCE PERMISSION

Resources may require separate permissions.

---

# 82. USER APPROVAL

High-risk MCP operations may require explicit user approval.

---

# 83. TEMPORARY PERMISSION

JARVIS may grant temporary capability access for a single task/session.

---

# 84. PERMISSION SCOPE

Possible scopes:

```text
Server
Tool
Resource
User
Task
Session
Workspace
Time
```

---

# 85. CREDENTIALS

JARVIS must not expose raw credentials to agents unless absolutely required and explicitly authorized.

---

# 86. OAUTH

Remote MCP authorization should use the MCP/OAuth authorization model defined by the selected specification.

The current MCP specification has further hardened authorization behavior and moves toward Client ID Metadata Documents rather than Dynamic Client Registration as the long-term direction. citeturn0search0

---

# 87. AUTHORIZATION SERVER

JARVIS should validate authorization-server identity and token issuer information according to the current MCP authorization requirements.

---

# 88. TOKEN BINDING

Credentials must remain bound to their intended authorization context.

---

# 89. TOKEN STORAGE

Tokens should be stored in the central JARVIS secret-management mechanism.

---

# 90. NO PLAINTEXT TOKENS

Tokens must not be stored in:

```text
Manifest
Source Code
Logs
Git
Plugin Configuration
```

in plaintext.

---

# 91. TOKEN ROTATION

Where supported, tokens should be refreshable/rotatable.

---

# 92. TOKEN REVOCATION

JARVIS should support revoking MCP authorization.

---

# 93. LOCAL MCP AUTH

Local STDIO servers may use a different trust model, but local execution does not automatically mean trusted.

---

# 94. LOCAL PROCESS TRUST

A locally launched MCP server must still pass:

```text
Source Validation
Artifact Validation
Permission Validation
```

---

# 95. REMOTE SERVER AUTHENTICATION

Remote MCP servers require authenticated transport where appropriate.

---

# 96. TLS

Remote MCP HTTP connections must use secure transport.

---

# 97. CERTIFICATE VALIDATION

Production deployments must not disable TLS certificate validation.

---

# 98. NETWORK POLICY

Network access is controlled centrally.

---

# 99. DESTINATION ALLOWLIST

High-risk integrations may require explicit destination allowlists.

---

# 100. SSRF PROTECTION

JARVIS must protect MCP clients/gateways from SSRF-style abuse.

MCP endpoints must not allow arbitrary internal-network access without policy authorization.

---

# 101. LOCAL NETWORK ACCESS

Requests to:

```text
localhost
127.0.0.1
private IP ranges
cloud metadata endpoints
```

must be governed by explicit network policy where relevant.

---

# 102. DNS REBINDING

Remote MCP connections should consider DNS rebinding and destination validation risks.

---

# 103. REDIRECT POLICY

Authorization and HTTP redirects must be controlled.

---

# 104. TIMEOUTS

Every MCP request must have a bounded timeout.

---

# 105. RETRIES

Retries must be bounded and policy-controlled.

---

# 106. IDEMPOTENCY

Mutating calls must not be retried blindly.

---

# 107. RETRY POLICY

Conceptually:

```text
Read-only
    → bounded retry

Idempotent mutation
    → conditional retry

Non-idempotent mutation
    → no automatic retry unless explicitly safe
```

---

# 108. RATE LIMITING

MCP servers and tools should have rate limits.

---

# 109. QUOTAS

Future JARVIS deployments may enforce:

```text
Calls/minute
Calls/day
Data volume
Task count
```

per server/tool.

---

# 110. COST CONTROL

Cloud MCP integrations may incur external costs.

JARVIS should track cost where measurable.

---

# 111. USAGE ACCOUNTING

Metrics should include:

```text
Requests
Latency
Failures
Tokens if applicable
Data Volume
External Cost
```

---

# 112. CACHING

The current MCP specification provides cache hints for list/read responses.

JARVIS may cache compatible results according to server-provided cache information and local policy. citeturn0search0

---

# 113. CACHEABLE DATA

Potentially cacheable:

```text
Tool Catalog
Prompt Catalog
Resource Catalog
Static Resource Data
```

---

# 114. NON-CACHEABLE DATA

Highly dynamic or sensitive data may not be cached.

---

# 115. CACHE SECURITY

Sensitive MCP data must not leak across:

```text
Users
Sessions
Workspaces
Permissions
```

---

# 116. CACHE INVALIDATION

Cache invalidation must respect:

```text
TTL
Server Hints
Local Policy
Security Events
Permission Changes
```

---

# 117. MCP TASKS

Long-running operations may return task handles.

Conceptually:

```text
Agent
 ↓
MCP Tool Call
 ↓
Task Handle
 ↓
Task Status
 ↓
Result
```

---

# 118. TASK OWNERSHIP

MCP task state must be associated with the correct JARVIS user/task context.

---

# 119. TASK POLLING

JARVIS may poll MCP task state according to the protocol.

---

# 120. TASK CANCELLATION

Where supported, JARVIS should support cancellation.

---

# 121. TASK TIMEOUT

Long-running MCP tasks must have a JARVIS-side timeout policy even if the server does not.

---

# 122. TASK RETENTION

Completed task results should have controlled retention.

---

# 123. TASK SECURITY

Task handles must not be exposed to unauthorized users.

---

# 124. MCP RESOURCE SECURITY

Resources may contain:

```text
Personal Data
Credentials
Private Documents
Code
Business Data
```

Therefore resource access must be permission-controlled.

---

# 125. RESOURCE URIS

External resource identifiers should not be blindly interpreted as local filesystem paths.

---

# 126. RESOURCE FETCHING

Resource fetching must pass:

```text
Authorization
Network Policy
Schema/Content Validation
```

where applicable.

---

# 127. RESOURCE SIZE LIMIT

JARVIS must enforce resource size limits.

---

# 128. RESOURCE TYPE

Resource content should carry type metadata where available.

---

# 129. CONTENT VALIDATION

Potentially dangerous content types require special handling.

---

# 130. FILE DOWNLOADS

MCP resources that represent files should pass through artifact/download security policies.

---

# 131. EXECUTABLE CONTENT

Downloaded executables must not be automatically executed.

---

# 132. ARCHIVE CONTENT

Archives must be protected against:

```text
Path Traversal
Zip Bomb
Resource Exhaustion
Malicious Payloads
```

---

# 133. MCP PROMPT SECURITY

MCP prompts are external content.

---

# 134. PROMPT EXECUTION

An MCP prompt must never bypass JARVIS's own instruction hierarchy.

---

# 135. PROMPT REVIEW

High-trust environments may restrict which MCP prompts are exposed to agents.

---

# 136. PROMPT CATALOG

JARVIS should maintain a catalog of available MCP prompts.

---

# 137. PROMPT NAMESPACE

Example:

```text
mcp.github.prompt.issue_summary
```

---

# 138. EXTERNAL INSTRUCTIONS

External instructions are always lower trust than JARVIS security/system policy.

---

# 139. MCP SERVER CONFIGURATION

Configuration should contain:

```text
Server ID
Transport
Endpoint
Command
Arguments
Environment
Authorization
Permissions
Enabled Tools
Enabled Resources
```

---

# 140. COMMAND VALIDATION

For STDIO MCP servers, executable commands must be allowlisted/validated.

---

# 141. NO ARBITRARY COMMAND EXECUTION

MCP server configuration must not become an unrestricted shell execution mechanism.

---

# 142. STDIO ENVIRONMENT

Environment variables passed to an MCP server must be explicitly selected.

---

# 143. NO SECRET INHERITANCE

A local MCP server must not automatically inherit all JARVIS secrets.

---

# 144. MCP SERVER SANDBOX

High-risk local MCP servers should be isolated where practical.

---

# 145. PROCESS ISOLATION

Potential model:

```text
JARVIS
 ↓
MCP Supervisor
 ↓
MCP Server Process
```

---

# 146. CONTAINER ISOLATION

Containerized MCP servers may be used for higher-risk integrations.

---

# 147. OCI

OCI-compatible images may be supported for server deployments.

---

# 148. DOCKER

Docker may be used where approved by the Deployment Stack.

---

# 149. REMOTE MCP

Remote MCP servers may run independently from JARVIS.

---

# 150. REMOTE SERVER SCALING

Stateless MCP protocol behavior allows compatible remote servers to scale horizontally.

---

# 151. LOAD BALANCER

Compatible remote MCP servers may operate behind:

```text
Load Balancer
 ↓
MCP Server A
MCP Server B
MCP Server C
```

---

# 152. MCP GATEWAY SCALING

JARVIS's own MCP Gateway should also be horizontally scalable in future deployments.

---

# 153. MCP CLIENT POOL

Multiple MCP server connections may be maintained through a managed client pool.

---

# 154. CONNECTION MANAGEMENT

The client layer manages:

```text
Connect
Disconnect
Reconnect
Health
Timeout
Backoff
```

---

# 155. RECONNECT

Connection failures should use bounded exponential backoff.

---

# 156. CIRCUIT BREAKER

Frequently failing MCP servers may be temporarily isolated.

---

# 157. DEGRADED STATE

A server can be:

```text
HEALTHY
DEGRADED
UNAVAILABLE
BLOCKED
```

---

# 158. HEALTH CHECK

Health checks should be lightweight and protocol-compatible.

---

# 159. HEALTH ≠ TRUST

A server being reachable does not mean it is trusted.

---

# 160. SERVER METADATA

JARVIS should retain server metadata for observability and compliance.

---

# 161. MCP SERVER VERSION

Where available, server version should be recorded.

---

# 162. SERVER CAPABILITY VERSION

Protocol and server capability versions must be distinguished.

---

# 163. SERVER CHANGE DETECTION

Unexpected capability changes should trigger review.

---

# 164. TOOL DRIFT

If a server suddenly adds:

```text
filesystem.delete
```

where it previously had only read tools, JARVIS should detect the capability drift.

---

# 165. CAPABILITY DRIFT

Unexpected capability expansion should not automatically become available to agents.

---

# 166. PERMISSION DRIFT

New capabilities require explicit policy evaluation.

---

# 167. SCHEMA DRIFT

Tool schema changes may break agents and must be detected.

---

# 168. COMPATIBILITY TESTING

Approved MCP servers should be tested against the locked JARVIS MCP client.

---

# 169. CONTRACT TESTING

JARVIS should provide MCP integration contract tests.

---

# 170. MCP CONFORMANCE

Servers should be evaluated for protocol conformance where practical.

---

# 171. SECURITY TESTING

MCP servers should be tested for:

```text
Authentication
Authorization
Input Validation
Output Validation
Prompt Injection
SSRF
Path Traversal
Resource Exhaustion
Credential Exposure
```

---

# 172. MALICIOUS SERVER MODEL

JARVIS security architecture must assume that an MCP server can be malicious or compromised.

---

# 173. COMPROMISED SERVER

If an MCP server becomes compromised:

```text
Revoke
 ↓
Disable
 ↓
Block
 ↓
Audit
 ↓
Notify
```

---

# 174. EMERGENCY DISABLE

JARVIS must support emergency disabling of an MCP server.

---

# 175. GLOBAL MCP KILL SWITCH

A deployment may provide a global mechanism to disable all MCP integrations.

---

# 176. SAFE MODE

Future Safe Mode may disable:

```text
All MCP Servers
```

while leaving Core operational.

---

# 177. AUDIT LOGGING

MCP security-sensitive actions must be auditable.

Examples:

```text
Server Connected
Tool Called
Permission Granted
Permission Denied
Authorization Refreshed
Server Disabled
Capability Changed
```

---

# 178. REQUEST IDs

Every MCP request should have traceable request metadata.

---

# 179. TRACE ID

MCP calls should integrate with JARVIS distributed tracing.

---

# 180. USER ID

Where applicable, MCP requests should retain the originating user context internally.

---

# 181. TASK ID

Agent-triggered MCP calls should retain task context.

---

# 182. AGENT ID

Where applicable, execution should identify the originating agent.

---

# 183. OBSERVABILITY

Minimum MCP observability:

```text
Request Count
Latency
Error Rate
Tool Usage
Server Health
Permission Denials
Authorization Errors
Task Count
```

---

# 184. LOG REDACTION

MCP logs must redact:

```text
Tokens
Passwords
API Keys
Secrets
Sensitive Personal Data
```

---

# 185. RESULT SIZE

MCP results should have configurable maximum sizes.

---

# 186. TOKEN BUDGET

Large MCP results should not automatically consume unlimited LLM context.

---

# 187. CONTEXT MANAGEMENT

JARVIS may summarize/filter MCP results before sending them to the LLM.

---

# 188. RAW RESULT RETENTION

Raw results may be retained only according to data policy.

---

# 189. MEMORY WRITE POLICY

MCP results should not automatically enter long-term memory.

---

# 190. PROVENANCE

MCP-derived information should preserve source provenance where practical.

---

# 191. SOURCE LABEL

Example:

```text
source:
  type: mcp
  server: github.primary
  tool: github.search
```

---

# 192. AGENT REASONING

Agents should know when information originates from external MCP systems.

---

# 193. EXTERNAL DATA TRUST

External MCP information may be useful evidence but is not automatically authoritative.

---

# 194. AUTHORITY HIERARCHY

```text
JAS / System Policy
        ↓
Security Policy
        ↓
User Instruction
        ↓
Trusted Application State
        ↓
External MCP Data
```

---

# 195. EXTERNAL INSTRUCTION

An MCP server cannot override user/system policy.

---

# 196. MCP TOOL CALL FLOW

```text
User
 ↓
Intent
 ↓
Planner
 ↓
Agent
 ↓
Capability Registry
 ↓
MCP Tool Discovery
 ↓
Permission
 ↓
Policy
 ↓
Schema Validation
 ↓
MCP Gateway
 ↓
MCP Client
 ↓
MCP Server
 ↓
External System
 ↓
Result Validation
 ↓
Agent
```

---

# 197. MCP RESOURCE FLOW

```text
Agent
 ↓
Resource Request
 ↓
Permission
 ↓
MCP Gateway
 ↓
MCP Server
 ↓
External Resource
 ↓
Content Validation
 ↓
Context Processing
```

---

# 198. MCP AUTH FLOW

```text
JARVIS
 ↓
MCP Server
 ↓
Authorization Metadata
 ↓
Authorization Server
 ↓
User Consent / Policy
 ↓
Token
 ↓
Secure Storage
 ↓
Authenticated MCP Request
```

---

# 199. MCP TASK FLOW

```text
Agent
 ↓
MCP Tool
 ↓
Task Created
 ↓
Task Handle
 ↓
Task Status
 ↓
Completion
 ↓
Result
```

---

# 200. MCP FAILURE FLOW

```text
MCP Call
 ↓
Timeout / Failure
 ↓
Retry Policy
 ↓
Circuit Breaker
 ↓
Degraded State
 ↓
Agent Recovery
```

---

# 201. MCP SECURITY FLOW

```text
Server Identity
 ↓
Integrity
 ↓
Authorization
 ↓
Capability
 ↓
Permission
 ↓
Policy
 ↓
Schema Validation
 ↓
Execution
 ↓
Output Validation
 ↓
Audit
```

---

# 202. EXTERNAL INTEGRATION LAYERS

The JARVIS external integration architecture is:

```text
┌───────────────────────────────┐
│          JARVIS CORE          │
└───────────────┬───────────────┘
                ↓
┌───────────────────────────────┐
│     CAPABILITY / TOOL LAYER   │
└───────────────┬───────────────┘
                ↓
┌───────────────────────────────┐
│         MCP GATEWAY           │
└───────────────┬───────────────┘
                ↓
┌───────────────────────────────┐
│          MCP CLIENT           │
└───────────────┬───────────────┘
                ↓
        ┌───────┴────────┐
        ↓                ↓
   LOCAL MCP         REMOTE MCP
     SERVER             SERVER
        ↓                ↓
   Local System      External API
```

---

# 203. MCP AND PLUGIN COMPOSITION

A Plugin may internally use MCP.

Example:

```text
JARVIS Plugin
      ↓
MCP Client
      ↓
External MCP Server
```

This is allowed if explicitly designed.

---

# 204. MCP SERVER INSIDE PLUGIN

A plugin may eventually provide an MCP server, but this should not be the default mechanism for JARVIS-native extensions.

---

# 205. PLUGIN AS MCP BRIDGE

A plugin may act as an adapter where:

```text
JARVIS-native API
        ↕
MCP
```

provides useful interoperability.

---

# 206. MCP BRIDGE SECURITY

Bridges must preserve the stricter permission boundary.

---

# 207. MCP TO PLUGIN

An external MCP server should not gain direct access to JARVIS plugin internals.

---

# 208. NO CROSS-BYPASS

Neither:

```text
Plugin → bypass MCP policy
```

nor:

```text
MCP → bypass Plugin policy
```

is permitted.

---

# 209. UNIFIED CAPABILITY MODEL

Plugins and MCP should eventually feed the same central capability registry.

```text
Plugin Capability
       │
       ├──────────┐
       │          │
       ▼          ▼
   Capability Registry
       ▲          ▲
       │          │
       └──────────┘
        MCP Capability
```

---

# 210. UNIFIED PERMISSION MODEL

Plugins and MCP should use the same policy engine where possible.

---

# 211. UNIFIED TOOL MODEL

The agent should not need to know whether a tool originates from:

```text
Core
Plugin
MCP
```

The infrastructure should expose normalized metadata.

---

# 212. TOOL ORIGIN

Every tool should retain origin metadata:

```text
core
plugin
mcp
```

---

# 213. ORIGIN-AWARE SECURITY

Risk evaluation may use tool origin.

---

# 214. TOOL NORMALIZATION

MCP tools should be normalized into JARVIS's internal tool representation.

---

# 215. MCP RESULT NORMALIZATION

MCP responses should be normalized into JARVIS internal result types.

---

# 216. ERROR NORMALIZATION

External protocol errors should become standardized JARVIS errors.

---

# 217. MCP ERROR

Example:

```text
MCP_SERVER_UNAVAILABLE
MCP_AUTH_REQUIRED
MCP_PERMISSION_DENIED
MCP_TOOL_INVALID
MCP_TIMEOUT
MCP_SCHEMA_ERROR
```

---

# 218. USER-FACING ERROR

Users should receive meaningful messages rather than raw protocol errors.

---

# 219. AGENT-FACING ERROR

Agents should receive structured machine-readable errors.

---

# 220. RETRYABLE ERROR

Errors should identify whether retry may be appropriate.

---

# 221. MCP SERVER REGISTRY STORAGE

Registry metadata should be stored in the approved persistent backend.

---

# 222. CONFIGURATION STORAGE

Server configuration should be managed through JARVIS configuration management.

---

# 223. SECRET STORAGE

Credentials should be stored in the approved secret-management layer.

---

# 224. MCP MANIFEST

Global JARVIS Manifest should eventually define approved/configured MCP servers.

Conceptually:

```yaml
mcp:
  servers:
    - id: github.primary
      source: approved-registry
      version: ...
      enabled: true
```

---

# 225. VERSION LOCK

Version Lock should contain:

```text
MCP Specification
Client SDK
Approved MCP Server Version
Artifact Hash
Container Image Digest
```

where applicable.

---

# 226. SERVER VERSION PINNING

Production MCP servers should be pinned rather than blindly tracking latest.

---

# 227. LATEST TAG

Production should avoid:

```text
latest
```

as a reproducibility strategy.

---

# 228. IMAGE DIGEST

Containerized MCP servers should preferably use immutable image digests.

---

# 229. SERVER UPDATE

MCP server updates follow:

```text
Candidate
 ↓
Security Review
 ↓
Compatibility Test
 ↓
Staging
 ↓
Production
```

---

# 230. SERVER ROLLBACK

Previous approved server version should remain available where practical.

---

# 231. CAPABILITY CHANGE ON UPDATE

An updated server must be re-evaluated if capabilities change.

---

# 232. PERMISSION CHANGE ON UPDATE

New permissions require explicit review.

---

# 233. SERVER DEPRECATION

Deprecated servers should have migration paths.

---

# 234. MIGRATION

Migration may involve:

```text
Server A
 ↓
Server B
 ↓
Capability Mapping
 ↓
Tool Compatibility
```

---

# 235. EXTERNAL SERVICE ADAPTER

If an external service does not have MCP, JARVIS may use a native integration adapter.

---

# 236. NATIVE ADAPTER

Example:

```text
JARVIS
 ↓
External Integration Adapter
 ↓
REST API
```

---

# 237. MCP FIRST, NOT MCP ONLY

MCP is the preferred standardized external protocol, but not every integration must be forced through MCP.

---

# 238. REST INTEGRATION

REST APIs remain supported for cases where:

```text
No suitable MCP server exists
Performance requires direct API
Protocol semantics are unsuitable
The integration is core infrastructure
```

---

# 239. GRAPHQL

GraphQL may be used where appropriate.

Status:

```text
CONDITIONAL
```

---

# 240. WEBSOCKETS

WebSockets may be used for external realtime systems where MCP is not appropriate.

Status:

```text
CONDITIONAL
```

---

# 241. WEBHOOKS

Webhooks may be used for external event delivery.

---

# 242. WEBHOOK SECURITY

Webhooks require:

```text
Signature Validation
Authentication
Replay Protection
Rate Limiting
Payload Validation
```

---

# 243. POLLING

Polling may be used when no event mechanism exists.

---

# 244. POLLING POLICY

Polling must use:

```text
Bounded Frequency
Backoff
Caching
Rate Limits
```

---

# 245. EVENT BRIDGE

External events may enter JARVIS through:

```text
MCP
Webhook
Queue
Native Adapter
```

---

# 246. EVENT NORMALIZATION

All external events should eventually be normalized into JARVIS event schemas.

---

# 247. EVENT SOURCE

Events retain source metadata:

```text
mcp
webhook
api
plugin
system
```

---

# 248. EXTERNAL INTEGRATION PRIORITY

Preferred order:

```text
Official MCP Server
        ↓
Trusted MCP Server
        ↓
Native API Adapter
        ↓
Generic HTTP Integration
        ↓
Custom Integration
```

subject to security and architectural suitability.

---

# 249. OFFICIAL SERVER

An official vendor MCP server is preferred when:

```text
Security
Maintenance
Compatibility
License
```

are acceptable.

---

# 250. COMMUNITY SERVER

Community MCP servers require additional review.

---

# 251. CUSTOM SERVER

JARVIS may implement custom MCP servers where no suitable existing server exists.

---

# 252. JARVIS-OWNED MCP SERVER

A JARVIS-owned MCP server may wrap:

```text
Internal Service
Legacy API
Hardware
Custom Tool
```

---

# 253. INTERNAL MCP

Internal MCP use is permitted but should not replace direct internal APIs unnecessarily.

---

# 254. MCP SERVER DEVELOPMENT

Custom MCP servers should use official SDKs where practical.

---

# 255. MCP SDK

The official Python MCP SDK is the preferred implementation SDK for JARVIS-owned Python MCP servers.

Exact version belongs to Version Lock.

---

# 256. SDK CONFORMANCE

Custom servers should pass:

```text
Protocol Tests
Security Tests
Schema Tests
Lifecycle Tests
```

---

# 257. SERVER MANIFEST

Custom MCP servers should document:

```text
Identity
Version
Capabilities
Tools
Resources
Prompts
Permissions
Dependencies
```

---

# 258. SERVER DOCUMENTATION

Every approved server should have operational documentation.

---

# 259. SERVER RUNBOOK

Production servers should document:

```text
Startup
Shutdown
Health
Failure
Recovery
Update
Rollback
```

---

# 260. EXTERNAL INTEGRATION TESTING

Integration tests should include:

```text
Connectivity
Authentication
Tool Calls
Resource Access
Error Handling
Timeout
Retry
Authorization
```

---

# 261. MOCK MCP SERVER

JARVIS should maintain mock/test MCP servers.

---

# 262. TEST FIXTURES

Tests should cover:

```text
Valid Server
Malformed Server
Malicious Server
Slow Server
Unavailable Server
Permission-Denied Server
```

---

# 263. CONFORMANCE TEST

A server that fails mandatory protocol requirements cannot be Approved.

---

# 264. SECURITY TEST

A server with unacceptable security behavior cannot be Approved.

---

# 265. LICENSE TEST

A server with incompatible licensing cannot be Approved.

---

# 266. MAINTENANCE TEST

An abandoned server may be rejected or conditionally approved.

---

# 267. SERVER HEALTH

Health should measure:

```text
Connectivity
Latency
Error Rate
Capability Availability
```

---

# 268. TOOL HEALTH

Individual tools may be unavailable even when the server is healthy.

---

# 269. PARTIAL FAILURE

JARVIS should support partial capability failure.

Example:

```text
GitHub MCP
  search → HEALTHY
  issue.create → FAILED
```

---

# 270. PARTIAL AVAILABILITY

The agent should see only currently permitted/available capabilities.

---

# 271. TOOL CATALOG REFRESH

Tool catalogs should refresh according to protocol/cache policy.

---

# 272. CAPABILITY CACHE

JARVIS may cache capability discovery data.

---

# 273. CACHE INVALIDATION ON UPDATE

Server updates must invalidate relevant capability caches.

---

# 274. SERVER DISCONNECT

Disconnected servers should not expose their tools as available.

---

# 275. STALE TOOL

Stale tools must be marked unavailable.

---

# 276. AGENT AWARENESS

Agents should receive current availability information.

---

# 277. TOOL EXECUTION GUARD

Even if an agent selected a tool earlier, the execution layer must re-check:

```text
Availability
Permission
Policy
```

before execution.

---

# 278. TIME-OF-CHECK VS TIME-OF-USE

Security must account for permission changes between planning and execution.

---

# 279. FINAL EXECUTION AUTHORIZATION

Every high-risk external action should have an execution-time authorization check.

---

# 280. USER CONFIRMATION

For destructive operations:

```text
Plan
 ↓
User Confirmation
 ↓
Execution
```

may be required.

---

# 281. AUTOMATION POLICY

User-approved automation may reduce confirmation requirements only within explicitly defined boundaries.

---

# 282. NO UNBOUNDED AUTONOMY

MCP does not give JARVIS unrestricted autonomous access to external systems.

---

# 283. AGENT LOOP

Even with MCP:

```text
Plan
 ↓
Permission
 ↓
Execute
 ↓
Observe
 ↓
Evaluate
```

remains mandatory.

---

# 284. TOOL CHAIN LIMIT

The system should support limits on chained external tool calls.

---

# 285. LOOP DETECTION

Repeated MCP tool calls may indicate an agent loop.

---

# 286. LOOP BREAKER

JARVIS should stop pathological tool loops.

---

# 287. MAXIMUM TOOL DEPTH

Future policy may define maximum tool-chain depth.

---

# 288. MCP CALL BUDGET

A task may have an MCP call budget.

---

# 289. MCP TASK CONTEXT

Each external call should be associated with:

```text
User
Task
Agent
Tool
Server
```

where applicable.

---

# 290. EXTERNAL ACTION JOURNAL

Security-sensitive actions should be recorded.

---

# 291. ACTION REPLAY

Logs should support forensic analysis but must not automatically replay destructive actions.

---

# 292. EXTERNAL SYSTEM STATE

JARVIS should not assume an external system remains unchanged after a previous call.

---

# 293. READ-BEFORE-WRITE

Where appropriate, agents should verify state before mutation.

---

# 294. CONFLICT DETECTION

External mutations should account for concurrent changes.

---

# 295. IDEMPOTENCY KEYS

Where external APIs support idempotency, JARVIS should use them.

---

# 296. TRANSACTION MODEL

MCP does not automatically provide distributed transactions.

---

# 297. PARTIAL FAILURE

If a multi-step workflow partially succeeds:

```text
Successful Actions
+
Failed Actions
+
Recovery Plan
```

must be tracked.

---

# 298. COMPENSATING ACTION

Where possible, JARVIS may perform compensating actions.

---

# 299. NO FALSE ROLLBACK

The system must not claim external rollback if the external service cannot guarantee it.

---

# 300. EXTERNAL INTEGRATION BOUNDARY

The external integration layer is therefore:

```text
Protocol
+
Security
+
Capability
+
Policy
+
Observability
+
Lifecycle
```

not merely a networking library.

---

# 301. APPROVED V1 STACK

Primary:

```text
MCP
+
Official MCP SDK
+
Python MCP Client
+
MCP Gateway
+
MCP Server Registry
+
Central Capability Registry
+
Central Permission System
+
Central Policy Engine
+
Central Observability
+
Central Task System
```

---

# 302. CONDITIONAL STACK

```text
TypeScript MCP SDK
Containerized MCP Servers
Remote MCP Servers
Custom MCP Servers
REST Adapters
GraphQL Adapters
Webhook Integrations
WebSocket Integrations
```

---

# 303. FUTURE STACK

```text
MCP Apps
Advanced Remote MCP Infrastructure
Enterprise Managed Authorization
Distributed MCP Gateway
MCP Marketplace Automation
Advanced Capability Brokerage
```

---

# 304. PROHIBITED DEFAULTS

```text
Arbitrary MCP server execution
Automatic trust of registry entries
Unrestricted server permissions
Unrestricted shell access
Unrestricted filesystem access
Unrestricted network access
Automatic credential exposure
Automatic permission escalation
Legacy HTTP+SSE as a new implementation target
Blind "latest" server versions
Unvalidated external tool outputs
Direct agent-to-server connections
```

---

# 305. MCP SERVER APPROVAL MATRIX

| Component | Direction | Status |
|---|---|---|
| MCP Protocol | `2026-07-28` | APPROVED |
| Python MCP SDK | Primary | APPROVED |
| TypeScript MCP SDK | Supporting | CONDITIONAL |
| STDIO | Local transport | APPROVED |
| Current HTTP transport | Remote transport | APPROVED |
| Legacy HTTP+SSE | Legacy | DEPRECATED / DO NOT TARGET |
| MCP Gateway | JARVIS component | APPROVED |
| MCP Registry | JARVIS component | APPROVED |
| Official MCP Registry | Discovery source | CONDITIONAL |
| Custom MCP Servers | Case-by-case | CONDITIONAL |
| Remote MCP | External services | APPROVED WITH SECURITY |
| Containerized MCP | Isolation | CONDITIONAL |
| MCP Apps | UI extension | FUTURE / CONDITIONAL |
| MCP Tasks | Long-running operations | CONDITIONAL / APPROVED WHERE NEEDED |
| Native REST Adapter | Fallback | APPROVED |
| Generic Webhook | Event integration | APPROVED |
| GraphQL | External integration | CONDITIONAL |
| WebSocket | Realtime integration | CONDITIONAL |

---

# 306. MCP SECURITY MATRIX

| Risk | Default |
|---|---|
| Unknown Server | DENY |
| Unknown Tool | DENY |
| Unknown Capability | DENY |
| Untrusted Resource | RESTRICT |
| Untrusted Prompt | TREAT AS DATA |
| High-risk Tool | APPROVAL/POLICY |
| Destructive Tool | EXPLICIT POLICY |
| Credential Access | RESTRICTED |
| Shell Access | HIGH-RISK |
| Filesystem Write | RESTRICTED |
| Network Access | RESTRICTED |
| Remote MCP | AUTHENTICATED |
| Local STDIO | VALIDATED |
| Tool Schema Failure | DENY |
| Server Integrity Failure | DISABLE |
| Capability Drift | REVIEW |
| Permission Drift | REVIEW |
| Critical Vulnerability | REVOKE/DISABLE |

---

# 307. DEFINITION OF DONE

The MCP integration system is considered implementation-complete when:

```text
[ ] MCP protocol version locked
[ ] Python MCP client implemented
[ ] MCP Gateway implemented
[ ] MCP Server Registry implemented
[ ] MCP server configuration implemented
[ ] Capability discovery implemented
[ ] Tool normalization implemented
[ ] Resource normalization implemented
[ ] Prompt normalization implemented
[ ] Permission integration implemented
[ ] Policy integration implemented
[ ] OAuth/auth integration implemented
[ ] Secret storage implemented
[ ] STDIO support implemented
[ ] Current HTTP transport implemented
[ ] Legacy transport excluded from new architecture
[ ] Timeout handling implemented
[ ] Retry handling implemented
[ ] Circuit breaker implemented
[ ] Rate limiting implemented
[ ] Capability caching implemented
[ ] Tool schema validation implemented
[ ] Result validation implemented
[ ] Prompt injection defenses implemented
[ ] SSRF protection implemented
[ ] Resource size limits implemented
[ ] Task support implemented where required
[ ] Server health implemented
[ ] Capability drift detection implemented
[ ] Permission drift detection implemented
[ ] Audit logging implemented
[ ] Distributed tracing implemented
[ ] MCP contract tests implemented
[ ] Security tests implemented
[ ] Failure tests implemented
[ ] Bootstrap integration implemented
[ ] Manifest integration implemented
[ ] Version Lock integration implemented
[ ] Compliance Checker integration implemented
[ ] System Verification integration implemented
```

---

# 308. FINAL ARCHITECTURAL RULES

### Rule 1

**MCP is JARVIS's primary standardized external capability protocol.**

### Rule 2

**MCP is not JARVIS Core.**

### Rule 3

**MCP is not the Plugin System.**

### Rule 4

**Plugin and MCP architectures remain separate.**

### Rule 5

**Agents must access MCP through the centralized MCP Gateway.**

### Rule 6

**Agents must not create arbitrary MCP connections.**

### Rule 7

**MCP server discovery does not imply trust.**

### Rule 8

**MCP protocol compatibility does not imply security approval.**

### Rule 9

**Every MCP server must have a JARVIS-local identity.**

### Rule 10

**Every MCP server must have an explicit trust state.**

### Rule 11

**Every MCP server must be evaluated before production approval.**

### Rule 12

**Capabilities are deny-by-default.**

### Rule 13

**Permissions are centrally enforced.**

### Rule 14

**High-risk tools require stronger authorization.**

### Rule 15

**Destructive operations require explicit policy.**

### Rule 16

**External MCP content is untrusted data.**

### Rule 17

**MCP tool descriptions are not trusted instructions.**

### Rule 18

**MCP prompts cannot override JARVIS system/security policy.**

### Rule 19

**MCP results must be validated before entering agent context.**

### Rule 20

**MCP results must not automatically enter long-term memory.**

### Rule 21

**External credentials must never be exposed unnecessarily.**

### Rule 22

**Secrets must be stored centrally.**

### Rule 23

**Remote MCP connections require secure authentication/transport.**

### Rule 24

**STDIO servers are validated even when local.**

### Rule 25

**Legacy HTTP+SSE is not a target for new implementations.**

### Rule 26

**MCP protocol version must be explicitly locked.**

### Rule 27

**Exact SDK versions belong to Version Lock.**

### Rule 28

**Server versions should be pinned for reproducible production deployments.**

### Rule 29

**Capability drift must be detected.**

### Rule 30

**Permission drift must be detected.**

### Rule 31

**Schema drift must be detected.**

### Rule 32

**Server failures must not normally crash JARVIS Core.**

### Rule 33

**MCP calls must be observable.**

### Rule 34

**Security-sensitive MCP actions must be auditable.**

### Rule 35

**Retries must be bounded.**

### Rule 36

**Non-idempotent operations must not be blindly retried.**

### Rule 37

**MCP tasks must respect JARVIS task and timeout policies.**

### Rule 38

**External resources must be size and content controlled.**

### Rule 39

**SSRF and network abuse must be prevented.**

### Rule 40

**MCP servers may be revoked after approval.**

### Rule 41

**Approved registry membership does not grant unlimited permissions.**

### Rule 42

**MCP tools must be normalized into the JARVIS capability/tool model.**

### Rule 43

**MCP and Plugin capabilities should eventually share the central capability registry.**

### Rule 44

**MCP and Plugin permissions should share central policy enforcement.**

### Rule 45

**External integrations must remain replaceable.**

### Rule 46

**JARVIS Core must not become dependent on a single external MCP server.**

### Rule 47

**Fallback adapters may exist where MCP is unavailable or unsuitable.**

### Rule 48

**MCP is preferred for standardized external capability integration, not mandated for every integration.**

### Rule 49

**External system state must never be assumed immutable.**

### Rule 50

**JARVIS must distinguish planning from final execution authorization.**

---

# 309. VERSION LOCK INTEGRATION

Version Lock will eventually contain:

```text
MCP Specification
MCP Python SDK
Supporting MCP Libraries
Approved MCP Server Versions
Server Artifact Hashes
Container Image Digests
```

Conceptually:

```yaml
mcp:
  protocol: 2026-07-28

  client:
    sdk: ...

  servers:
    github.primary:
      version: ...
      digest: ...
```

Exact versions remain intentionally deferred.

---

# 310. MANIFEST INTEGRATION

The global Manifest will eventually define:

```yaml
mcp:
  servers:
    - id: github.primary
      enabled: true

    - id: calendar.personal
      enabled: true
```

and associated:

```text
Permissions
Capabilities
Transport
Endpoint
Configuration
```

---

# 311. BOOTSTRAP INTEGRATION

Bootstrap will eventually:

```text
Read MCP Configuration
        ↓
Validate Server
        ↓
Resolve Artifact
        ↓
Verify Integrity
        ↓
Install / Configure
        ↓
Configure Credentials
        ↓
Register
        ↓
Discover Capabilities
        ↓
Health Check
        ↓
Enable
```

---

# 312. COMPLIANCE INTEGRATION

Compliance Checker will verify:

```text
Installed Server
        =
Manifest
        =
Version Lock
        =
Approved MCP Server
```

where the server is managed by the production configuration.

---

# 313. SYSTEM VERIFICATION

System Verification must confirm:

```text
Server Reachable
Server Authenticated
Capabilities Discoverable
Tools Valid
Permissions Enforced
Requests Execute
Results Validate
Failures Recover
Audit Works
Disable Works
Restart Works
```

---

# 314. NEXT-PHASE HANDOFF

This document feeds into:

```text
13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md
            │
            ▼
14_SECURITY_STACK.md
            │
            ▼
15_DEVOPS_AND_DEPLOYMENT_STACK.md
            │
            ▼
16_MONITORING_AND_OBSERVABILITY_STACK.md
            │
            ▼
17_TESTING_AND_QUALITY_ASSURANCE_STACK.md
            │
            ▼
18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md
            │
            ▼
19_APPROVED_MODELS.md
            │
            ▼
20_APPROVED_MCP_SERVERS.md
            │
            ▼
21_APPROVED_SOFTWARE_MATRIX.md
            │
            ▼
VERSION LOCK v1
            │
            ▼
MANIFEST v1
            │
            ▼
BOOTSTRAP v1
```

---

# 315. FINAL DECISION

```text
========================================================
       JARVIS MCP & EXTERNAL INTEGRATION STACK
                       FINAL v1
========================================================

PRIMARY EXTERNAL PROTOCOL:
    Model Context Protocol
    APPROVED

TARGET SPECIFICATION:
    MCP 2026-07-28
    APPROVED

PRIMARY CLIENT RUNTIME:
    Python
    APPROVED

MCP CLIENT:
    APPROVED

MCP GATEWAY:
    APPROVED

MCP SERVER REGISTRY:
    APPROVED

CAPABILITY REGISTRY:
    APPROVED

CENTRAL PERMISSION SYSTEM:
    APPROVED

CENTRAL POLICY ENGINE:
    APPROVED

CENTRAL OBSERVABILITY:
    APPROVED

STDIO:
    APPROVED FOR LOCAL MCP

CURRENT HTTP TRANSPORT:
    APPROVED FOR REMOTE MCP

LEGACY HTTP+SSE:
    DEPRECATED
    NOT A NEW IMPLEMENTATION TARGET

MCP TASKS:
    CONDITIONAL / APPROVED WHERE REQUIRED

MCP APPS:
    FUTURE / CONDITIONAL

OFFICIAL MCP REGISTRY:
    DISCOVERY SOURCE
    NOT AUTOMATIC TRUST

CUSTOM MCP SERVERS:
    CONDITIONAL

REMOTE MCP:
    APPROVED WITH SECURITY CONTROLS

CONTAINERIZED MCP:
    CONDITIONAL

REST ADAPTERS:
    APPROVED FALLBACK

WEBHOOK INTEGRATIONS:
    APPROVED

GRAPHQL:
    CONDITIONAL

WEBSOCKET:
    CONDITIONAL

========================================================

PRIMARY ARCHITECTURE:

Agent
  ↓
Capability Registry
  ↓
Permission
  ↓
Policy
  ↓
MCP Gateway
  ↓
MCP Client
  ↓
MCP Server
  ↓
External System
  ↓
Validated Result
  ↓
Agent

========================================================

SECURITY PRINCIPLE:

MCP COMPATIBILITY
        ≠
TRUST

========================================================

ARCHITECTURAL PRINCIPLE:

MCP PROVIDES INTEROPERABILITY.

JARVIS PROVIDES:
SECURITY
POLICY
PERMISSIONS
STATE
OBSERVABILITY
ORCHESTRATION

========================================================
```

# 316. ARCHITECTURAL SUMMARY

JARVIS'in external integration architecture v1 şu prensip üzerine kurulacaktır:

```text
                         JARVIS
                            │
                    ┌───────┴────────┐
                    │                │
                 PLUGIN              MCP
                    │                │
              JARVIS-NATIVE      EXTERNAL
               EXTENSION         PROTOCOL
                    │                │
                    └───────┬────────┘
                            │
                     CAPABILITY LAYER
                            │
                       PERMISSION
                            │
                          POLICY
                            │
                        EXECUTION
                            │
                      OBSERVABILITY
```

MCP'nin görevi JARVIS'in kendisi olmak değil, **JARVIS ile dış dünya arasında standartlaştırılmış bir capability boundary oluşturmak** olacaktır.

Dolayısıyla nihai v1 kararı:

> **JARVIS MCP & External Integration Stack = MCP 2026-07-28 tabanlı, Python-first, Gateway-controlled, capability-oriented, permission-enforced, policy-governed, observable ve version-locked bir dış entegrasyon platformudur.**

En önemli sınır:

```text
MCP SERVER
    ≠
TRUSTED JARVIS COMPONENT
```

ve:

```text
MCP CAPABILITY
    ↓
MUST PASS
    ↓
PERMISSION + POLICY
```

olacaktır.