# 20 — APPROVED MCP SERVERS

**Document ID:** JAS-AS-20  
**Document:** `20_APPROVED_MCP_SERVERS.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED MCP GOVERNANCE SPECIFICATION  
**Primary Domain:** Model Context Protocol, External Integrations, Tool Servers, Resources, Capability Extensions and Remote Service Access  
**Depends On:** JAS v1, `12_PLUGIN_AND_EXTENSION_STACK.md`, `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`, `14_SECURITY_STACK.md`, `15_DEVOPS_AND_DEPLOYMENT_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`, `19_APPROVED_MODELS.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, MCP Registry, MCP Gateway, Security Policy, System Verification, Runtime Configuration

---

# 1. PURPOSE

This document defines the approved MCP server architecture and governance policy for JARVIS.

It does not merely list MCP servers.

It defines:

```text
Which MCP servers may be used
+
What capabilities they expose
+
What trust level they require
+
What permissions they receive
+
How they are installed
+
How they are versioned
+
How they are verified
+
How they are monitored
+
How they are isolated
+
How they are removed
```

---

# 2. CORE PRINCIPLE

MCP servers are external capability providers.

They are not part of the JARVIS reasoning core.

The architectural relationship is:

```text
JARVIS Core
    ↓
MCP Gateway / Client
    ↓
Security Policy
    ↓
Approved MCP Server
    ↓
External Capability
```

---

# 3. MCP IS NOT JARVIS

MCP does not replace:

```text
Agents
Memory
Planning
Security
Plugins
Model Router
Core Runtime
```

MCP provides a standardized integration boundary.

---

# 4. MCP SERVER TRUST MODEL

Every MCP server is treated as an independently governed component.

The fact that a server is published in an official or community registry does not automatically make it trusted for unrestricted production use.

---

# 5. MCP PRIMITIVES

JARVIS recognizes the MCP primitives:

```text
Tools
Resources
Prompts
```

Tools are executable capabilities.

Resources provide contextual data.

Prompts provide reusable interaction templates.

---

# 6. TOOL TRUST

Tools are the highest-risk MCP primitive because they can perform actions.

A tool may:

```text
Read
Write
Delete
Execute
Send
Modify
Create
```

depending on the server.

---

# 7. RESOURCE TRUST

Resources are generally lower risk than tools but may still expose sensitive information.

---

# 8. PROMPT TRUST

Prompts are not treated as security policies.

A prompt supplied by an MCP server must never override JARVIS security policy.

---

# 9. MCP SERVER CATEGORIES

JARVIS classifies MCP servers into:

```text
1. Filesystem
2. Git / Source Control
3. Browser / Web
4. Database
5. Developer Tools
6. Documentation / Knowledge
7. Memory
8. Monitoring
9. Infrastructure
10. Productivity
11. Communication
12. External APIs
13. Research
14. System Administration
15. Testing
16. Experimental
```

---

# 10. APPROVAL STATES

Every MCP server has one of:

```text
APPROVED
CONDITIONALLY APPROVED
EXPERIMENTAL
EVALUATION
DEPRECATED
REJECTED
```

---

# 11. APPROVED

Approved servers may be used in production subject to their declared permissions.

---

# 12. CONDITIONALLY APPROVED

Conditionally approved servers require additional restrictions such as:

```text
Sandboxing
Read-only mode
Specific directory
Specific repository
Specific network
User confirmation
Manual credential setup
```

---

# 13. EXPERIMENTAL

Experimental servers may be used only in isolated development/evaluation environments.

They must not silently become production dependencies.

---

# 14. EVALUATION

Servers under evaluation may be tested but are not production-authorized.

---

# 15. DEPRECATED

Deprecated servers remain documented for migration and compatibility but should not be used for new deployments.

---

# 16. REJECTED

Rejected servers must not be installed or executed by production JARVIS.

The reason must be recorded.

---

# 17. OFFICIAL REGISTRY

The official MCP Registry is a discovery and publication mechanism.

It is not itself a security approval mechanism.

The registry provides server metadata and version information and supports server discovery and version history.

---

# 18. REGISTRY PRINCIPLE

JARVIS should use the official registry as a discovery/provenance source where appropriate.

It must not interpret:

```text
Published
```

as:

```text
Approved
```

---

# 19. SOURCE PROVENANCE

Every approved MCP server must have a known source repository or official distribution source.

---

# 20. SOURCE VERIFICATION

The following should be verified:

```text
Repository
Organization
Maintainer
Release
Package
Checksum
License
```

where applicable.

---

# 21. OFFICIAL REFERENCE SERVERS

The official `modelcontextprotocol/servers` repository contains reference implementations maintained by the MCP project.

These are valuable reference implementations but are not automatically production-ready.

---

# 22. REFERENCE IMPLEMENTATION POLICY

A reference server must undergo JARVIS security and operational review before production use.

---

# 23. OFFICIAL SERVER BASELINE

The initial official-reference baseline considered by JARVIS includes:

```text
Filesystem
Git
Fetch
Time
Memory
Sequential Thinking
Everything
```

Not all of these are production-approved.

---

# 24. PRODUCTION DISTINCTION

The following distinction is mandatory:

```text
Reference Implementation
        ≠
Production Approved Server
```

---

# 25. FILESYSTEM SERVER

The filesystem MCP server provides filesystem-oriented capabilities.

It is potentially high risk because filesystem access can expose:

```text
Credentials
Documents
Source Code
Browser Data
Personal Data
System Files
```

---

# 26. FILESYSTEM STATUS

```text
CONDITIONALLY APPROVED
```

---

# 27. FILESYSTEM RESTRICTION

Filesystem access must be restricted to explicit allowed roots.

Example:

```text
JAS_ALLOWED_ROOTS
```

---

# 28. NO UNRESTRICTED FILESYSTEM

The JARVIS MCP layer must not expose the entire host filesystem by default.

---

# 29. FILESYSTEM READ/WRITE SEPARATION

Where possible:

```text
Read
```

and:

```text
Write
```

permissions must be independently controlled.

---

# 30. FILESYSTEM DELETE

Delete operations require a higher permission level than read operations.

---

# 31. FILESYSTEM EXECUTION

Filesystem access must not imply shell execution.

---

# 32. PATH TRAVERSAL

Path traversal must be prevented at the MCP policy layer and, where possible, inside the server.

---

# 33. SYMLINK POLICY

Symlink resolution must not allow escaping an approved filesystem root.

---

# 34. FILESYSTEM SENSITIVE PATHS

The following should be blocked by default:

```text
SSH credentials
Browser credential stores
OS credential stores
Environment secret files
Cloud credential directories
Password databases
Private keys
```

---

# 35. GIT SERVER

The official Git MCP server provides Git-oriented capabilities.

---

# 36. GIT STATUS

```text
CONDITIONALLY APPROVED
```

---

# 37. GIT REPOSITORY BOUNDARY

Git operations must be restricted to approved repositories.

---

# 38. GIT READ OPERATIONS

Read operations are lower risk:

```text
Status
Log
Diff
Show
Branch Inspection
```

---

# 39. GIT WRITE OPERATIONS

Write operations require elevated permissions:

```text
Commit
Checkout
Merge
Reset
Branch Creation
```

---

# 40. GIT DESTRUCTIVE OPERATIONS

Operations capable of losing data require explicit policy controls.

Examples:

```text
Reset
Clean
Force Operations
Checkout Overwrite
```

---

# 41. GIT REMOTE OPERATIONS

Remote operations may affect external repositories.

They require separate network and authorization policy.

---

# 42. GIT SECURITY

The Git server must be reviewed against path validation and command-injection vulnerabilities before every production upgrade.

---

# 43. FETCH SERVER

The official Fetch server provides HTTP retrieval capabilities.

---

# 44. FETCH STATUS

```text
CONDITIONALLY APPROVED
```

---

# 45. FETCH RISK

HTTP fetching creates a network boundary.

Potential risks include:

```text
SSRF
Internal Network Access
Credential Leakage
Malicious Content
Prompt Injection
Large Downloads
Resource Exhaustion
```

---

# 46. FETCH NETWORK POLICY

Fetch requests must pass network policy.

---

# 47. PRIVATE NETWORK

Access to:

```text
localhost
127.0.0.1
Private IP ranges
Cloud metadata endpoints
Internal DNS
```

must be blocked unless explicitly permitted.

---

# 48. FETCH CONTENT LIMIT

Responses must have:

```text
Maximum Size
Timeout
Redirect Limit
Content-Type Policy
```

---

# 49. FETCH DOWNLOADS

Arbitrary binary downloads must not be enabled by default.

---

# 50. FETCH PROMPT INJECTION

Web content must be treated as untrusted data.

---

# 51. FETCH → LLM BOUNDARY

Fetched content must never automatically become trusted instructions.

---

# 52. TIME SERVER

The official Time server provides time-related functionality.

---

# 53. TIME STATUS

```text
APPROVED
```

subject to minimal operational review.

---

# 54. TIME RISK

The Time server has a comparatively small security surface.

---

# 55. MEMORY SERVER

The official Memory server demonstrates MCP-based memory functionality.

---

# 56. MEMORY STATUS

```text
CONDITIONALLY APPROVED
```

---

# 57. MEMORY SERVER VS JARVIS MEMORY

The MCP Memory server must not automatically become the authoritative JARVIS memory architecture.

---

# 58. MEMORY AUTHORITY

JARVIS memory remains governed by:

```text
05_MEMORY_AND_VECTOR_DATABASE
```

and the dedicated JARVIS memory architecture.

---

# 59. MEMORY MCP USE

The Memory MCP server may be used for:

```text
Experimental Memory
Prototype Workflows
External MCP Compatibility
```

until it is proven appropriate for production memory.

---

# 60. SEQUENTIAL THINKING SERVER

The Sequential Thinking server demonstrates structured reasoning workflows.

---

# 61. SEQUENTIAL THINKING STATUS

```text
EXPERIMENTAL
```

---

# 62. REASONING SERVER PRINCIPLE

An MCP reasoning server must not become a security authority.

---

# 63. EVERYTHING SERVER

The Everything server is a protocol demonstration/test server.

---

# 64. EVERYTHING STATUS

```text
EVALUATION ONLY
```

---

# 65. EVERYTHING SERVER PURPOSE

It is useful for:

```text
Protocol Testing
Client Testing
Integration Testing
Capability Testing
```

but not as a production capability provider.

---

# 66. TEST SERVER POLICY

Test MCP servers must not be enabled in production.

---

# 67. BROWSER MCP

Browser MCP servers can expose:

```text
Navigation
DOM
Screenshots
Console
Network
Interaction
```

---

# 68. BROWSER MCP STATUS

```text
CONDITIONALLY APPROVED
```

---

# 69. BROWSER MCP TRUST

Browser MCP has high capability because it can interact with authenticated external services.

---

# 70. BROWSER SESSION

Browser sessions must be isolated.

---

# 71. AUTHENTICATED SESSION

Authenticated browser access must require explicit permission.

---

# 72. COOKIES

Cookies and session tokens must never be exposed as ordinary model-readable resources.

---

# 73. PASSWORDS

Passwords must not be provided to the model through MCP.

---

# 74. DOWNLOADS

Downloads must be sandboxed and size-limited.

---

# 75. UPLOADS

Uploads require explicit policy because they can exfiltrate local data.

---

# 76. BROWSER DOMAIN POLICY

JARVIS should support domain allowlists and denylists.

---

# 77. BROWSER ACTION POLICY

High-risk actions should require confirmation:

```text
Purchase
Send Message
Delete
Account Changes
Financial Actions
```

---

# 78. DATABASE MCP

Database MCP servers expose database operations.

---

# 79. DATABASE STATUS

```text
CONDITIONALLY APPROVED
```

---

# 80. DATABASE READ/WRITE SEPARATION

Database access must distinguish:

```text
SELECT
```

from:

```text
INSERT / UPDATE / DELETE / DDL
```

---

# 81. DATABASE READ-ONLY DEFAULT

Read-only database access should be the default.

---

# 82. DATABASE WRITE

Write access requires explicit authorization.

---

# 83. DATABASE ADMIN

Database administrative operations must not be available to ordinary JARVIS agents.

---

# 84. SQL INJECTION

Parameterized queries or equivalent safe mechanisms are mandatory.

---

# 85. DATABASE SECRET

Database credentials must be stored in the approved secret management system.

---

# 86. DATABASE NETWORK

Database servers must not expose unrestricted network access.

---

# 87. DOCKER MCP

Docker-oriented MCP servers can control containers and infrastructure.

---

# 88. DOCKER STATUS

```text
CONDITIONALLY APPROVED
```

---

# 89. DOCKER RISK

Docker control can become host-level control depending on configuration.

---

# 90. DOCKER SOCKET

Direct unrestricted access to the Docker socket is prohibited by default.

---

# 91. CONTAINER POLICY

Allowed operations should be explicitly defined:

```text
List
Inspect
Logs
Start
Stop
Restart
```

before:

```text
Create
Delete
Exec
```

---

# 92. CONTAINER EXEC

Container shell execution is privileged.

---

# 93. HOST ESCAPE

Docker configuration must be reviewed for host escape risks.

---

# 94. GITHUB MCP

GitHub MCP provides repository, issue, pull request and related capabilities.

---

# 95. GITHUB STATUS

```text
CONDITIONALLY APPROVED
```

---

# 96. GITHUB AUTHORIZATION

GitHub access must use narrowly scoped credentials.

---

# 97. GITHUB TOKEN

Tokens must never be passed into model prompts.

---

# 98. GITHUB READ

Read-only GitHub access is preferred for research.

---

# 99. GITHUB WRITE

Write operations require explicit authorization.

---

# 100. GITHUB DESTRUCTIVE OPERATIONS

Repository deletion, force operations and destructive administrative actions require highest-level authorization.

---

# 101. GITHUB PULL REQUESTS

Creating or modifying a PR is a consequential action and should be auditable.

---

# 102. GITHUB ACTIONS

Triggering workflows may execute code.

It requires elevated permission.

---

# 103. GITHUB SECRETS

GitHub secrets must never be returned to the model.

---

# 104. MCP SERVER TRUST TIERS

JARVIS defines:

```text
T0 — Informational
T1 — Read-only Local
T2 — Read-only External
T3 — Controlled Write
T4 — Privileged
T5 — Administrative
```

---

# 105. T0 INFORMATIONAL

Examples:

```text
Time
Static Documentation
Public Metadata
```

---

# 106. T1 READ-ONLY LOCAL

Examples:

```text
Approved project files
Git read operations
Local documentation
```

---

# 107. T2 READ-ONLY EXTERNAL

Examples:

```text
Public Web Fetch
Public GitHub Data
Public APIs
```

---

# 108. T3 CONTROLLED WRITE

Examples:

```text
Git Commit
Issue Creation
Database Write
File Write
```

---

# 109. T4 PRIVILEGED

Examples:

```text
Container Execution
System Configuration
Authenticated Browser Actions
Credentialed External APIs
```

---

# 110. T5 ADMINISTRATIVE

Examples:

```text
Infrastructure Administration
Credential Management
Security Policy Changes
Host-Level Operations
```

T5 should be extremely rare.

---

# 111. DEFAULT TRUST

New MCP servers start at:

```text
UNTRUSTED
```

until reviewed.

---

# 112. DEFAULT PERMISSIONS

New MCP servers receive:

```text
NO PRIVILEGES
```

until explicitly granted.

---

# 113. CAPABILITY GRANTS

Permissions must be capability-specific.

---

# 114. LEAST PRIVILEGE

Every MCP server receives the minimum privileges necessary.

---

# 115. PRINCIPLE OF SEPARATION

A browser server does not automatically receive filesystem access.

A Git server does not automatically receive shell access.

A database server does not automatically receive browser access.

---

# 116. MCP SERVER IDENTITY

Each installed server must have a stable identity:

```text
Server Name
Publisher
Repository
Version
Revision
Transport
```

---

# 117. MCP VERSION

The server package version must be tracked.

---

# 118. MCP PROTOCOL VERSION

The MCP protocol version must be tracked separately from server version.

---

# 119. PROTOCOL NEGOTIATION

Client and server protocol versions must be negotiated according to MCP specification rules.

---

# 120. CURRENT PROTOCOL POLICY

The implementation must support the MCP protocol version selected by the JAS-approved MCP SDK/runtime.

The exact protocol version belongs in Version Lock.

---

# 121. TRANSPORTS

JARVIS recognizes:

```text
stdio
Streamable HTTP
```

as primary transport classes.

Legacy SSE should not be introduced for new JARVIS integrations unless compatibility requires it.

---

# 122. STDIO

stdio is preferred for local, single-host MCP servers where practical.

---

# 123. STDIO SECURITY

stdio servers should run with the minimum OS permissions necessary.

---

# 124. STREAMABLE HTTP

Streamable HTTP is appropriate for remote or separately deployed MCP services.

---

# 125. HTTP SECURITY

Remote MCP servers require:

```text
TLS
Authentication
Authorization
Origin Policy
Rate Limiting
Logging
```

where applicable.

---

# 126. REMOTE MCP

Remote MCP servers are treated as network services.

---

# 127. LOCAL MCP

Local MCP servers are treated as local processes with host-level security implications.

---

# 128. LOCAL PROCESS ISOLATION

Where practical, local MCP servers should run under a dedicated service account or sandbox.

---

# 129. PROCESS ENVIRONMENT

MCP processes must receive only required environment variables.

---

# 130. SECRET INJECTION

Secrets should be injected at runtime rather than embedded in MCP configuration.

---

# 131. NO SECRETS IN CONFIG

MCP configuration files must not contain plaintext credentials.

---

# 132. SECRET REFERENCES

Configuration should contain secret references/identifiers instead of secret values.

---

# 133. MCP AUTHENTICATION

Remote MCP servers must use approved authentication mechanisms.

---

# 134. MCP AUTHORIZATION

Authentication does not imply authorization.

---

# 135. TOOL AUTHORIZATION

Each tool invocation must be evaluated against the permission policy.

---

# 136. USER APPROVAL

High-impact tool actions may require explicit user confirmation.

---

# 137. CONFIRMATION POLICY

Confirmation should be based on:

```text
Risk
Reversibility
Financial Impact
Data Sensitivity
External Visibility
```

---

# 138. REVERSIBILITY

Irreversible operations receive higher risk classification.

---

# 139. EXTERNAL SIDE EFFECTS

Actions affecting third parties require higher authorization.

---

# 140. MCP PROMPT INJECTION

MCP resources and tool outputs are untrusted input.

---

# 141. TOOL OUTPUT TRUST

Tool output must not automatically become system instructions.

---

# 142. RESOURCE TRUST

Resources may contain malicious or misleading instructions.

---

# 143. OUTPUT SANITIZATION

Where applicable, outputs should be normalized and bounded before entering the model context.

---

# 144. CONTENT SIZE

MCP outputs must have size limits.

---

# 145. PAGINATION

Large datasets should use pagination rather than unlimited output.

---

# 146. TIMEOUT

Every MCP operation requires a timeout.

---

# 147. RETRY

Retries must be bounded and operation-aware.

---

# 148. IDEMPOTENCY

Write operations should be idempotent where practical.

---

# 149. DUPLICATE ACTIONS

The system must prevent duplicate external side effects caused by retries.

---

# 150. CIRCUIT BREAKER

Repeated MCP failures may trigger a circuit breaker.

---

# 151. RATE LIMITING

Remote MCP servers must support or be protected by rate limits.

---

# 152. RESOURCE EXHAUSTION

MCP servers must be protected against:

```text
Memory Exhaustion
CPU Exhaustion
Disk Exhaustion
Network Flooding
Huge Responses
Infinite Loops
```

---

# 153. MCP SERVER HEALTH

Health should be observable through:

```text
Availability
Latency
Error Rate
Process Status
Resource Usage
```

---

# 154. MCP SERVER LOGGING

Logs must include:

```text
Server ID
Version
Tool
Latency
Outcome
Error Class
```

without exposing secrets.

---

# 155. AUDIT LOGGING

High-risk actions should produce audit events.

---

# 156. AUDIT EVENT

Conceptually:

```text
timestamp
actor
agent
server
tool
resource
action
authorization
result
```

---

# 157. PROMPT LOGGING

MCP prompts should not be logged unnecessarily when they contain sensitive data.

---

# 158. RESOURCE LOGGING

Sensitive resource contents should not be copied into logs.

---

# 159. MCP SERVER TELEMETRY

MCP servers should expose metrics where practical.

---

# 160. MCP LATENCY

Measure:

```text
Connection
Request
Server Processing
Response
Total
```

---

# 161. MCP ERROR CLASSES

Errors should be classified:

```text
TIMEOUT
AUTHENTICATION
AUTHORIZATION
NOT_FOUND
INVALID_ARGUMENT
RATE_LIMIT
SERVER_ERROR
NETWORK
POLICY_BLOCK
```

---

# 162. MCP MONITORING

MCP monitoring integrates with `16_MONITORING_AND_OBSERVABILITY_STACK.md`.

---

# 163. MCP TESTING

MCP testing integrates with `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`.

---

# 164. MCP DEPLOYMENT

MCP deployment integrates with `15_DEVOPS_AND_DEPLOYMENT_STACK.md`.

---

# 165. MCP BUILD

MCP package installation integrates with `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`.

---

# 166. MCP SECURITY

MCP security integrates with `14_SECURITY_STACK.md`.

---

# 167. MCP MODEL RELATIONSHIP

The model may request an MCP tool.

The model does not own the tool.

---

# 168. MCP CONTROL FLOW

```text
User
 ↓
Agent
 ↓
Model
 ↓
Tool Selection
 ↓
MCP Gateway
 ↓
Policy
 ↓
MCP Server
 ↓
External System
```

---

# 169. POLICY ENFORCEMENT

The policy layer must sit between model intent and MCP execution.

---

# 170. NO DIRECT MODEL → SERVER TRUST

The model must not be able to bypass the MCP Gateway.

---

# 171. MCP GATEWAY

The JARVIS MCP Gateway should centralize:

```text
Discovery
Registration
Authentication
Authorization
Routing
Timeout
Retry
Audit
Telemetry
```

---

# 172. MCP REGISTRY VS JARVIS REGISTRY

The official MCP Registry is external.

JARVIS maintains its own approved inventory.

---

# 173. JARVIS MCP REGISTRY

Conceptually:

```text
Approved Server
Capability
Version
Revision
Transport
Permissions
Status
Risk
```

---

# 174. REGISTRY ENTRY

Minimum metadata:

```text
server_id
name
publisher
source
version
revision
license
transport
capabilities
trust_tier
permissions
status
```

---

# 175. SERVER REVISION

Production deployments should pin an immutable release/revision where possible.

---

# 176. `latest`

Production MCP configurations must not rely on mutable `latest`.

---

# 177. PACKAGE DIGEST

Containerized/package-based servers should use immutable digests where practical.

---

# 178. MCP VERSION LOCK

Exact server versions belong in Version Lock.

---

# 179. MCP MANIFEST

Manifest defines required/optional MCP servers.

---

# 180. MCP BOOTSTRAP

Bootstrap installs and verifies required MCP servers.

---

# 181. MCP SYSTEM VERIFICATION

Verification must confirm:

```text
Installed
Correct Version
Correct Revision
Correct Transport
Correct Permissions
Healthy
```

---

# 182. MCP INSTALLATION

Installation must use approved sources.

---

# 183. PACKAGE SOURCE

Approved sources include:

```text
Official Repository
Official Package Registry
Approved Container Registry
Official MCP Registry Metadata
```

subject to provenance verification.

---

# 184. UNVERIFIED COMMUNITY SERVER

A community server is not production-approved solely because it exists in an MCP registry.

---

# 185. COMMUNITY SERVER APPROVAL

Requires:

```text
Source Review
Security Review
License Review
Maintenance Review
Integration Test
```

---

# 186. MAINTAINER HEALTH

Evaluate:

```text
Release Activity
Issue Response
Security History
Repository Activity
Documentation
```

---

# 187. DEPENDENCY REVIEW

MCP server dependencies must be reviewed for supply-chain risk.

---

# 188. TRANSITIVE DEPENDENCIES

Approval applies to important transitive dependencies as well.

---

# 189. VULNERABILITY SCANNING

Production MCP packages should be scanned for known vulnerabilities.

---

# 190. MALICIOUS PACKAGE DEFENSE

Package names and publishers must be verified to prevent typosquatting.

---

# 191. MCP SERVER NAME

The canonical server identity must not be inferred solely from a package name.

---

# 192. PACKAGE → REPOSITORY

Package provenance should map to an expected repository.

---

# 193. REPOSITORY → PUBLISHER

Repository ownership must be verified.

---

# 194. RELEASE SIGNING

Signed releases are preferred where available.

---

# 195. ARTIFACT DIGEST

Artifact digests should be recorded for reproducibility.

---

# 196. CONTAINERIZED MCP

Containerized servers should use:

```text
Non-root
Read-only filesystem where possible
Dropped capabilities
Resource limits
Network restrictions
```

---

# 197. CONTAINER NETWORK

MCP containers should receive only required network access.

---

# 198. HOST NETWORK

Host networking is prohibited by default.

---

# 199. PRIVILEGED CONTAINER

Privileged containers require explicit security approval.

---

# 200. HOST MOUNTS

Host filesystem mounts require explicit allowlisting.

---

# 201. MCP SANDBOX

High-risk MCP servers should be sandboxed.

---

# 202. SANDBOX OPTIONS

Depending on platform:

```text
Container
VM
Dedicated User
OS Sandbox
Restricted Network Namespace
```

---

# 203. MCP PROCESS USER

Servers should not run as administrator/root unless technically unavoidable and explicitly approved.

---

# 204. WINDOWS

Because JARVIS must support desktop environments, Windows-specific process and filesystem security must be considered.

---

# 205. CROSS-PLATFORM

MCP server approval should document:

```text
Windows
Linux
macOS
```

support where relevant.

---

# 206. PLATFORM-SPECIFIC SERVER

A server may be conditionally approved for one platform.

---

# 207. MCP SERVER CONFIGURATION

Configuration should be declarative and version-controlled.

---

# 208. SECRET CONFIGURATION

Secret values must be externalized.

---

# 209. ENVIRONMENT CONFIGURATION

Environment-specific values belong outside the immutable server definition.

---

# 210. DEVELOPMENT CONFIGURATION

Development MCP servers must be isolated from production credentials.

---

# 211. STAGING CONFIGURATION

Staging should use staging credentials and endpoints.

---

# 212. PRODUCTION CONFIGURATION

Production must use production credentials with minimum scope.

---

# 213. MCP ENVIRONMENTS

```text
Development
Testing
Staging
Production
```

must have separate MCP configurations.

---

# 214. MCP PROFILE

JARVIS may define:

```text
OFFLINE
LOCAL
DEVELOPMENT
PRODUCTION
HIGH_SECURITY
```

profiles.

---

# 215. OFFLINE PROFILE

No external MCP server requiring network access should be enabled.

---

# 216. HIGH SECURITY PROFILE

Only explicitly approved low-risk MCP capabilities should be enabled.

---

# 217. MCP DISCOVERY

Dynamic MCP discovery may exist, but discovered servers must remain untrusted until approved.

---

# 218. DYNAMIC REGISTRATION

JARVIS must not automatically install a discovered MCP server.

---

# 219. AUTO-INSTALL PROHIBITION

Model-generated requests must never trigger unrestricted MCP package installation.

---

# 220. USER-INVOKED INSTALLATION

MCP installation should be initiated through explicit user/admin action or controlled bootstrap configuration.

---

# 221. MCP UPDATE

Updates must follow:

```text
Research
↓
Evaluation
↓
Security
↓
Approval
↓
Version Lock
↓
Deployment
```

---

# 222. MCP PATCH

Security patches may receive expedited review.

---

# 223. MCP BREAKING UPDATE

Breaking changes require compatibility testing.

---

# 224. MCP PROTOCOL UPDATE

A protocol update must not be assumed compatible with every server.

---

# 225. MCP SERVER API

Tool schemas are part of the compatibility contract.

---

# 226. TOOL SCHEMA CHANGE

A changed tool schema requires integration testing.

---

# 227. RESOURCE SCHEMA CHANGE

Resource schema changes require consumer compatibility testing.

---

# 228. PROMPT CHANGE

Prompt changes may alter agent behavior and should be evaluated.

---

# 229. MCP CONTRACT TESTS

Every production server should have contract tests for:

```text
Tools
Resources
Prompts
Errors
Authentication
```

as applicable.

---

# 230. MCP SMOKE TEST

Minimum:

```text
Connect
Initialize/Negotiate
List Capabilities
Execute Safe Operation
Validate Result
Disconnect
```

---

# 231. MCP FAILURE TEST

Test:

```text
Timeout
Server Crash
Invalid Input
Network Failure
Permission Denied
Malformed Output
```

---

# 232. MCP SECURITY TEST

Test:

```text
Path Traversal
Unauthorized Access
Credential Leakage
Injection
Oversized Input
Oversized Output
```

where relevant.

---

# 233. MCP ADVERSARIAL TESTING

High-risk servers should receive adversarial tests.

---

# 234. MCP REGRESSION

Every server upgrade should run regression tests.

---

# 235. MCP SERVER HEALTH CHECK

Health checks should not require destructive operations.

---

# 236. MCP STARTUP

Server startup must be deterministic.

---

# 237. MCP SHUTDOWN

Servers must support controlled shutdown where practical.

---

# 238. MCP CRASH RECOVERY

The MCP Gateway should restart failed local servers where appropriate.

---

# 239. CRASH LOOP

Repeated crashes must trigger disablement rather than infinite restart loops.

---

# 240. MCP RESOURCE LIMITS

Each server may define:

```text
CPU
RAM
Disk
Network
Process Count
```

limits.

---

# 241. MCP SERVER PRIORITY

Interactive MCP servers receive higher scheduling priority than background integrations.

---

# 242. BACKGROUND MCP

Background MCP servers may handle:

```text
Indexing
Monitoring
Synchronization
```

---

# 243. MCP CONCURRENCY

Concurrency limits must prevent server overload.

---

# 244. MCP QUEUE

Requests may be queued where appropriate.

---

# 245. MCP CANCELLATION

Long-running requests should be cancellable where supported.

---

# 246. MCP IDEMPOTENCY

Retries of write actions require idempotency protection.

---

# 247. MCP TRANSACTIONAL ACTIONS

Database and external API writes should use transactional or compensating mechanisms where available.

---

# 248. MCP EXTERNAL API

External API MCP servers must define:

```text
Endpoint
Authentication
Rate Limit
Data Policy
Write Scope
```

---

# 249. API KEY

API keys are secrets and must be managed by the security layer.

---

# 250. OAUTH

OAuth tokens must be stored securely and scoped minimally.

---

# 251. TOKEN REFRESH

Token refresh should occur outside model-visible context.

---

# 252. MCP CREDENTIAL BOUNDARY

```text
Model
  X
Credentials

Model
  ↓
Tool Request
  ↓
Credentialed Server
```

---

# 253. MCP CREDENTIAL ISOLATION

Credentials belong to the integration runtime, not the LLM.

---

# 254. MCP DATA MINIMIZATION

Servers should receive only the data required for the operation.

---

# 255. MCP OUTPUT MINIMIZATION

Servers should return only the data required by the task.

---

# 256. MCP PERSONAL DATA

Personal data must be handled according to JARVIS privacy/security policies.

---

# 257. MCP RETENTION

MCP data should not be retained longer than necessary.

---

# 258. MCP CACHE

Cached external data must have a retention policy.

---

# 259. MCP RESOURCE PROVENANCE

Resources should preserve their source/provenance where relevant.

---

# 260. MCP RESEARCH

Research MCP servers must preserve source information where possible.

---

# 261. MCP BROWSER + RESEARCH

Browser MCP output must be treated as untrusted external content.

---

# 262. MCP SERVER PROMPT INJECTION

Servers may return malicious content.

The agent must not interpret server content as system-level instructions.

---

# 263. TOOL DESCRIPTION INJECTION

Tool descriptions are also part of the untrusted supply chain.

---

# 264. TOOL DESCRIPTION REVIEW

Production MCP server tool descriptions should be reviewed during approval.

---

# 265. TOOL NAME

Tool names should be stable and descriptive.

---

# 266. TOOL SCOPE

Each tool should perform a narrowly defined capability.

---

# 267. GOD TOOL PROHIBITION

A single MCP tool with unrestricted arbitrary execution is strongly discouraged.

---

# 268. SHELL TOOL

Arbitrary shell execution is considered privileged.

---

# 269. SHELL MCP STATUS

```text
CONDITIONALLY APPROVED
```

only in controlled development/admin environments.

---

# 270. PRODUCTION SHELL

Production JARVIS should not expose unrestricted shell access to general agents.

---

# 271. COMMAND ALLOWLIST

Where shell access is required, command allowlisting should be preferred.

---

# 272. ARGUMENT VALIDATION

Shell arguments require strict validation.

---

# 273. MCP CODE EXECUTION

Any MCP capability that executes arbitrary code receives high-risk classification.

---

# 274. MCP ADMINISTRATION

Administrative MCP servers must require explicit administrative mode.

---

# 275. ADMIN MODE

Admin mode should be:

```text
Explicit
Audited
Time-Bounded
User-Authorized
```

---

# 276. BREAK-GLASS

Emergency administrative access should be separately governed.

---

# 277. MCP SERVER DISABLE

JARVIS must support immediate server disablement.

---

# 278. REMOTE KILL SWITCH

Production deployments should be able to disable a compromised remote integration.

---

# 279. LOCAL KILL SWITCH

Local MCP processes must also be disableable.

---

# 280. MCP INCIDENT RESPONSE

```text
Detect
↓
Disable
↓
Contain
↓
Rotate Credentials
↓
Investigate
↓
Patch
↓
Re-evaluate
↓
Re-enable
```

---

# 281. COMPROMISED SERVER

A compromised server is immediately removed from the approved runtime set.

---

# 282. COMPROMISED CREDENTIAL

Credentials must be rotated.

---

# 283. COMPROMISED PACKAGE

Affected package versions must be blocked.

---

# 284. MCP SUPPLY CHAIN

MCP servers are part of JARVIS's software supply chain.

---

# 285. SUPPLY CHAIN REVIEW

Review:

```text
Publisher
Repository
Dependencies
Release Process
Package Registry
Build System
Signing
```

---

# 286. MCP PACKAGE PINNING

Production package versions must be pinned.

---

# 287. MCP CONTAINER PINNING

Production containers should use immutable image digests where practical.

---

# 288. MCP SOURCE PINNING

Source-based deployments should pin commits/tags.

---

# 289. MCP REPRODUCIBILITY

The same Version Lock should reproduce the same MCP deployment.

---

# 290. MCP LICENSE

Every server must have recorded license metadata.

---

# 291. MCP COMMERCIAL USE

Commercial distribution rights must be checked.

---

# 292. MCP DEPENDENCY LICENSES

Important transitive dependencies must be included in compliance review.

---

# 293. MCP NOTICES

Required attribution and license notices must be retained.

---

# 294. MCP SERVER INVENTORY

The approved inventory should contain:

| Server | Capability | Status | Trust | Default Mode |
|---|---|---|---|---|
| Filesystem | Local files | CONDITIONAL | T1/T3 | Restricted roots |
| Git | Source control | CONDITIONAL | T1/T3 | Approved repos |
| Fetch | HTTP retrieval | CONDITIONAL | T2 | Public network |
| Time | Time | APPROVED | T0 | Enabled |
| Memory | MCP memory | CONDITIONAL | T1 | Experimental/isolated |
| Browser/Chrome | Browser tooling | CONDITIONAL | T2/T4 | Explicit session |
| Database | DB operations | CONDITIONAL | T1/T3 | Read-only |
| Docker | Containers | CONDITIONAL | T4 | Admin/dev |
| GitHub | GitHub integration | CONDITIONAL | T2/T3 | Scoped token |

---

# 295. OFFICIAL REFERENCE SERVER WARNING

The official MCP reference repository explicitly states that its servers are reference implementations rather than production-ready solutions.

Therefore JARVIS must perform its own production review.

---

# 296. CURRENT SECURITY BASELINE

At the time of this specification, the official MCP servers repository has published security advisories affecting some reference servers, including Git-related path validation and argument-injection issues.

Therefore MCP server updates require security review before promotion.

---

# 297. MCP VERSION REVIEW

The MCP protocol and SDK ecosystem evolves rapidly.

JARVIS must pin the protocol/SDK versions used by production.

---

# 298. PROTOCOL VERSION

The exact MCP protocol version belongs in Version Lock.

---

# 299. SDK VERSION

The exact MCP SDK/client version belongs in Version Lock.

---

# 300. SERVER VERSION

The exact server version belongs in Version Lock.

---

# 301. THREE-WAY LOCK

Production MCP compatibility is therefore:

```text
Protocol Version
+
SDK Version
+
Server Version
```

---

# 302. TRANSPORT LOCK

Transport is also part of the deployment contract:

```text
stdio
Streamable HTTP
```

as applicable.

---

# 303. MCP VERSION MATRIX

Conceptually:

| Component | Version Authority |
|---|---|
| MCP Protocol | Version Lock |
| MCP Client SDK | Version Lock |
| MCP Server | Version Lock |
| Transport | Manifest + Version Lock |
| Server Runtime | Version Lock |
| Container Image | Version Lock |
| Credentials | Secret Manager |

---

# 304. MCP MODEL ROUTER RELATIONSHIP

The Model Router may select an MCP capability without knowing implementation details.

---

# 305. CAPABILITY ABSTRACTION

Agents should request:

```text
filesystem.read
github.issue.create
browser.navigate
database.query
```

rather than hard-coding package names where possible.

---

# 306. MCP CAPABILITY REGISTRY

JARVIS should maintain a capability registry mapping:

```text
Capability
→
MCP Server
→
Tool
→
Permission
```

---

# 307. MCP TOOL REGISTRY

Every production tool should have:

```text
Tool ID
Server ID
Risk Tier
Input Schema
Output Schema
Permission
Audit Policy
```

---

# 308. TOOL DISCOVERY

Agents may discover approved tools through the JARVIS MCP Gateway.

---

# 309. UNAPPROVED TOOL

Unapproved tools must not be exposed to production agents.

---

# 310. TOOL DEPRECATION

Deprecated tools should be hidden from new agent sessions.

---

# 311. TOOL VERSIONING

Tool schemas are versioned compatibility contracts.

---

# 312. MCP SERVER MIGRATION

Migration path:

```text
New Server
↓
Compatibility Tests
↓
Shadow Mode
↓
Canary
↓
Production
↓
Old Server Deprecated
```

---

# 313. SHADOW MCP

Where practical, a replacement server can execute read-only/shadow requests without producing external side effects.

---

# 314. MCP CANARY

A new server version can be enabled for a limited subset of workflows.

---

# 315. MCP ROLLBACK

Previous approved version must remain deployable during migration.

---

# 316. MCP CHANGELOG

Every production MCP change must record:

```text
Old Version
New Version
Reason
Risk
Tests
Rollback
```

---

# 317. MCP DEPRECATION

Deprecation triggers include:

```text
Security Issue
Maintenance Failure
Protocol Incompatibility
Better Alternative
License Problem
Reliability Problem
```

---

# 318. MCP REJECTION

A server should be rejected if:

```text
Unacceptable Security Risk
Unclear Provenance
Incompatible License
Unmaintained Critical Dependency
No Isolation Strategy
No Reliable Deployment Path
```

---

# 319. MCP APPROVAL SCORE

Candidate servers may be evaluated on:

```text
Security
Reliability
Maintenance
Documentation
Capability Quality
Protocol Compliance
License
Supply Chain
Isolation
Observability
JAS Compatibility
Bootstrap Compatibility
```

---

# 320. HARD BLOCKERS

No score can override:

```text
Critical Security Failure
Unacceptable License
Unknown Provenance
Uncontrolled Privilege
No Safe Deployment Model
```

---

# 321. MCP SERVER MINIMALISM

Only required MCP servers should be enabled.

---

# 322. MCP SPRAWL

Too many servers increase:

```text
Attack Surface
Tool Confusion
Memory Context
Maintenance
Resource Usage
```

---

# 323. TOOL SPRAWL

Agents should not receive hundreds of unnecessary tools.

---

# 324. DYNAMIC TOOL SELECTION

JARVIS may dynamically expose only the tools relevant to the current task.

---

# 325. TOOL CONTEXT BUDGET

Tool schemas consume model context.

Tool exposure should therefore be minimized.

---

# 326. MCP TOOL GROUPS

Tools may be grouped by:

```text
Filesystem
Browser
Git
Database
Infrastructure
Productivity
```

---

# 327. AGENT TOOL ALLOWLIST

Each agent may have an explicit MCP capability allowlist.

---

# 328. PLANNER TOOL ALLOWLIST

The planner may not automatically receive privileged tools.

---

# 329. BROWSER AGENT

Browser Agent may receive:

```text
Browser MCP
Fetch
```

but not:

```text
Docker Admin
Credential Management
```

by default.

---

# 330. CODING AGENT

Coding Agent may receive:

```text
Filesystem
Git
GitHub
```

with scoped permissions.

---

# 331. RESEARCH AGENT

Research Agent may receive:

```text
Fetch
Browser
Documentation
```

with external-content controls.

---

# 332. SYSTEM AGENT

System Agent may receive infrastructure MCP only under elevated policy.

---

# 333. MEMORY AGENT

Memory Agent may receive memory/database capabilities but not unrestricted filesystem or shell access.

---

# 334. MCP SERVER ISOLATION

Servers should be isolated by capability domain.

---

# 335. CROSS-SERVER ACCESS

An MCP server must not automatically call another MCP server.

---

# 336. MCP COMPOSITION

Cross-server composition should occur through JARVIS orchestration.

---

# 337. MCP SERVER DEPENDENCY

If a server requires another server, the dependency must be explicitly declared.

---

# 338. DEPENDENCY CYCLES

MCP server dependency cycles are prohibited.

---

# 339. MCP START ORDER

Dependencies must start before dependents.

---

# 340. MCP SHUTDOWN ORDER

Dependents should stop before dependencies.

---

# 341. MCP HEALTH DEPENDENCY

A dependent server is unhealthy if a required dependency is unavailable.

---

# 342. MCP REGISTRY SCHEMA

Conceptually:

```yaml
server_id:
publisher:
repository:
version:
revision:
license:
protocol_version:
transport:
capabilities:
trust_tier:
permissions:
network_policy:
filesystem_policy:
secrets:
runtime:
platforms:
status:
health:
evaluation:
```

---

# 343. MCP MANIFEST EXAMPLE

Conceptually:

```yaml
mcp:
  required:
    - filesystem
    - git

  optional:
    - github
    - fetch
    - browser

  experimental:
    - sequential-thinking
```

Exact syntax belongs to the future Manifest specification.

---

# 344. MCP VERSION LOCK EXAMPLE

Conceptually:

```yaml
mcp:
  filesystem:
    version:
    revision:
    digest:

  git:
    version:
    revision:
    digest:
```

Exact schema belongs to Version Lock.

---

# 345. MCP BOOTSTRAP

Bootstrap must:

```text
Detect
↓
Resolve
↓
Download
↓
Verify
↓
Install
↓
Configure
↓
Start
↓
Health Check
↓
Smoke Test
```

---

# 346. MCP BOOTSTRAP SECURITY

Bootstrap must never execute arbitrary installation instructions supplied by an MCP server.

---

# 347. MCP SERVER START COMMAND

Start commands must originate from trusted manifest/configuration data.

---

# 348. MCP INSTALL SCRIPT

Third-party install scripts require review and should not be executed blindly.

---

# 349. PACKAGE MANAGER

Package manager selection follows `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`.

---

# 350. MCP RUNTIME

The MCP runtime must be version locked.

---

# 351. MCP CLIENT

The JARVIS MCP client must be treated as a core security component.

---

# 352. MCP CLIENT HARDENING

Client hardening includes:

```text
Schema Validation
Timeouts
Size Limits
Auth
Audit
Policy Enforcement
```

---

# 353. MCP SERVER HARDENING

Server hardening includes:

```text
Least Privilege
Input Validation
Output Limits
Sandbox
Secret Isolation
```

---

# 354. MCP GATEWAY HARDENING

Gateway hardening includes:

```text
Authentication
Authorization
Rate Limits
Circuit Breakers
Logging
Tracing
```

---

# 355. MCP TOOL SCHEMA VALIDATION

Input must be validated before execution.

---

# 356. MCP OUTPUT VALIDATION

Output must be validated before entering trusted application state.

---

# 357. MCP TYPE SAFETY

Schemas should use strict types.

---

# 358. MCP UNEXPECTED FIELDS

Unexpected fields should be rejected or ignored according to schema policy.

---

# 359. MCP LARGE OUTPUT

Large outputs should be truncated/paginated rather than blindly inserted into context.

---

# 360. MCP BINARY DATA

Binary resources should be handled outside normal text context where practical.

---

# 361. MCP FILE RESOURCE

File resources must obey filesystem policy.

---

# 362. MCP URL RESOURCE

URL resources must obey network policy.

---

# 363. MCP DATABASE RESOURCE

Database resources must obey database access policy.

---

# 364. MCP GITHUB RESOURCE

GitHub resources must obey GitHub token scope.

---

# 365. MCP BROWSER RESOURCE

Browser resources must obey browser session policy.

---

# 366. MCP TOOL SIDE EFFECT CLASS

Each tool should declare:

```text
READ_ONLY
REVERSIBLE_WRITE
IRREVERSIBLE_WRITE
EXTERNAL_SIDE_EFFECT
PRIVILEGED
```

---

# 367. READ_ONLY

May execute automatically when permitted.

---

# 368. REVERSIBLE_WRITE

May require confirmation depending on context.

---

# 369. IRREVERSIBLE_WRITE

Requires explicit confirmation unless a pre-authorized workflow exists.

---

# 370. EXTERNAL SIDE EFFECT

Requires external-action policy.

---

# 371. PRIVILEGED

Requires elevated authorization.

---

# 372. MCP APPROVAL MATRIX

| Capability | Default | User Confirmation | Isolation |
|---|---|---|---|
| Time | Approved | No | Low |
| Public Fetch | Conditional | Usually no | Network |
| Filesystem Read | Conditional | No | Root sandbox |
| Filesystem Write | Conditional | Contextual | Root sandbox |
| Git Read | Conditional | No | Repo sandbox |
| Git Commit | Conditional | Yes/contextual | Repo sandbox |
| GitHub Read | Conditional | No | Token scope |
| GitHub Write | Conditional | Yes | Token scope |
| Database Read | Conditional | No | DB account |
| Database Write | Conditional | Yes | DB account |
| Browser Read | Conditional | No | Browser profile |
| Browser Write | Conditional | Yes/contextual | Browser sandbox |
| Docker Read | Conditional | No | Container boundary |
| Docker Exec | Conditional | Yes | Strong isolation |
| Shell | Conditional | Yes | Strong isolation |

---

# 373. MCP SECURITY INVARIANTS

The following invariants are mandatory:

```text
1. MCP cannot bypass JARVIS policy.
2. Model cannot directly grant itself permissions.
3. Secrets are never model-visible by default.
4. Unapproved servers cannot enter production.
5. Production versions are pinned.
6. High-risk operations are auditable.
7. External content is untrusted.
8. Filesystem access is scoped.
9. Network access is scoped.
10. Server installation is controlled.
```

---

# 374. MCP FAILURE INVARIANTS

On failure:

```text
No uncontrolled retries
No privilege escalation
No silent fallback to unsafe capability
No secret exposure
No duplicate irreversible action
```

---

# 375. MCP FALLBACK

A failed MCP server may be replaced only by an approved alternative with equivalent capability and compatible security policy.

---

# 376. MCP NO FALLBACK

If no safe fallback exists:

```text
Stop
Report
Ask User
```

rather than guessing.

---

# 377. MCP OBSERVABILITY

Every production MCP server should integrate with the observability stack.

---

# 378. MCP TRACE

A trace should connect:

```text
User Request
→ Agent
→ Model
→ MCP Gateway
→ MCP Server
→ Tool
→ External System
```

---

# 379. MCP TRACE PRIVACY

Trace metadata must minimize sensitive content.

---

# 380. MCP COST

Cloud/external MCP services may incur costs.

Cost metadata should be tracked where practical.

---

# 381. MCP QUOTA

External API MCP servers must respect provider quotas.

---

# 382. MCP RATE LIMIT

The Gateway should enforce rate limits independently of provider limits.

---

# 383. MCP BACKOFF

Exponential backoff should be used where appropriate.

---

# 384. MCP RETRY SAFETY

Retries must consider side effects.

---

# 385. MCP IDENTITY

Each tool invocation should have a correlation/request ID.

---

# 386. MCP AUDIT

High-risk operations must be attributable to:

```text
User
Agent
Session
Tool
Server
```

---

# 387. MCP SESSION

MCP session state must not persist longer than necessary.

---

# 388. REMOTE SESSION

Remote session credentials must expire according to policy.

---

# 389. MCP CONNECTION POOL

Connection pooling may be used for remote servers but must respect isolation and authentication.

---

# 390. MCP SERVER RESTART

Server restart must not silently repeat previous side effects.

---

# 391. MCP STATE

Persistent server state must be explicitly declared.

---

# 392. STATEFUL MCP

Stateful servers require lifecycle documentation.

---

# 393. STATELESS MCP

Stateless servers are preferred where practical for scalable remote deployment.

---

# 394. MCP SERVER DATA

Persistent server data belongs to the server's defined storage boundary.

---

# 395. MCP SERVER BACKUP

Important persistent MCP data must have a backup policy.

---

# 396. MCP SERVER RESTORE

Restoration must preserve version compatibility.

---

# 397. MCP DATABASE MIGRATION

Database-backed MCP servers require migration controls.

---

# 398. MCP SCHEMA MIGRATION

Schema changes must be tested before deployment.

---

# 399. MCP ROLLBACK

Database migrations must have rollback/forward-recovery strategies.

---

# 400. MCP SERVER DOCUMENTATION

Every approved server must document:

```text
Purpose
Capabilities
Permissions
Dependencies
Installation
Configuration
Security
Known Limitations
```

---

# 401. MCP SERVER LIMITATIONS

Known limitations must be recorded in the registry.

---

# 402. MCP SERVER CONTACT

Maintainer/project information should be recorded.

---

# 403. MCP SUPPORT

Critical MCP servers should have a support/maintenance path.

---

# 404. MCP MAINTENANCE REVIEW

Critical servers should be reviewed periodically.

---

# 405. MCP SECURITY REVIEW

High-risk servers require periodic security review.

---

# 406. MCP LICENSE REVIEW

License terms should be rechecked when major versions change.

---

# 407. MCP PROTOCOL REVIEW

Protocol compatibility should be rechecked after MCP SDK upgrades.

---

# 408. MCP SERVER UPGRADE

No automatic production upgrade.

---

# 409. MCP UPDATE POLICY

```text
New Release
↓
Security Scan
↓
Compatibility Test
↓
Integration Test
↓
Approval
↓
Version Lock Update
```

---

# 410. MCP SERVER ROLLBACK

Rollback must restore the previous approved server revision and configuration.

---

# 411. MCP SERVER DELETION

Deletion must verify that no active workflow depends on the server.

---

# 412. MCP DEPENDENCY CHECK

Before removal:

```text
Agents
Plugins
Workflows
Manifest
```

must be checked.

---

# 413. MCP SERVER REPLACEMENT

Replacement requires capability compatibility.

---

# 414. MCP CAPABILITY COMPATIBILITY

Equivalent server does not necessarily mean equivalent tool schema.

---

# 415. MCP TOOL MIGRATION

Tool names and schemas may require agent updates.

---

# 416. MCP MIGRATION TEST

Run:

```text
Unit
Contract
Integration
System
Security
```

tests.

---

# 417. MCP APPROVAL RECORD

Each approval should record:

```text
Decision
Date
Reviewer
Version
Reason
Risks
Conditions
```

---

# 418. MCP CONDITIONAL APPROVAL RECORD

Conditions must be machine-enforceable where possible.

---

# 419. MCP EXPERIMENT RECORD

Experiments should record:

```text
Hypothesis
Server
Version
Test
Result
Decision
```

---

# 420. MCP ROADMAP

Future servers belong in:

```text
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

until evaluated.

---

# 421. MCP REJECTED SERVERS

Rejected servers belong in:

```text
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

where applicable.

---

# 422. MCP SOFTWARE MATRIX

Approved servers must eventually be represented in:

```text
21_APPROVED_SOFTWARE_MATRIX.md
```

---

# 423. MCP VERSION SUPPORT

Support lifecycle follows:

```text
Current
Supported
Maintenance
Deprecated
Removed
```

---

# 424. MCP SUPPORT WINDOW

Critical servers should not remain on unsupported versions.

---

# 425. MCP END OF LIFE

End-of-life servers require migration or removal.

---

# 426. MCP SERVER SELECTION PRINCIPLE

> The smallest safe MCP capability that satisfies the task should be selected.

---

# 427. MCP TRUST PRINCIPLE

> Registry publication does not equal production trust.

---

# 428. MCP SECURITY PRINCIPLE

> MCP is a capability boundary, not a security boundary by itself; JARVIS must enforce security around it.

---

# 429. MCP MODEL PRINCIPLE

> The LLM may request an MCP capability but never grants itself permission to execute it.

---

# 430. MCP SECRETS PRINCIPLE

> Credentials belong to integration infrastructure, not model context.

---

# 431. MCP VERSION PRINCIPLE

> Production MCP servers must be reproducible from pinned protocol, SDK, server and artifact versions.

---

# 432. MCP CONTENT PRINCIPLE

> External MCP content is untrusted data until independently validated.

---

# 433. MCP MINIMALISM PRINCIPLE

> Do not expose an agent to MCP capabilities it does not need.

---

# 434. MCP RECOVERY PRINCIPLE

> A failed integration must degrade safely rather than escalating privileges or repeating side effects.

---

# 435. MCP PRODUCTION BASELINE

```text
============================================================
                JARVIS MCP BASELINE v1
============================================================

APPROVED
------------------------------------------------------------
Time
Status: APPROVED
Risk: Low

CONDITIONALLY APPROVED
------------------------------------------------------------
Filesystem
Git
Fetch
Browser / Chrome
Database
Docker
GitHub
Memory

EXPERIMENTAL
------------------------------------------------------------
Sequential Thinking

EVALUATION ONLY
------------------------------------------------------------
Everything

UNAPPROVED BY DEFAULT
------------------------------------------------------------
All other community MCP servers

============================================================

MANDATORY CONTROLS
------------------------------------------------------------
Server Provenance
License Review
Version Pinning
Protocol Pinning
SDK Pinning
Permission Policy
Least Privilege
Secret Isolation
Network Policy
Filesystem Policy
Timeouts
Rate Limits
Audit Logging
Observability
Contract Tests
Security Tests
Rollback
Kill Switch

============================================================
```

---

# 436. INITIAL APPROVED SERVER MATRIX

| Server | Primary Capability | Status | Trust Tier | Default Access |
|---|---|---|---|---|
| Time | Time | APPROVED | T0 | Enabled |
| Filesystem | Files | CONDITIONAL | T1/T3 | Restricted roots |
| Git | Git repositories | CONDITIONAL | T1/T3 | Approved repos |
| Fetch | HTTP retrieval | CONDITIONAL | T2 | Public network |
| Memory | MCP memory | CONDITIONAL | T1 | Isolated |
| Browser / Chrome | Browser automation | CONDITIONAL | T2/T4 | Explicit session |
| Database | Database | CONDITIONAL | T1/T3 | Read-only |
| Docker | Containers | CONDITIONAL | T4 | Admin/dev |
| GitHub | GitHub | CONDITIONAL | T2/T3 | Scoped credentials |
| Sequential Thinking | Reasoning utility | EXPERIMENTAL | T0 | Development |
| Everything | MCP test suite | EVALUATION | T0 | Testing only |

---

# 437. WHY MOST SERVERS ARE CONDITIONAL

The reason is architectural.

An MCP server can turn an otherwise passive LLM into an agent capable of:

```text
Reading
Writing
Executing
Communicating
Changing Systems
```

Therefore production approval must consider capability risk rather than popularity.

---

# 438. MCP SERVER ARCHITECTURE

```text
                       JARVIS
                          │
                          ▼
                     MCP GATEWAY
                          │
                   SECURITY POLICY
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        LOCAL MCP     REMOTE MCP    SANDBOX
             │            │            │
       ┌─────┼─────┐      │      ┌─────┼─────┐
       ▼     ▼     ▼      ▼      ▼     ▼     ▼
    Files   Git   DB   Browser  Docker Fetch  Tools
             │            │
             └────────────┼────────────┘
                          ▼
                    EXTERNAL SYSTEMS
```

---

# 439. COMPLETE MCP GOVERNANCE CHAIN

```text
Research
   ↓
Candidate
   ↓
Source Verification
   ↓
Security Review
   ↓
License Review
   ↓
Capability Review
   ↓
Sandbox Review
   ↓
Integration Testing
   ↓
Approval
   ↓
Version Lock
   ↓
Manifest
   ↓
Bootstrap
   ↓
System Verification
   ↓
Production
   ↓
Monitoring
   ↓
Upgrade / Deprecation
```

---

# 440. FINAL ARCHITECTURAL DECISION

MCP is officially adopted as a controlled external capability integration layer for JARVIS.

However:

```text
MCP ≠ Plugin
MCP ≠ Agent
MCP ≠ Security Policy
MCP ≠ Model
MCP ≠ Core
```

The correct relationship is:

```text
JARVIS Core
    ↓
Agent
    ↓
Model
    ↓
Tool Request
    ↓
MCP Gateway
    ↓
Policy
    ↓
Approved MCP Server
    ↓
External Capability
```

---

# 441. FINAL APPROVAL RULE

No MCP server enters production merely because:

```text
It exists
It is popular
It is on GitHub
It is in the MCP Registry
It has many stars
It is official
```

Production approval requires:

```text
Capability Need
+
Provenance
+
Security
+
License
+
Compatibility
+
Testing
+
Isolation
+
Version Lock
```

---

# 442. FINAL MODEL

The JARVIS MCP architecture is therefore:

```text
                  ┌─────────────────────┐
                  │      JARVIS         │
                  │       CORE          │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │   AGENT / MODEL     │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │    MCP GATEWAY      │
                  └──────────┬──────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │ SECURITY / POLICY   │
                  └──────────┬──────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │ Filesystem │ │   Browser  │ │  GitHub    │
       └────────────┘ └────────────┘ └────────────┘
              │              │              │
              ▼              ▼              ▼
          Local FS        Web Apps      GitHub API

              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
          Database        Docker          Fetch
```

---

# 443. CONCLUSION

`20_APPROVED_MCP_SERVERS.md` establishes MCP as a governed capability layer rather than an uncontrolled plugin marketplace.

The initial JARVIS baseline therefore consists of:

```text
Time
        → APPROVED

Filesystem
        → CONDITIONAL

Git
        → CONDITIONAL

Fetch
        → CONDITIONAL

Memory
        → CONDITIONAL

Browser / Chrome
        → CONDITIONAL

Database
        → CONDITIONAL

Docker
        → CONDITIONAL

GitHub
        → CONDITIONAL

Sequential Thinking
        → EXPERIMENTAL

Everything
        → EVALUATION ONLY
```

The most important rule is:

> **An MCP server is approved because JARVIS has evaluated and constrained its capability, not because the MCP ecosystem has published it.**

MCP therefore becomes a controlled extension boundary:

```text
Approved Server
+
Pinned Version
+
Defined Capability
+
Least Privilege
+
Sandbox
+
Security Policy
+
Observability
+
Testing
+
Rollback
```

Only after these conditions are satisfied may an MCP server become part of the production JARVIS environment.

---

# 444. NEXT DEPENDENCIES

This document feeds directly into:

```text
21_APPROVED_SOFTWARE_MATRIX.md
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
23_LICENSE_AND_COMPLIANCE.md
24_VERSION_SUPPORT_POLICY.md
```

and operationally into:

```text
VERSION LOCK
MANIFEST
BOOTSTRAP
COMPLIANCE CHECKER
SYSTEM VERIFICATION
```

The exact production server versions, protocol version, SDK version, package revisions and artifact digests are intentionally deferred to Version Lock.