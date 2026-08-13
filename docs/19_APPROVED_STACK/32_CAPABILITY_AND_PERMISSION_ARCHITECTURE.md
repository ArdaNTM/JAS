# 32 — CAPABILITY AND PERMISSION ARCHITECTURE

**Document ID:** JAS-AS-32  
**Document:** `32_CAPABILITY_AND_PERMISSION_ARCHITECTURE.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED ARCHITECTURE SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  

**Depends On:**
- `00_APPROVED_STACK_OVERVIEW.md`
- `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`
- `04_AGENT_ORCHESTRATION_STACK.md`
- `12_PLUGIN_AND_EXTENSION_STACK.md`
- `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`
- `14_SECURITY_STACK.md`
- `19_APPROVED_MODELS.md`
- `20_APPROVED_MCP_SERVERS.md`
- `24_VERSION_SUPPORT_POLICY.md`
- `26_VERSION_LOCK.md`
- `27_MANIFEST.md`
- `28_BOOTSTRAP.md`
- `29_SYSTEM_VERIFICATION.md`
- `30_JARVIS_CORE_ARCHITECTURE.md`
- `31_AGENT_RUNTIME_AND_EXECUTION_ARCHITECTURE.md`

**Feeds Into:**
- JARVIS Core
- Agent Runtime
- Tool Gateway
- Plugin Manager
- MCP Gateway
- Security Policy Engine
- Manifest
- Bootstrap
- Version Lock
- Compliance Checker
- System Verification

---

# 1. PURPOSE

This document defines the capability and permission architecture of JARVIS.

The purpose is to establish a single, centralized and enforceable model for determining:

```text
WHO
    may perform
WHAT
    against
WHICH RESOURCE
    under
WHICH CONTEXT
    according to
WHICH POLICY
```

The capability and permission architecture exists to prevent agents, plugins, MCP servers, tools, models and other runtime components from receiving implicit authority.

The architecture therefore establishes:

```text
Capability
    ↓
Permission
    ↓
Policy
    ↓
Context
    ↓
Authorization Decision
    ↓
Execution
```

The system must not treat possession of a tool, plugin, MCP connection, model output or local process as sufficient authority to perform an operation.

---

# 2. CORE DECISION

JARVIS v1 adopts:

```text
CAPABILITY-BASED ACCESS
+
LEAST PRIVILEGE
+
DEFAULT DENY
+
EXPLICIT GRANTS
+
CENTRAL AUTHORIZATION
+
RESOURCE SCOPING
+
CONTEXT-AWARE AUTHORIZATION
+
POLICY ENFORCEMENT
+
AUDITABILITY
+
REVOCABILITY
```

as the authoritative capability and permission model.

These principles are consistent with the existing JARVIS security architecture.

---

# 3. FUNDAMENTAL SECURITY RULE

The fundamental rule is:

> Possessing a capability does not automatically grant permission to use it.

Therefore:

```text
Capability
    ≠
Permission
```

and:

```text
Permission
    ≠
Automatic Authorization
```

Authorization requires the complete decision context.

---

# 4. AUTHORIZATION FORMULA

A capability invocation is authorized only when all required conditions are satisfied.

Conceptually:

```text
AUTHORIZED =
    VALID_IDENTITY
    AND
    VALID_CAPABILITY
    AND
    VALID_PERMISSION
    AND
    VALID_POLICY
    AND
    VALID_CONTEXT
    AND
    VALID_RESOURCE_SCOPE
    AND
    VALID_RUNTIME_STATE
```

If any mandatory condition fails:

```text
DENY
```

---

# 5. DEFAULT DENY

The default permission state is:

```text
DENY
```

No agent, plugin, MCP server or tool receives access merely because it is:

```text
installed
local
internal
approved
registered
discoverable
available
previously used
```

Access must be explicitly granted.

---

# 6. LEAST PRIVILEGE

Every runtime principal receives only the minimum authority required to perform its assigned operation.

Example:

```text
Research Agent
    ↓
web.search
```

does not imply:

```text
filesystem.write
shell.execute
email.send
calendar.create
credential.read
```

The capability set must be limited to the actual task.

---

# 7. CAPABILITY DEFINITION

A capability represents an abstract ability that JARVIS can expose to an authorized runtime principal.

Examples:

```text
filesystem.read
filesystem.write
process.start
process.terminate
browser.navigate
browser.click
browser.type
browser.download
network.request
github.read
github.write
calendar.read
calendar.create
email.read
email.send
memory.read
memory.write
database.read
database.write
shell.execute
model.inference
vision.inspect
audio.capture
notification.send
```

A capability describes:

```text
WHAT CAN BE DONE
```

It does not by itself define:

```text
WHO MAY DO IT
```

or:

```text
WHICH RESOURCE MAY BE USED
```

---

# 8. CAPABILITY VS OPERATION

A capability is an authorization concept.

An operation is an executable action.

Example:

```text
Capability:
filesystem.read

Operation:
read_file("D:/AURA/JAS/README.md")
```

Another example:

```text
Capability:
calendar.create

Operation:
create_calendar_event(...)
```

Therefore:

```text
Capability
    ↓
permits a class of operations
```

while the operation contains the concrete execution request.

---

# 9. CAPABILITY ID

Every capability must have a stable unique identifier.

Recommended structure:

```text
<domain>.<resource>.<operation>
```

Examples:

```text
filesystem.file.read
filesystem.file.write
filesystem.directory.list

browser.page.navigate
browser.page.click
browser.page.type

network.http.request

calendar.event.read
calendar.event.create
calendar.event.delete

email.message.read
email.message.send

github.repository.read
github.repository.write
```

Capability IDs must be stable and must not depend on display names.

---

# 10. CAPABILITY NAMESPACE

Capabilities must use namespaces.

Core capabilities:

```text
core.*
```

Plugin capabilities:

```text
plugin.<plugin_id>.*
```

MCP capabilities:

```text
mcp.<server_id>.*
```

Browser capabilities:

```text
browser.*
```

Filesystem capabilities:

```text
filesystem.*
```

This prevents collisions between independently provided capabilities.

---

# 11. CAPABILITY REGISTRY

JARVIS v1 requires a centralized Capability Registry.

The registry is authoritative for capability discovery and capability metadata.

Conceptually:

```text
                    CAPABILITY REGISTRY
                           │
        ┌──────────────────┼──────────────────┐
        ↓                  ↓                  ↓
      Core              Plugin              MCP
  Capabilities       Capabilities       Capabilities
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ↓
                     Authorization
```

Agents must not maintain independent authoritative capability catalogs.

---

# 12. CAPABILITY REGISTRY RESPONSIBILITIES

The Capability Registry is responsible for:

```text
Capability Registration
Capability Discovery
Capability Identity
Capability Metadata
Capability Ownership
Capability Provider
Capability Version
Capability Risk Classification
Capability Availability
Capability Scope Definition
Capability Dependency Metadata
Capability Permission Requirements
Capability Policy Requirements
Capability Lifecycle
Capability Revocation State
Capability Audit Metadata
```

---

# 13. CAPABILITY REGISTRY RECORD

A capability record should contain at minimum:

```text
Capability ID
Provider ID
Provider Type
Version
Description
Operation
Resource Type
Risk Level
Required Permissions
Required Policy
Allowed Contexts
Resource Scope
Dependencies
Availability
Trust Level
Isolation Requirement
Audit Requirement
Approval Requirement
Lifecycle State
```

---

# 14. CAPABILITY OWNERSHIP

Every capability must have a known provider.

Possible providers:

```text
JARVIS Core
JARVIS Service
Plugin
MCP Server
External Adapter
System Integration
```

Unknown ownership results in:

```text
DENY
```

---

# 15. CAPABILITY DISCOVERY

Capability discovery does not grant permission.

The correct flow is:

```text
Discover Capability
        ↓
Register Capability
        ↓
Validate Provider
        ↓
Classify Risk
        ↓
Determine Permission Requirements
        ↓
Apply Policy
        ↓
Grant or Deny
```

Therefore:

```text
DISCOVERED
    ≠
AUTHORIZED
```

---

# 16. CAPABILITY LIFECYCLE

Capabilities have a lifecycle.

```text
DISCOVERED
    ↓
REGISTERED
    ↓
VALIDATED
    ↓
AVAILABLE
    ↓
AUTHORIZED
    ↓
ACTIVE
    ↓
SUSPENDED / REVOKED
    ↓
RETIRED
```

A capability may move directly to:

```text
REJECTED
```

if validation fails.

---

# 17. CAPABILITY STATE

Possible states include:

```text
DISCOVERED
REGISTERED
VALIDATING
AVAILABLE
RESTRICTED
SUSPENDED
REVOKED
REJECTED
RETIRED
```

The registry must expose the current state.

---

# 18. PERMISSION DEFINITION

A permission represents authorization granted to a principal for a capability within a defined scope.

Conceptually:

```text
Principal
    +
Capability
    +
Scope
    +
Conditions
    =
Permission
```

A permission therefore answers:

```text
WHO
may use
WHICH CAPABILITY
against
WHICH RESOURCE
under
WHICH CONDITIONS
```

---

# 19. PERMISSION IS NOT CAPABILITY

The architecture must preserve:

```text
Capability = Ability

Permission = Granted authority
```

Example:

```text
Capability:
filesystem.file.write

Permission:
Agent X
may write
D:\AURA\workspace\*
during
active task T
```

---

# 20. PERMISSION PRINCIPAL

A principal is an identity capable of requesting a capability.

Possible principals:

```text
User
Agent
Plugin
MCP Server
Core Service
Background Task
Scheduled Task
System Process
```

Each principal must have a stable runtime identity.

---

# 21. PRINCIPAL IDENTITY

A principal identity should contain:

```text
Principal ID
Principal Type
Provider
Version
Trust Level
Execution Context
Security Context
Permission Profile
Lifecycle State
```

Example:

```text
principal:
  id: agent.research
  type: agent
  trust: T1
```

---

# 22. AGENT PERMISSIONS

Agents do not receive unrestricted access to the capabilities exposed by their tools.

Instead:

```text
Agent
    ↓
Capability Request
    ↓
Permission Engine
    ↓
Policy Engine
    ↓
Execution
```

An agent's model output is therefore never treated as an authorization decision.

---

# 23. MODEL OUTPUT IS NOT AUTHORITY

The LLM may propose:

```text
"Run this command."
```

The model output does not authorize execution.

Instead:

```text
LLM Output
    ↓
Intent / Tool Request
    ↓
Capability Resolution
    ↓
Permission Evaluation
    ↓
Policy Evaluation
    ↓
Execution Decision
```

This distinction is mandatory.

---

# 24. PLUGIN PERMISSIONS

Plugins operate through the JARVIS extension boundary.

The plugin architecture already establishes:

```text
Plugin
    ↓
Capability
    ↓
Permission
    ↓
Policy
    ↓
Execution
```

A plugin must not access JARVIS Core internals directly.

Installation must not automatically grant permissions.

---

# 25. MCP PERMISSIONS

MCP capabilities are treated as external capabilities.

The architecture remains:

```text
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
MCP Gateway
    ↓
MCP Client
    ↓
MCP Server
```

MCP compatibility does not imply trust or authorization.

---

# 26. TOOL PERMISSIONS

Every executable tool must have an associated capability and permission profile.

Example:

```text
Tool:
github.issue.create

Capability:
github.issue.create

Risk:
MEDIUM

Permission:
github.issue.create

Scope:
repository-specific
```

---

# 27. RESOURCE SCOPING

Permissions must be scoped whenever possible.

A permission should not merely state:

```text
filesystem.write = ALLOW
```

when a more precise scope is possible.

Instead:

```text
filesystem.write
scope:
  D:\AURA\workspace\*
```

is preferred.

---

# 28. RESOURCE SCOPE TYPES

Supported conceptual scopes include:

```text
GLOBAL
SYSTEM
USER
WORKSPACE
PROJECT
DIRECTORY
FILE
REPOSITORY
DATABASE
TABLE
RECORD
DOMAIN
URL
APPLICATION
PROCESS
DEVICE
SESSION
TASK
```

---

# 29. SCOPE NARROWING

When multiple scopes apply, the narrower valid scope should be preferred.

Example:

```text
Global
    ↓
Workspace
    ↓
Project
    ↓
Directory
    ↓
File
```

A broad permission must not be used merely because a narrow permission could not be conveniently evaluated.

---

# 30. RESOURCE IDENTIFIERS

Resources should use stable identifiers whenever possible.

Examples:

```text
filesystem://D:/AURA/workspace
github://repo/owner/name
calendar://account/event/id
database://postgres/database/table
browser://session/page
```

The exact resource identifier format may be finalized by the corresponding subsystem.

---

# 31. PERMISSION CONDITIONS

Permissions may contain conditions.

Examples:

```text
time window
task ID
session ID
resource scope
network state
user presence
approval state
risk state
runtime state
```

Example:

```text
calendar.event.create
ALLOW
only:
  task = task_123
  user_confirmation = true
```

---

# 32. CONTEXT-AWARE AUTHORIZATION

Authorization must evaluate execution context.

Relevant context may include:

```text
User Identity
Agent Identity
Task Identity
Session Identity
Plugin Identity
MCP Server Identity
Resource Identity
Current Policy
Current Risk
Current Runtime State
Current Security State
Approval State
```

---

# 33. SESSION BOUND PERMISSIONS

Some permissions may be granted only for a specific session.

Example:

```text
Session:
S-2026-001

Permission:
browser.download

Scope:
current browser session

Expiration:
session end
```

When the session ends, the permission may automatically expire.

---

# 34. TASK BOUND PERMISSIONS

High-risk capabilities should preferably be bound to a task.

Example:

```text
Task:
"Update project dependencies"

Allowed:
filesystem.write
git.write

Scope:
D:\AURA\JAS
```

The same agent should not automatically inherit those permissions for unrelated tasks.

---

# 35. TEMPORARY PERMISSIONS

Permissions may be temporary.

Possible expiration mechanisms:

```text
time-based
session-based
task-based
operation-count-based
approval-based
resource-state-based
```

Expired permissions must no longer authorize execution.

---

# 36. PERMISSION GRANT

A permission grant must identify:

```text
Principal
Capability
Scope
Conditions
Issuer
Issued At
Expiration
Policy
Risk
Approval Requirement
Audit Requirement
```

Example:

```yaml
principal: agent.coding
capability: filesystem.file.write
scope: D:/AURA/JAS/**
conditions:
  task_id: task_123
expires: task_end
```

---

# 37. PERMISSION REVOCATION

Permissions must be revocable.

Revocation may occur because of:

```text
User Request
Security Event
Policy Change
Capability Drift
Permission Drift
Provider Compromise
Credential Compromise
Task Completion
Session End
Plugin Failure
MCP Failure
Critical Vulnerability
Integrity Failure
```

Revocation must take effect before subsequent execution where technically possible.

---

# 38. CAPABILITY REVOCATION

A capability may be revoked independently of individual permissions.

Example:

```text
MCP Server Integrity Failure
        ↓
Capability Revocation
        ↓
All Related Permissions Invalid
        ↓
Execution Blocked
```

---

# 39. PERMISSION PRECEDENCE

The authorization system must resolve conflicting rules deterministically.

The conceptual precedence is:

```text
SYSTEM SAFETY
    ↓
SECURITY POLICY
    ↓
EXPLICIT USER POLICY
    ↓
RESOURCE POLICY
    ↓
TASK POLICY
    ↓
AGENT PERMISSION
    ↓
CAPABILITY AVAILABILITY
    ↓
EXECUTION
```

A lower-level rule must never override a higher-level deny.

---

# 40. DENY OVERRIDES ALLOW

The default conflict rule is:

```text
DENY > ALLOW
```

Example:

```text
Agent Permission:
ALLOW filesystem.write

Security Policy:
DENY filesystem.write on protected path
```

Result:

```text
DENY
```

---

# 41. PROTECTED RESOURCES

JARVIS must support protected resource classes.

Examples:

```text
Master Credentials
Secret Stores
Security Configuration
System Configuration
JARVIS Core Integrity
Version Lock
Manifest
Security Policies
Audit Logs
User Authentication Data
```

These resources require additional controls.

---

# 42. CREDENTIAL ACCESS

Credential access is a restricted capability.

An agent should not receive raw credentials merely because it needs to interact with a service.

Preferred model:

```text
Agent
    ↓
Capability
    ↓
Credential Broker
    ↓
Authenticated Operation
```

rather than:

```text
Agent
    ↓
Raw Secret
```

---

# 43. SECRET NON-DISCLOSURE

Where possible, a capability should permit an operation without exposing the underlying secret.

Example:

```text
email.send
```

may be authorized through a credential broker without exposing:

```text
SMTP_PASSWORD
```

to the agent.

---

# 44. HIGH-RISK CAPABILITIES

High-risk capabilities require stronger controls.

Examples:

```text
shell.execute
process.terminate
filesystem.delete
filesystem.write outside workspace
credential.read
credential.export
network unrestricted
browser.payment
email.send
calendar.commit
financial.transaction
security.configuration.modify
JARVIS Core modification
```

The exact classification is maintained by the security and policy layers.

---

# 45. HIGH-IMPACT ACTIONS

High-impact actions should support:

```text
Explicit Permission
Policy Evaluation
User Confirmation where required
Strong Audit
Resource Scoping
Failure Recovery
```

The system must not assume that autonomous execution is appropriate merely because an agent can technically perform the operation.

---

# 46. DESTRUCTIVE OPERATIONS

Destructive operations require explicit policy.

Examples:

```text
delete
terminate
overwrite
revoke
disable
remove
reset
format
destroy
```

The capability model must distinguish:

```text
read
write
modify
delete
execute
```

rather than representing all of them as a single unrestricted capability.

---

# 47. READ VS WRITE

Where possible:

```text
resource.read
```

and:

```text
resource.write
```

must be separate capabilities.

Example:

```text
github.repository.read
github.repository.write
```

An agent authorized to read a repository is not automatically authorized to modify it.

---

# 48. WRITE VS DELETE

Delete must not automatically follow from write.

```text
filesystem.write
    ≠
filesystem.delete
```

This prevents ordinary modification authority from becoming destructive authority.

---

# 49. EXECUTION AUTHORITY

Execution authority must be explicitly modeled.

Examples:

```text
process.start
process.stop
shell.execute
python.execute
docker.execute
```

must not be inferred from general filesystem access.

---

# 50. NETWORK AUTHORITY

Network access must be explicitly controlled.

Examples:

```text
network.http.request
network.tcp.connect
network.dns.resolve
```

may have different risk profiles.

Network permissions should support:

```text
domain allowlists
URL allowlists
port restrictions
protocol restrictions
request limits
authentication requirements
```

---

# 51. BROWSER AUTHORITY

Browser capabilities must be granular.

Examples:

```text
browser.session.create
browser.page.navigate
browser.page.read
browser.page.click
browser.page.type
browser.download
browser.upload
browser.cookie.read
browser.storage.read
```

Sensitive browser state must receive stronger authorization.

---

# 52. COMPUTER CONTROL AUTHORITY

Computer interaction must be capability-based.

Examples:

```text
computer.screen.capture
computer.mouse.move
computer.mouse.click
computer.keyboard.type
computer.window.focus
computer.application.launch
```

Screen capture and input control are distinct capabilities.

---

# 53. MEMORY AUTHORITY

Memory access must be scoped.

Examples:

```text
memory.read
memory.write
memory.delete
memory.search
memory.consolidate
```

An agent should not automatically receive unrestricted access to all memory.

---

# 54. KNOWLEDGE GRAPH AUTHORITY

Knowledge graph access may distinguish:

```text
graph.read
graph.write
graph.delete
graph.link
graph.unlink
```

Sensitive graph namespaces may require additional permissions.

---

# 55. DATABASE AUTHORITY

Database permissions should distinguish:

```text
database.connect
database.read
database.insert
database.update
database.delete
database.schema.modify
```

A database connection does not imply unrestricted SQL execution.

---

# 56. SQL EXECUTION

Raw SQL execution is considered a distinct capability.

Example:

```text
database.sql.execute
```

It should normally be more restricted than:

```text
database.query.read
```

---

# 57. FILESYSTEM AUTHORITY

Filesystem access should support resource-scoped permissions.

Example:

```text
filesystem.file.read
scope:
  D:\AURA\JAS\docs\**
```

does not imply:

```text
D:\Users\...
```

or:

```text
C:\Windows\...
```

---

# 58. SHELL AUTHORITY

Shell execution is a high-risk capability.

The architecture should support:

```text
shell.execute
```

with:

```text
command allowlist
working-directory restriction
environment restriction
network restriction
timeout
resource limits
audit
```

where applicable.

---

# 59. TOOL GATEWAY

Tools must be executed through a centralized gateway.

Conceptually:

```text
Agent
    ↓
Tool Request
    ↓
Capability Resolution
    ↓
Permission Engine
    ↓
Policy Engine
    ↓
Tool Gateway
    ↓
Tool
```

Agents must not bypass the gateway for privileged operations.

---

# 60. CAPABILITY REQUEST

A capability request should contain:

```text
Request ID
Principal
Capability
Operation
Resource
Arguments
Context
Task
Session
Requested Scope
Timestamp
```

---

# 61. AUTHORIZATION DECISION

The Permission Engine returns a deterministic decision.

Possible decisions:

```text
ALLOW
DENY
REQUIRE_APPROVAL
DEFER
RESTRICT
```

The final execution path must respect the decision.

---

# 62. ALLOW

`ALLOW` means:

```text
The request satisfies all required authorization conditions.
```

Execution may continue subject to runtime validation.

---

# 63. DENY

`DENY` means:

```text
The request must not execute.
```

The denial should include a machine-readable reason.

Examples:

```text
CAPABILITY_NOT_FOUND
PERMISSION_NOT_GRANTED
RESOURCE_OUT_OF_SCOPE
POLICY_DENIED
RISK_TOO_HIGH
PROVIDER_UNTRUSTED
INTEGRITY_FAILURE
SESSION_EXPIRED
TASK_EXPIRED
```

---

# 64. REQUIRE APPROVAL

Some actions require explicit user or policy approval.

Flow:

```text
Request
    ↓
Capability
    ↓
Permission
    ↓
Policy
    ↓
Approval Required
    ↓
User / Authorized Approver
    ↓
ALLOW / DENY
```

Approval must be bound to the relevant request.

---

# 65. APPROVAL NON-TRANSFERABILITY

Approval for one operation must not automatically authorize unrelated operations.

Example:

```text
Approve:
send email X
```

does not imply:

```text
send email Y
```

unless the policy explicitly defines a broader scope.

---

# 66. APPROVAL EXPIRATION

Approval may expire after:

```text
operation completion
task completion
session completion
time expiration
policy change
```

---

# 67. PERMISSION ENGINE

JARVIS v1 requires a centralized Permission Engine.

Responsibilities include:

```text
Permission Lookup
Permission Evaluation
Scope Evaluation
Condition Evaluation
Policy Interaction
Approval Handling
Conflict Resolution
Expiration Handling
Revocation Handling
Decision Logging
```

---

# 68. PERMISSION ENGINE BOUNDARY

The Permission Engine must be independent of individual agents.

Agents may request authorization.

Agents must not define authorization rules for themselves.

Therefore:

```text
Agent
    ≠
Authorization Authority
```

---

# 69. POLICY ENGINE

The Policy Engine determines whether a capability invocation satisfies system policy.

Conceptually:

```text
Capability
    +
Permission
    +
Context
    ↓
Policy Engine
    ↓
Decision
```

---

# 70. PERMISSION ENGINE VS POLICY ENGINE

The distinction is:

```text
Permission Engine
    =
Does this principal have authority?

Policy Engine
    =
Is this operation allowed under current policy?
```

Both are required.

---

# 71. CAPABILITY + PERMISSION + POLICY

The authoritative model is:

```text
CAPABILITY
    ↓
Can this operation exist?

PERMISSION
    ↓
Is this principal granted authority?

POLICY
    ↓
Is the operation currently allowed?

CONTEXT
    ↓
Does the current situation satisfy the conditions?

EXECUTION
```

---

# 72. RUNTIME ENFORCEMENT

Authorization must be enforced at execution time.

It is insufficient to authorize a tool during discovery and assume the permission remains valid indefinitely.

The runtime must re-evaluate relevant authorization state before execution.

---

# 73. TIME-OF-CHECK VS TIME-OF-USE

The system must account for state changes between:

```text
authorization check
```

and:

```text
execution
```

High-risk operations should perform an authorization check as close to execution as practical.

---

# 74. CAPABILITY DRIFT

Capability definitions may change.

Examples:

```text
Tool adds a new operation
Plugin changes permissions
MCP server exposes new tools
Provider changes behavior
```

Capability drift must trigger review.

The existing MCP architecture explicitly identifies capability drift as a review condition.

---

# 75. PERMISSION DRIFT

Permission profiles may also change.

Examples:

```text
new permissions
broader resource scopes
new dependencies
new runtime privileges
```

Permission drift must be detected and reviewed.

---

# 76. PROVIDER TRUST

Provider identity and integrity are separate from capability identity.

A capability may be valid while its provider becomes untrusted.

Example:

```text
Capability:
mcp.github.issue.create

Provider:
MCP Server X

Integrity:
FAILED
```

Result:

```text
DENY
```

---

# 77. PLUGIN TRUST

A plugin is not trusted merely because it is installed.

The plugin architecture requires:

```text
Manifest
Identity
Capability Declaration
Permission Profile
Integrity Verification
Compatibility Validation
Policy Evaluation
```

before activation.

---

# 78. MCP TRUST

An MCP server is not trusted merely because it implements MCP.

The existing MCP architecture requires:

```text
Server Identity
Integrity
Authorization
Capability
Permission
Policy
Schema Validation
Execution
Output Validation
Audit
```

for secure execution.

---

# 79. EXTERNAL DATA

External capability results are untrusted data.

Therefore:

```text
MCP Result
    ≠
Trusted Instruction
```

and:

```text
Browser Content
    ≠
System Policy
```

External data must never automatically gain authority.

---

# 80. INSTRUCTION AUTHORITY

The authority hierarchy remains:

```text
JAS / System Policy
        ↓
Security Policy
        ↓
User Instruction
        ↓
Trusted Application State
        ↓
External Data
```

An external capability provider cannot override higher-level policy.

---

# 81. PROMPT INJECTION

Capability execution must assume that external data may contain prompt injection.

Therefore:

```text
External Data
    ↓
Validation / Sanitization
    ↓
Context
```

must not become:

```text
External Data
    ↓
System Instruction
```

automatically.

---

# 82. CAPABILITY METADATA SECURITY

Capability descriptions themselves must not be treated as authoritative instructions.

A malicious or compromised provider must not be able to elevate its own authority through:

```text
tool description
capability description
resource description
prompt
result
metadata
```

---

# 83. PERMISSION ESCALATION

A principal must not be able to grant itself additional permissions.

Therefore:

```text
Agent
    ✗
    ↓
Grant self permission
```

is prohibited.

Likewise:

```text
Plugin
    ✗
    ↓
Grant self permission
```

and:

```text
MCP Server
    ✗
    ↓
Grant self permission
```

are prohibited.

---

# 84. TRANSITIVE PERMISSIONS

Permissions must not automatically propagate through components.

Example:

```text
Agent
    ↓
Plugin
    ↓
MCP Server
```

does not mean that all permissions available to the agent become available to the plugin or MCP server.

Each boundary must be evaluated independently.

---

# 85. DELEGATION

Delegation may be supported, but delegated authority must be explicit.

Conceptually:

```text
Principal A
    ↓
Delegates Capability X
    ↓
Principal B
```

The delegation must define:

```text
capability
scope
duration
conditions
maximum authority
```

---

# 86. NO PRIVILEGE AMPLIFICATION

Delegation must not allow:

```text
B > A
```

in terms of effective authority.

A delegated principal cannot gain privileges greater than those legitimately delegated.

---

# 87. AGENT-TO-AGENT AUTHORIZATION

Agents communicating with other agents must preserve identity.

Example:

```text
Mission Agent
    ↓
Delegates task
    ↓
Research Agent
```

The Research Agent must have its own identity and capability profile.

The Mission Agent cannot silently transfer unrestricted authority.

---

# 88. SUPERVISOR AUTHORITY

The Execution Supervisor may enforce execution constraints, but it must remain subject to system security policy.

Supervisor authority does not override:

```text
Security Deny
System Deny
Protected Resource Rules
```

---

# 89. BACKGROUND TASKS

Background tasks are separate principals or execution contexts where appropriate.

A background task must not automatically inherit every permission available to an interactive agent session.

---

# 90. SCHEDULED TASKS

Scheduled execution must specify its permission profile.

Example:

```text
Task:
daily research

Capabilities:
web.search
filesystem.write

Scope:
workspace/research/**
```

A scheduled task should not silently acquire new privileges because a plugin becomes available later.

---

# 91. USER CONTROL

The user remains the highest operational authority within the limits of system security policy.

User instructions may authorize actions that require explicit user authorization.

However:

```text
User authorization
    ≠
system security bypass
```

System-level safety controls remain authoritative.

---

# 92. USER CONFIRMATION

User confirmation should be used for high-impact operations according to policy.

Examples:

```text
send message
delete important files
financial action
publish content
modify security settings
install untrusted software
grant sensitive permission
```

---

# 93. PERMISSION UI

The frontend should expose permission state clearly.

Users should be able to understand:

```text
Who
can do
What
to Which Resource
Why
Until When
Under Which Conditions
```

---

# 94. PERMISSION VISIBILITY

The system should expose:

```text
Granted Permissions
Denied Permissions
Pending Approvals
Expired Permissions
Revoked Permissions
Restricted Capabilities
```

where appropriate.

---

# 95. PERMISSION MANAGEMENT

The permission management interface should support:

```text
Grant
Deny
Revoke
Review
Inspect Scope
Inspect Expiration
Inspect Provider
Inspect Risk
Inspect Audit History
```

---

# 96. AUDITABILITY

Every privileged capability decision should be auditable.

Audit events should record:

```text
Request ID
Principal
Capability
Provider
Resource
Scope
Decision
Policy
Reason
Approval
Timestamp
Task
Session
Execution Result
```

---

# 97. AUDIT IMMUTABILITY

Security-critical authorization logs should be protected against unauthorized modification.

The exact storage mechanism belongs to the observability and security implementation layers.

---

# 98. DECISION REASON

Every denial should have a machine-readable reason.

Example:

```yaml
decision: DENY
reason: RESOURCE_OUT_OF_SCOPE
capability: filesystem.file.write
resource: D:/secret.txt
principal: agent.coding
```

This improves:

```text
debugging
security analysis
user transparency
testing
compliance
```

---

# 99. AUDIT CORRELATION

Authorization events should be correlated with:

```text
Task ID
Session ID
Agent ID
Tool Call ID
MCP Request ID
Plugin Invocation ID
Trace ID
```

where available.

---

# 100. CAPABILITY RISK

Capabilities should have a risk classification.

Conceptual levels:

```text
T0 / LOW
T1 / RESTRICTED
T2 / NETWORK / EXTERNAL
T3 / HIGH IMPACT
```

The exact security trust-tier model remains governed by the Security Stack.

---

# 101. RISK-BASED AUTHORIZATION

Risk may influence:

```text
approval requirements
sandbox requirements
scope restrictions
audit level
execution limits
credential access
network access
human confirmation
```

---

# 102. SANDBOXING

High-risk capabilities may require isolated execution.

Possible isolation mechanisms include:

```text
Process Isolation
Virtual Environment
Container Isolation
OS Sandbox
Network Isolation
Filesystem Isolation
```

The selected mechanism depends on the capability and runtime.

---

# 103. CAPABILITY-LEVEL ISOLATION

Isolation requirements should be part of capability metadata.

Example:

```yaml
capability: shell.execute
risk: high
isolation:
  required: true
  network: restricted
  filesystem: workspace-only
```

---

# 104. PLUGIN ISOLATION

Dependency-heavy or high-risk plugins should support isolated execution.

Plugin permissions must remain enforceable even when the plugin is isolated.

---

# 105. MCP ISOLATION

Containerized or remote MCP servers may require additional isolation and trust validation.

MCP transport does not eliminate the need for capability and permission enforcement.

---

# 106. TOOL SCHEMA VALIDATION

Authorization does not replace input validation.

The execution pipeline must remain:

```text
Capability
    ↓
Permission
    ↓
Policy
    ↓
Schema Validation
    ↓
Execution
```

A permitted operation with invalid arguments must still be rejected.

---

# 107. OUTPUT VALIDATION

Capability results must also be validated before entering trusted application state.

Especially:

```text
MCP Results
Browser Content
Downloaded Files
External API Results
Plugin Results
```

must be treated according to their trust level.

---

# 108. CAPABILITY DEPENDENCIES

Capabilities may depend on other capabilities.

Example:

```text
github.issue.create
    ↓
github.repository.read
```

Dependencies must be explicitly declared.

They must not create hidden privilege escalation.

---

# 109. DEPENDENCY AUTHORIZATION

If capability A requires capability B:

```text
A
    ↓
requires B
```

then execution must verify authorization for B as well.

---

# 110. COMPOSITE CAPABILITIES

A higher-level capability may compose multiple lower-level capabilities.

Example:

```text
research.execute
    ├── web.search
    ├── browser.read
    ├── filesystem.write
    └── memory.write
```

Composite capabilities must declare their underlying requirements.

---

# 111. COMPOSITE CAPABILITY LIMITS

Granting:

```text
research.execute
```

must not implicitly grant unrelated capabilities.

Only declared constituent operations may be authorized.

---

# 112. CAPABILITY CONTRACT

Every capability must define an executable contract.

Conceptually:

```text
Capability Contract
├── ID
├── Version
├── Provider
├── Input
├── Output
├── Scope
├── Permissions
├── Risk
├── Policy
├── Dependencies
├── Isolation
└── Audit
```

---

# 113. CAPABILITY VERSIONING

Capabilities must be versioned independently where necessary.

Example:

```text
filesystem.file.write@1
filesystem.file.write@2
```

A capability version change may require compatibility review.

---

# 114. PERMISSION VERSIONING

Permission schemas may also evolve.

A permission change that broadens authority must not be silently treated as a compatible update.

---

# 115. VERSION LOCK INTEGRATION

Capability and permission definitions that affect runtime behavior must be compatible with the JAS Version Lock.

The Version Lock must be able to identify:

```text
Capability Provider
Provider Version
Tool Version
Plugin Version
MCP Server Version
Permission Schema
Policy Schema
```

where applicable.

---

# 116. MANIFEST INTEGRATION

The Manifest must describe required capabilities and permission profiles.

Conceptually:

```yaml
capabilities:
  - filesystem.file.read
  - filesystem.file.write

permissions:
  - scope: workspace
```

A manifest declaration is not itself sufficient authorization.

It declares requirements.

---

# 117. MANIFEST VS PERMISSION

The distinction is:

```text
Manifest
    =
What the component requires

Permission
    =
What the component is actually granted
```

Therefore:

```text
Manifest Requirement
    ≠
Automatic Grant
```

---

# 118. BOOTSTRAP INTEGRATION

During bootstrap:

```text
Manifest
    ↓
Capability Discovery
    ↓
Provider Validation
    ↓
Permission Profile Loading
    ↓
Policy Validation
    ↓
Runtime Registration
```

Components failing authorization validation must not become active privileged providers.

---

# 119. SYSTEM VERIFICATION

System Verification must test:

```text
Capability Registration
Capability Discovery
Permission Resolution
Default Deny
Explicit Allow
Scope Enforcement
Policy Enforcement
Revocation
Expiration
High-Risk Controls
Plugin Permissions
MCP Permissions
Audit Logging
```

---

# 120. COMPLIANCE CHECKER

The Compliance Checker must verify that:

```text
Every capability has an owner
Every privileged tool has a capability
Every capability has a risk classification
Every privileged capability has a permission model
Every plugin declares capabilities
Every MCP provider is registered
No forbidden implicit privilege exists
No floating privileged dependency exists
```

---

# 121. BOOTSTRAP FAILURE

If mandatory capability or permission validation fails:

```text
Bootstrap
    ↓
Validation Failure
    ↓
Restricted / Safe State
```

The system must not silently continue with elevated capabilities.

---

# 122. SAFE MODE

JARVIS should support a restricted operational state in which high-risk capabilities are unavailable.

Conceptually:

```text
SAFE MODE
    ↓
Core Diagnostics
    ↓
Read-only Capabilities
    ↓
No High-Risk Execution
```

---

# 123. FAILURE BEHAVIOR

When authorization infrastructure is unavailable:

```text
fail closed
```

for security-sensitive capabilities.

The system must not interpret an authorization service failure as:

```text
ALLOW
```

---

# 124. AVAILABILITY VS SECURITY

Availability requirements must not silently override security requirements.

Example:

```text
Permission Engine unavailable
```

must not result in:

```text
execute anyway
```

for privileged operations.

---

# 125. OFFLINE MODE

Offline operation may use cached authorization state only when policy explicitly allows it.

Cached permissions must have:

```text
expiration
scope
integrity
version
```

and must not bypass revocation mechanisms where revocation status is required.

---

# 126. CACHE SECURITY

Capability and permission caches must be integrity-protected.

A modified cache must be treated as untrusted.

---

# 127. PERMISSION CACHE INVALIDATION

Permission caches must be invalidated after:

```text
Revocation
Policy Change
Provider Change
Capability Drift
Permission Drift
Security Incident
Session End
Task End
```

where applicable.

---

# 128. MULTI-USER SUPPORT

The capability model must not assume that a single runtime identity is equivalent to all users.

Permissions should be attributable to:

```text
User
Session
Agent
Task
Provider
```

as applicable.

---

# 129. SESSION ISOLATION

One user session must not inherit another user's sensitive permissions unless explicitly designed by the security architecture.

---

# 130. TENANT / ACCOUNT ISOLATION

Where external services contain multiple accounts or identities, permissions should be scoped to the relevant account.

Example:

```text
calendar.read
account = user@example
```

must not imply:

```text
calendar.read
account = another-user
```

---

# 131. NETWORK TRUST

Network location does not imply permission.

Therefore:

```text
localhost
    ≠
trusted
```

and:

```text
LAN
    ≠
trusted
```

The security model remains Zero Trust.

---

# 132. LOCAL PROCESS TRUST

A local process does not receive implicit capability authority.

A local process must still have:

```text
identity
capability
permission
policy
```

where required.

---

# 133. INSTALLED SOFTWARE TRUST

Installation does not imply authorization.

An installed executable may be:

```text
available
```

without being:

```text
authorized
```

---

# 134. USER-INITIATED OPERATIONS

A user explicitly requesting an operation may satisfy an approval requirement, but the operation must still pass:

```text
Capability Validation
Permission Validation
Policy Validation
Resource Scope
Security Controls
```

---

# 135. AUTONOMOUS OPERATIONS

Autonomous operations must use predefined permission profiles.

An agent must not dynamically invent permissions based solely on its reasoning.

---

# 136. SELF-MODIFICATION

JARVIS must not allow ordinary agents to modify their own:

```text
Permission Profile
Security Policy
Capability Registry
Manifest
Version Lock
Credential Policy
```

without explicit privileged authority.

---

# 137. SECURITY ADMINISTRATION

Security administration is itself a privileged capability.

Example:

```text
security.permission.grant
security.permission.revoke
security.policy.modify
security.capability.disable
```

These capabilities require elevated controls.

---

# 138. PRIVILEGE ADMINISTRATION

Privilege-management capabilities must not be granted to ordinary agents by default.

They should be restricted to authorized security administration contexts.

---

# 139. EMERGENCY REVOCATION

The system should support rapid revocation of:

```text
Capability
Permission
Plugin
MCP Server
Agent
Credential
Session
```

during security incidents.

---

# 140. KILL SWITCH

High-risk providers should support emergency disablement.

Example:

```text
MCP Server compromised
    ↓
Disable Provider
    ↓
Revoke Capabilities
    ↓
Invalidate Permissions
    ↓
Audit Event
```

---

# 141. OBSERVABILITY

Capability and permission events must integrate with the central observability architecture.

Relevant telemetry:

```text
authorization attempts
denials
approvals
revocations
capability usage
permission usage
policy failures
provider failures
scope violations
```

---

# 142. SECURITY TELEMETRY

Security telemetry must not expose sensitive credentials or protected data.

Logs should record authorization metadata rather than raw secrets.

---

# 143. METRICS

Useful metrics include:

```text
authorization_requests_total
authorization_denials_total
authorization_approvals_total
permission_revocations_total
capability_invocations_total
capability_failures_total
scope_violations_total
policy_denials_total
```

---

# 144. TRACE CORRELATION

Capability execution should be traceable across:

```text
User
    ↓
Task
    ↓
Agent
    ↓
Capability
    ↓
Permission
    ↓
Policy
    ↓
Tool
    ↓
Provider
    ↓
External System
```

---

# 145. TESTING REQUIREMENTS

The capability and permission system must include:

```text
Unit Tests
Contract Tests
Integration Tests
Security Tests
Negative Tests
Boundary Tests
Revocation Tests
Expiration Tests
Scope Tests
Policy Tests
Provider Trust Tests
```

---

# 146. NEGATIVE TESTING

The system must specifically test that unauthorized operations fail.

Examples:

```text
Agent without filesystem.write
    → DENY

Plugin without credential.read
    → DENY

MCP server without permission
    → DENY

Expired permission
    → DENY

Out-of-scope resource
    → DENY

Unknown capability
    → DENY
```

---

# 147. PRIVILEGE ESCALATION TESTING

Tests must verify that no component can escalate privileges through:

```text
tool chaining
plugin chaining
MCP chaining
agent delegation
nested execution
metadata injection
prompt injection
resource aliasing
scope confusion
```

---

# 148. CONFUSED DEPUTY PROTECTION

JARVIS must prevent one principal from using another principal's privileges without authorization.

Example:

```text
Unprivileged Agent
    ↓
Privileged Service
```

must not automatically mean:

```text
Unprivileged Agent
    =
Privileged Service
```

The service must enforce authorization independently.

---

# 149. CAPABILITY CHAINING

Capability chains must preserve the original authorization context.

Example:

```text
Agent
 ↓
Plugin
 ↓
MCP
 ↓
External API
```

Each boundary must preserve:

```text
principal
task
session
scope
policy
audit context
```

---

# 150. NO HIDDEN CAPABILITIES

A provider must not expose undocumented privileged operations.

All executable privileged operations must be represented in the capability model.

---

# 151. DISCOVERY VS EXECUTION

Discovery is not execution.

The following are separate:

```text
Capability discovered
Capability available
Capability authorized
Capability executed
```

Each state must be represented appropriately.

---

# 152. REGISTRY CONSISTENCY

The Capability Registry must remain consistent with:

```text
Plugin Registry
MCP Registry
Tool Registry
Manifest
Version Lock
Security Policy
```

Inconsistency must trigger verification failure or restricted operation.

---

# 153. CAPABILITY COLLISION

Two providers must not silently claim the same authoritative capability identity.

Provider-specific namespaces should be used where necessary.

Example:

```text
mcp.serverA.search
mcp.serverB.search
```

rather than:

```text
search
```

without provenance.

---

# 154. CAPABILITY ALIASES

Aliases may exist for user-facing convenience, but authorization must resolve to a canonical capability ID before execution.

Example:

```text
"search web"
    ↓
web.search
```

---

# 155. HUMAN-READABLE DESCRIPTIONS

Capabilities should have human-readable descriptions.

However:

```text
description
    ≠
authorization rule
```

Descriptions cannot override the formal capability contract.

---

# 156. POLICY-DRIVEN RESTRICTION

Policies may narrow capabilities dynamically.

Example:

```text
Capability:
browser.download

Policy:
DENY executable downloads

Result:
Restricted
```

---

# 157. RESOURCE CLASS POLICIES

Policies may be attached to resource classes.

Examples:

```text
Protected Files
Protected Domains
Sensitive Databases
Credential Stores
Financial Systems
Security Configuration
```

---

# 158. DATA CLASSIFICATION

Permission decisions may depend on data sensitivity.

Conceptual classes:

```text
PUBLIC
INTERNAL
CONFIDENTIAL
SENSITIVE
CRITICAL
```

The exact data classification system belongs to the Security and Memory layers.

---

# 159. DATA FLOW AUTHORIZATION

Capabilities that move data between trust zones require explicit authorization.

Example:

```text
Local Sensitive Data
    ↓
External Network
```

must not be implicitly permitted by:

```text
filesystem.read
```

alone.

---

# 160. EXFILTRATION CONTROL

A read capability must not automatically imply permission to transmit the read data externally.

For example:

```text
filesystem.read
    ≠
network.send
```

This separation is mandatory for sensitive resources.

---

# 161. CROSS-DOMAIN ACTIONS

Composite actions involving multiple security domains must authorize every domain.

Example:

```text
Read File
    +
Upload File
```

requires:

```text
filesystem.read
+
network.upload
```

and applicable policy authorization.

---

# 162. USER DATA PROTECTION

User data access must remain scoped.

Examples:

```text
documents
email
calendar
browser history
memory
personal files
```

must not be exposed globally to every agent.

---

# 163. AGENT CAPABILITY PROFILES

Each specialized agent should have a capability profile.

Example:

```text
Research Agent
    ├── web.search
    ├── browser.read
    └── memory.write

Coding Agent
    ├── filesystem.read
    ├── filesystem.write
    ├── git.read
    └── git.write
```

---

# 164. MINIMAL AGENT PROFILES

Agent profiles should be minimal.

The existence of a specialized agent does not justify granting every capability relevant to the entire JARVIS system.

---

# 165. AGENT PROFILE VERSIONING

Agent capability profiles should be versioned.

A profile change that expands authority must trigger compatibility and security review.

---

# 166. AGENT PROFILE VALIDATION

At agent activation:

```text
Agent Manifest
    ↓
Capability Requirements
    ↓
Permission Profile
    ↓
Policy
    ↓
Validation
    ↓
Activation
```

---

# 167. CAPABILITY REQUEST BROKER

The runtime should provide a central capability request mechanism.

Agents should request:

```text
request_capability(...)
```

rather than directly invoking privileged implementation details.

---

# 168. INTERNAL IMPLEMENTATION HIDING

Capability consumers should not need to know:

```text
filesystem implementation
database driver
MCP transport
plugin process model
credential implementation
```

They interact through the capability contract.

---

# 169. ARCHITECTURAL ABSTRACTION

The architecture therefore becomes:

```text
Agent
   ↓
Capability
   ↓
Permission
   ↓
Policy
   ↓
Gateway
   ↓
Provider
   ↓
Implementation
```

This preserves dependency inversion.

---

# 170. CAPABILITY GATEWAY

The Capability Gateway is the common entry point for executable capabilities.

It should provide:

```text
Request Validation
Capability Resolution
Authorization
Policy Enforcement
Schema Validation
Execution Dispatch
Result Validation
Audit
```

---

# 171. PROVIDER ADAPTER

A provider adapter translates a canonical capability into the provider-specific operation.

Example:

```text
canonical:
github.repository.read

provider:
MCP GitHub Server

operation:
mcp.github.repo.get
```

The agent should not bypass the canonical capability model.

---

# 172. PROVIDER INDEPENDENCE

Capability consumers should remain decoupled from individual providers where possible.

This allows:

```text
Provider A
    ↓
replacement
    ↓
Provider B
```

without changing the authorization model.

---

# 173. PROVIDER SELECTION

When multiple providers implement a capability, provider selection must respect:

```text
trust
version
availability
security
permissions
policy
latency
resource constraints
```

Provider selection does not bypass authorization.

---

# 174. FALLBACK PROVIDERS

Fallback execution is allowed only if the fallback provider also satisfies authorization.

Example:

```text
Provider A unavailable
    ↓
Provider B
    ↓
Permission Check
    ↓
Policy Check
    ↓
Execution
```

---

# 175. NO AUTHORIZATION BY FALLBACK

A provider fallback must never be used as a method to circumvent a denial.

```text
Provider A denied
    ≠
try Provider B without authorization
```

---

# 176. CAPABILITY RESOLUTION ORDER

The preferred resolution flow is:

```text
Request
    ↓
Canonical Capability
    ↓
Capability Registry
    ↓
Provider Resolution
    ↓
Permission Evaluation
    ↓
Policy Evaluation
    ↓
Scope Evaluation
    ↓
Schema Validation
    ↓
Execution
```

---

# 177. EXECUTION CONTEXT

Every privileged execution should carry an execution context containing:

```text
Principal
Task
Session
Capability
Permission
Policy
Resource
Provider
Trace
Approval
```

---

# 178. CONTEXT PROPAGATION

Execution context must propagate across internal boundaries.

Example:

```text
Agent
 ↓
Plugin
 ↓
MCP Gateway
 ↓
MCP Server
```

must retain sufficient context for authorization and audit.

---

# 179. CONTEXT INTEGRITY

A lower-trust component must not be able to modify authorization context to gain privileges.

For example:

```text
plugin says:
"principal = administrator"
```

must not be accepted merely because the plugin supplied that metadata.

Identity must originate from a trusted runtime boundary.

---

# 180. IDENTITY PROVENANCE

Authorization decisions must use trusted identity sources.

Potential sources:

```text
Runtime Identity
Session Identity
Authenticated User
Signed Manifest
Trusted Registry
Provider Identity
```

---

# 181. PERMISSION ISSUER

Every persistent permission grant should have an identifiable issuer.

Possible issuers:

```text
System Policy
User
Security Administrator
Bootstrap Configuration
Approved Profile
```

---

# 182. GRANT TRACEABILITY

A permission should be traceable to its origin.

Example:

```text
Permission:
filesystem.write

Source:
user-approved coding profile

Scope:
D:/AURA/JAS

Issued:
2026-08-11
```

---

# 183. PERMISSION REVIEW

Permissions should be periodically reviewable.

Review triggers include:

```text
version update
provider change
capability drift
security incident
policy change
long inactivity
scope expansion
```

---

# 184. STALE PERMISSIONS

Unused permissions should be identifiable as stale.

The system may recommend removal, but automatic removal must follow the applicable policy.

---

# 185. PERMISSION MINIMIZATION

The long-term goal is:

```text
minimum required authority
```

rather than:

```text
maximum available authority
```

---

# 186. CAPABILITY DISCOVERY FOR AGENTS

Agents should only discover capabilities that are relevant and visible to their current authorization context where practical.

This reduces:

```text
tool confusion
attack surface
prompt injection surface
unnecessary privilege exposure
```

---

# 187. TOOL CATALOG FILTERING

The Tool Registry should be able to filter tools according to:

```text
agent
permission
policy
scope
risk
availability
```

An unauthorized tool should not be presented as executable.

---

# 188. HIDDEN VS DENIED

There is a distinction between:

```text
not discoverable
```

and:

```text
discoverable but denied
```

Security-sensitive capabilities may be hidden entirely from unauthorized principals.

---

# 189. EXPLAINABLE AUTHORIZATION

For debugging and user-facing interfaces, the system should be able to explain:

```text
Allowed because:
capability + permission + policy + scope

Denied because:
permission missing
```

Explanations must not expose sensitive security internals unnecessarily.

---

# 190. SECURITY BOUNDARY

The capability system forms a security boundary between:

```text
Intent
```

and:

```text
Execution
```

This is one of the most important architectural properties of JARVIS.

---

# 191. FINAL EXECUTION BOUNDARY

The final execution boundary is:

```text
Intent
   ↓
Agent
   ↓
Capability Request
   ↓
Capability Registry
   ↓
Permission Engine
   ↓
Policy Engine
   ↓
Scope Validation
   ↓
Schema Validation
   ↓
Execution Gateway
   ↓
Provider
```

---

# 192. COMPLETE AUTHORIZATION FLOW

The canonical JARVIS v1 flow is:

```text
┌──────────────────────────────┐
│            USER              │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│          INTENT              │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│       AGENT / PLANNER        │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│    CAPABILITY REQUEST        │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│    CAPABILITY REGISTRY       │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│      PERMISSION ENGINE       │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│        POLICY ENGINE         │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│       SCOPE VALIDATION       │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│      APPROVAL IF NEEDED      │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│       SCHEMA VALIDATION      │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│       EXECUTION GATEWAY      │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│        TOOL / PLUGIN /       │
│          MCP PROVIDER        │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│       RESULT VALIDATION      │
└──────────────┬───────────────┘
               ↓
┌──────────────────────────────┐
│        AUDIT / TRACE         │
└──────────────────────────────┘
```

---

# 193. PLUGIN AUTHORIZATION FLOW

```text
Plugin
   ↓
Plugin Manifest
   ↓
Declared Capabilities
   ↓
Capability Registry
   ↓
Permission Profile
   ↓
Policy
   ↓
Plugin Gateway
   ↓
Plugin Execution
```

The plugin must not directly bypass the permission boundary.

---

# 194. MCP AUTHORIZATION FLOW

```text
Agent
   ↓
Capability Registry
   ↓
MCP Tool
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
```

This is consistent with the existing MCP architecture.

---

# 195. COMPUTER CONTROL AUTHORIZATION FLOW

```text
Agent
   ↓
computer.*
   ↓
Permission
   ↓
Policy
   ↓
Resource Scope
   ↓
Computer Gateway
   ↓
OS Integration
```

---

# 196. FILESYSTEM AUTHORIZATION FLOW

```text
Agent
   ↓
filesystem.file.write
   ↓
Permission
   ↓
Path Scope
   ↓
Policy
   ↓
Filesystem Gateway
   ↓
OS
```

---

# 197. NETWORK AUTHORIZATION FLOW

```text
Agent
   ↓
network.http.request
   ↓
Permission
   ↓
Domain / URL Scope
   ↓
Policy
   ↓
Network Gateway
   ↓
External Service
```

---

# 198. EMAIL AUTHORIZATION FLOW

```text
Agent
   ↓
email.message.send
   ↓
Permission
   ↓
Recipient / Account Scope
   ↓
Policy
   ↓
Approval if required
   ↓
Email Provider
```

Sending email is therefore distinct from merely reading email.

---

# 199. CALENDAR AUTHORIZATION FLOW

```text
Agent
   ↓
calendar.event.create
   ↓
Permission
   ↓
Calendar Scope
   ↓
Policy
   ↓
Confirmation if required
   ↓
Calendar Provider
```

External commitments remain subject to policy.

---

# 200. FINANCIAL ACTIONS

Financial operations must be treated as high-risk.

Autonomous financial transactions must not be enabled by default.

Any future financial capability must define:

```text
explicit authorization
strict resource scope
approval
audit
risk policy
revocation
```

---

# 201. CAPABILITY SECURITY INVARIANTS

The following invariants are mandatory:

```text
1. Unknown capability → DENY
2. Unknown provider → DENY
3. Missing permission → DENY
4. Out-of-scope resource → DENY
5. Policy violation → DENY
6. Invalid schema → DENY
7. Failed integrity → DISABLE / DENY
8. Expired permission → DENY
9. Revoked permission → DENY
10. Unauthorized privilege escalation → DENY
11. Provider discovery → does not imply trust
12. Installation → does not imply permission
13. Capability declaration → does not imply grant
14. Model output → does not imply authority
15. External data → does not imply authority
16. Deny overrides allow
17. Security failure → fail closed
```

---

# 202. ARCHITECTURAL NON-GOALS

This document does not define:

```text
LLM reasoning internals
Agent planning algorithms
Plugin implementation details
MCP protocol internals
Database implementation
Frontend implementation
Operating system implementation
Credential storage implementation
```

Those remain defined by their respective architectural documents.

This document defines the authorization boundary between them.

---

# 203. RELATIONSHIP TO AGENT ARCHITECTURE

The Agent Runtime may:

```text
reason
plan
select tools
request capabilities
```

but it may not bypass:

```text
Capability Registry
Permission Engine
Policy Engine
Execution Gateway
```

---

# 204. RELATIONSHIP TO PLUGIN ARCHITECTURE

Plugins remain:

```text
JARVIS-native extensions
```

but are constrained by:

```text
Capability
Permission
Policy
Isolation
Audit
```

The plugin system therefore remains separate from the capability authorization authority.

---

# 205. RELATIONSHIP TO MCP

MCP remains:

```text
external capability interoperability
```

and not:

```text
security policy
authorization authority
JARVIS Core
agent runtime
plugin system
```

MCP providers must pass through JARVIS authorization controls.

---

# 206. RELATIONSHIP TO SECURITY

The capability architecture implements the authorization portion of the broader:

```text
Zero Trust
Defense in Depth
Least Privilege
Default Deny
Explicit Authorization
Auditability
Fail-Safe
```

security model.

---

# 207. RELATIONSHIP TO VERSION LOCK

The capability model must be version-compatible with:

```text
Provider Versions
Tool Versions
Plugin Versions
MCP Server Versions
Permission Schema
Policy Schema
Manifest Schema
```

Version Lock is the authoritative source for locked runtime versions.

---

# 208. RELATIONSHIP TO MANIFEST

Manifest defines declared requirements.

Capability Registry defines available capabilities.

Permission Engine defines granted authority.

Policy Engine defines runtime admissibility.

These roles must remain separate.

---

# 209. RELATIONSHIP TO BOOTSTRAP

Bootstrap establishes the initial trusted runtime.

Capability and permission services must be initialized before privileged runtime components are activated.

---

# 210. RELATIONSHIP TO SYSTEM VERIFICATION

System Verification must verify that:

```text
Declared Capability
    =
Registered Capability
    =
Authorized Capability
    =
Executable Capability
```

where applicable.

Any unauthorized discrepancy must fail verification or place the system into a restricted state.

---

# 211. DEFINITION OF DONE

The Capability and Permission Architecture is considered implementation-complete when:

```text
[ ] Capability Registry implemented
[ ] Stable capability IDs implemented
[ ] Capability namespaces implemented
[ ] Capability metadata implemented
[ ] Capability lifecycle implemented
[ ] Capability ownership implemented
[ ] Capability risk classification implemented
[ ] Permission Engine implemented
[ ] Default deny implemented
[ ] Explicit grants implemented
[ ] Resource scoping implemented
[ ] Session-aware permissions implemented
[ ] Task-aware permissions implemented
[ ] Permission expiration implemented
[ ] Permission revocation implemented
[ ] Policy Engine integration implemented
[ ] Approval flow implemented
[ ] High-risk capability controls implemented
[ ] Tool Gateway integration implemented
[ ] Plugin integration implemented
[ ] MCP integration implemented
[ ] Manifest integration implemented
[ ] Version Lock integration implemented
[ ] Bootstrap integration implemented
[ ] System Verification integration implemented
[ ] Compliance Checker integration implemented
[ ] Audit logging implemented
[ ] Trace correlation implemented
[ ] Capability drift detection implemented
[ ] Permission drift detection implemented
[ ] Negative authorization tests implemented
[ ] Privilege escalation tests implemented
[ ] Scope enforcement tests implemented
[ ] Revocation tests implemented
[ ] Expiration tests implemented
[ ] Fail-closed behavior implemented
```

---

# 212. FINAL ARCHITECTURAL MODEL

The final JARVIS capability architecture is:

```text
                         USER
                          │
                          ▼
                       INTENT
                          │
                          ▼
                  AGENT / PLANNER
                          │
                          ▼
                 CAPABILITY REQUEST
                          │
                          ▼
               ┌────────────────────┐
               │ CAPABILITY REGISTRY│
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │ PERMISSION ENGINE  │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │   POLICY ENGINE    │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │   SCOPE / CONTEXT  │
               │     VALIDATION     │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │ APPROVAL IF NEEDED │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │ SCHEMA VALIDATION  │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │ EXECUTION GATEWAY  │
               └─────────┬──────────┘
                         │
             ┌───────────┼───────────┐
             ▼           ▼           ▼
          CORE        PLUGIN        MCP
             │           │           │
             └───────────┼───────────┘
                         │
                         ▼
                     PROVIDER
                         │
                         ▼
                 EXTERNAL / LOCAL
                     RESOURCE
                         │
                         ▼
                 RESULT VALIDATION
                         │
                         ▼
                    AUDIT / TRACE
```

---

# 213. FINAL RULES

### Rule 1

**Every privileged operation must correspond to a capability.**

### Rule 2

**Capability does not imply permission.**

### Rule 3

**Permission does not override policy.**

### Rule 4

**Default permission state is DENY.**

### Rule 5

**Explicit authorization is required.**

### Rule 6

**Least privilege is mandatory.**

### Rule 7

**Permissions must be scoped whenever possible.**

### Rule 8

**Permissions may be session-bound or task-bound.**

### Rule 9

**Permissions must be revocable.**

### Rule 10

**Expired permissions are invalid.**

### Rule 11

**Deny overrides allow.**

### Rule 12

**Agents cannot grant themselves permissions.**

### Rule 13

**Plugins cannot grant themselves permissions.**

### Rule 14

**MCP servers cannot grant themselves permissions.**

### Rule 15

**Model output is never an authorization decision.**

### Rule 16

**External data is never automatically trusted instruction.**

### Rule 17

**Discovery does not imply trust.**

### Rule 18

**Installation does not imply authorization.**

### Rule 19

**Manifest declaration does not imply permission grant.**

### Rule 20

**Provider identity and capability identity must remain distinct.**

### Rule 21

**High-risk capabilities require stronger controls.**

### Rule 22

**Destructive operations require explicit policy.**

### Rule 23

**Read authority does not imply write authority.**

### Rule 24

**Write authority does not imply delete authority.**

### Rule 25

**Filesystem authority does not imply network authority.**

### Rule 26

**Network authority does not imply credential authority.**

### Rule 27

**Capability chains must preserve authorization context.**

### Rule 28

**Delegation must not create privilege amplification.**

### Rule 29

**Privileged execution must be auditable.**

### Rule 30

**Security-sensitive authorization failures must fail closed.**

### Rule 31

**Capability drift requires review.**

### Rule 32

**Permission drift requires review.**

### Rule 33

**Protected resources require additional authorization controls.**

### Rule 34

**Capability execution must pass through an enforceable execution boundary.**

### Rule 35

**The Capability Registry is authoritative for capability identity and metadata.**

### Rule 36

**The Permission Engine is authoritative for permission evaluation.**

### Rule 37

**The Policy Engine is authoritative for policy admissibility.**

### Rule 38

**No agent, plugin or MCP server may bypass the authorization boundary.**

### Rule 39

**Capability, permission, policy and execution remain separate architectural concerns.**

### Rule 40

**The JARVIS capability system must remain modular, auditable, versioned, revocable and least-privileged.**

---

# 214. FINAL STATEMENT

The JARVIS v1 capability architecture is therefore defined as:

```text
CAPABILITY-BASED
+
CENTRALIZED
+
DEFAULT-DENY
+
LEAST-PRIVILEGE
+
EXPLICITLY-AUTHORIZED
+
RESOURCE-SCOPED
+
CONTEXT-AWARE
+
POLICY-ENFORCED
+
REVOCABLE
+
AUDITABLE
+
VERSIONED
+
FAIL-CLOSED
```

The resulting architectural principle is:

```text
JARVIS may know how to perform an action
        ≠
JARVIS is allowed to perform the action
```

Authorization exists as an independent architectural boundary between intelligence and execution.

Therefore the final execution rule is:

```text
INTELLIGENCE
    ↓
INTENT
    ↓
CAPABILITY
    ↓
PERMISSION
    ↓
POLICY
    ↓
CONTEXT
    ↓
SCOPE
    ↓
APPROVAL
    ↓
VALIDATION
    ↓
EXECUTION
    ↓
AUDIT
```

This model is the authoritative Capability and Permission Architecture for JARVIS v1.