# 11 — BACKEND STACK

**Document ID:** JAS-AS-11  
**Document:** `11_BACKEND_STACK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED STACK SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  
**Depends On:** JAS v1, `00_APPROVED_STACK_OVERVIEW.md`, `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`, `02_CORE_RUNTIME_AND_PROGRAMMING_LANGUAGES.md`, `03_AI_AND_LLM_FRAMEWORKS.md`, `04_AGENT_ORCHESTRATION_STACK.md`, `05_MEMORY_AND_VECTOR_DATABASE_STACK.md`, `06_DATABASE_AND_STORAGE_STACK.md`, `10_FRONTEND_STACK.md`  
**Related Documents:** `07_BROWSER_AUTOMATION_STACK.md`, `08_VOICE_AND_AUDIO_STACK.md`, `09_COMPUTER_VISION_STACK.md`, `12_PLUGIN_AND_EXTENSION_STACK.md`, `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`, `14_SECURITY_STACK.md`, `15_DEVOPS_AND_DEPLOYMENT_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, System Verification, JARVIS Core

---

# 1. PURPOSE

This document defines the approved backend technology direction and architectural boundaries for JARVIS.

The backend is not merely:

```text
API Server
```

It is the controlled application and service layer connecting:

```text
Frontend
    ↓
API / Events
    ↓
Backend Services
    ↓
JARVIS Core
    ↓
Agents / Memory / Tools / Integrations
    ↓
Infrastructure
```

The backend therefore acts as:

> **The controlled execution, coordination, security-enforcement and service boundary of JARVIS.**

---

# 2. PRIMARY OBJECTIVE

The backend must provide a stable and secure interface between user-facing clients and the internal JARVIS system.

It must support:

```text
HTTP APIs
WebSocket Communication
Streaming
Authentication
Authorization
Policy Enforcement
Task Management
Agent Coordination
Tool Invocation
Memory Access
Plugin Integration
MCP Integration
Voice Integration
Vision Integration
Browser Integration
Persistence
Caching
Background Execution
Observability
Health Monitoring
Configuration
```

---

# 3. CORE ARCHITECTURAL PRINCIPLE

The backend must remain separate from:

```text
Frontend
Database
LLM Provider
Agent Framework
Browser Automation
MCP Server
Plugin
Operating System
```

The backend coordinates these systems.

It does not become tightly coupled to one implementation of each.

---

# 4. HIGH-LEVEL ARCHITECTURE

The target architecture is:

```text
                              USER
                                │
                    ┌───────────┴───────────┐
                    │                       │
                 FRONTEND               OTHER CLIENT
                    │                       │
                    └───────────┬───────────┘
                                │
                                ▼
                         API / EVENT GATEWAY
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
              ▼                 ▼                 ▼
        Authentication     API Services      Realtime Events
              │                 │                 │
              └─────────────────┼─────────────────┘
                                ▼
                       APPLICATION SERVICES
                                │
       ┌────────────┬───────────┼───────────┬────────────┐
       ▼            ▼           ▼           ▼            ▼
    Tasks        Agents       Memory       Tools       Sessions
       │            │           │           │            │
       └────────────┴───────────┼───────────┴────────────┘
                                ▼
                         JARVIS CORE
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
       Models                Plugins                 MCP
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
                         INFRASTRUCTURE
                                │
          ┌──────────────┬──────┴──────┬──────────────┐
          ▼              ▼             ▼              ▼
      PostgreSQL       Redis        Object Store    External APIs
```

---

# 5. BACKEND IS NOT JARVIS CORE

One of the most important architectural rules is:

```text
Backend ≠ JARVIS Core
```

The backend provides:

```text
Transport
Authentication
Authorization
API
Sessions
Task Submission
State Access
Event Delivery
Service Coordination
```

The Core provides:

```text
Reasoning
Planning
Agent Execution
Memory Operations
Tool Selection
System Intelligence
```

---

# 6. PRIMARY BACKEND LANGUAGE

**Selected Language: Python**

Status:

```text
APPROVED
```

Python is the primary backend/application language for JARVIS.

---

# 7. WHY PYTHON

Python is selected because the JARVIS backend must integrate tightly with:

```text
LLMs
Machine Learning
Computer Vision
Speech
Browser Automation
Agent Frameworks
Scientific Libraries
AI Inference
Data Processing
```

Python also provides a mature ecosystem for these domains.

---

# 8. PYTHON ROLE

Python is the default language for:

```text
Backend
Application Services
Agent Runtime
AI Integration
Tool Adapters
Memory Services
Model Adapters
Automation
Inference Integration
```

---

# 9. SECONDARY LANGUAGES

Other languages may be used for specialized components.

Potential examples:

```text
Rust
C++
TypeScript
SQL
Shell
```

However:

> A secondary language must have an explicit architectural reason.

It must not be introduced merely because it is technically possible.

---

# 10. PRIMARY WEB FRAMEWORK

**Selected Technology: FastAPI**

Status:

```text
APPROVED
```

FastAPI is built around OpenAPI and JSON Schema and includes WebSocket, streaming response, startup/shutdown and testing capabilities. citeturn0search0

---

# 11. WHY FASTAPI

FastAPI provides a strong fit for JARVIS because the backend requires:

```text
Typed APIs
Async Execution
OpenAPI
JSON Schema
WebSockets
Streaming
Validation
Dependency Injection
Automatic API Documentation
Testing Support
```

---

# 12. FASTAPI RESPONSIBILITY

FastAPI is responsible primarily for:

```text
HTTP API
WebSocket Endpoints
Request Validation
Response Serialization
OpenAPI Contract
Dependency Injection
Authentication Integration
Middleware
Streaming
```

FastAPI is not responsible for:

```text
Agent Reasoning
Memory Database
LLM Selection
Tool Authorization Policy
Background Worker Infrastructure
```

---

# 13. ASGI FOUNDATION

FastAPI uses the Starlette ASGI framework underneath.

Starlette provides ASGI support, WebSockets, streaming, middleware and async service capabilities. citeturn0search1turn0search2

Therefore the backend architecture is:

```text
JARVIS
 ↓
FastAPI
 ↓
Starlette / ASGI
 ↓
ASGI Server
```

---

# 14. ASGI SERVER

The production ASGI server must be selected and version-locked separately.

Preferred candidate:

```text
Uvicorn
```

Status:

```text
APPROVED CANDIDATE
```

Exact server configuration belongs to deployment architecture.

---

# 15. API STANDARD

The primary external backend API style is:

```text
REST + OpenAPI
```

Status:

```text
APPROVED
```

---

# 16. REST ROLE

REST APIs should be used for:

```text
CRUD
Configuration
Authentication
Task Submission
Task Queries
Memory Queries
Settings
System Information
Administrative Operations
```

---

# 17. API DESIGN

APIs should be resource-oriented.

Example:

```text
GET    /api/v1/tasks
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/cancel
```

rather than arbitrary action-heavy endpoints.

---

# 18. API VERSIONING

The backend should use explicit API versions.

Initial target:

```text
/api/v1/
```

Future evolution:

```text
/api/v2/
```

must be controlled.

---

# 19. OPENAPI

OpenAPI is the authoritative description of HTTP API contracts.

FastAPI can generate OpenAPI documentation automatically. citeturn0search0

The OpenAPI document should eventually feed:

```text
Frontend Type Generation
API Testing
Documentation
Compliance
Contract Validation
```

---

# 20. API CONTRACT PRINCIPLE

The frontend must never depend on undocumented backend behavior.

Correct:

```text
Backend Schema
      ↓
OpenAPI
      ↓
Frontend Client
```

Incorrect:

```text
Frontend guesses backend response shape
```

---

# 21. PYDANTIC

**Selected Technology: Pydantic v2**

Status:

```text
APPROVED
```

Pydantic is the primary backend schema and validation layer.

---

# 22. PYDANTIC RESPONSIBILITY

Pydantic should be used for:

```text
Request Models
Response Models
Configuration
Domain DTOs
Event Payloads
Validation
Serialization
```

---

# 23. VALIDATION PRINCIPLE

Every external boundary must validate input.

Boundaries include:

```text
HTTP
WebSocket
Plugin
MCP
External API
File Metadata
Configuration
Environment Variables
```

---

# 24. DOMAIN MODELS VS API MODELS

The backend should distinguish:

```text
API Model
```

from:

```text
Domain Model
```

when necessary.

Not every internal domain object should automatically become a public API object.

---

# 25. PYDANTIC CONFIGURATION

Configuration should be represented using typed models.

Conceptually:

```text
Environment
 ↓
Configuration Loader
 ↓
Pydantic Settings
 ↓
Validated Application Configuration
```

---

# 26. DATA SERIALIZATION

Backend communication should use explicit schemas.

Avoid arbitrary:

```python
dict[str, Any]
```

as the universal data model.

Dynamic structures are permitted where the domain genuinely requires them.

---

# 27. WEBSOCKET

**Selected Technology: WebSocket**

Status:

```text
APPROVED
```

WebSocket is the preferred bidirectional realtime transport for JARVIS.

Starlette provides native WebSocket support, including async send/receive and JSON/text/byte iteration. citeturn0search1

---

# 28. WEBSOCKET USE CASES

WebSocket should be used for:

```text
Agent Activity
Task Progress
Streaming
Voice Sessions
Interactive Sessions
Tool Events
Realtime Notifications
Connection State
```

---

# 29. WEBSOCKET IS NOT THE DATABASE

WebSocket is a transport.

It must not become the authoritative source of persistent state.

Correct:

```text
Task State
 ↓
Backend Persistence
 ↓
WebSocket Event
 ↓
Frontend
```

---

# 30. EVENT ARCHITECTURE

Backend events should have a standard envelope.

Conceptually:

```yaml
event:
  id: ...
  type: ...
  version: ...
  timestamp: ...
  request_id: ...
  trace_id: ...
  conversation_id: ...
  task_id: ...
  agent_id: ...
  payload: ...
```

---

# 31. EVENT TYPES

Potential event categories:

```text
message.*
agent.*
task.*
tool.*
memory.*
voice.*
vision.*
browser.*
system.*
permission.*
notification.*
```

---

# 32. EVENT VERSIONING

Events should be versioned.

Example:

```text
agent.started.v1
agent.completed.v1
tool.started.v1
tool.completed.v1
message.delta.v1
task.progress.v1
```

---

# 33. EVENT DELIVERY

The backend should distinguish:

```text
Transient Event
```

from:

```text
Persistent Event
```

Not every event must be persisted forever.

---

# 34. EVENT REPLAY

Important task and system events may require replay.

This is particularly useful for:

```text
Long-running Tasks
Agent Execution
Audit
Recovery
Frontend Reconnection
```

---

# 35. REALTIME RECONNECTION

The backend should support:

```text
Reconnect
Session Resumption
Event Replay
Duplicate Detection
Ordering
```

where required.

---

# 36. SSE

Server-Sent Events may be supported.

Status:

```text
OPTIONAL
```

SSE is appropriate when communication is primarily:

```text
Server
 ↓
Client
```

and bidirectional communication is unnecessary.

---

# 37. HTTP STREAMING

HTTP streaming may be used for:

```text
Large Responses
File Downloads
Generated Artifacts
Server Streaming
```

---

# 38. DATABASE

**Selected Primary Database: PostgreSQL**

Status:

```text
APPROVED
```

PostgreSQL provides relational persistence together with JSON/JSONB functionality, allowing structured relational data and flexible metadata to coexist. citeturn0search11

---

# 39. WHY POSTGRESQL

JARVIS requires durable storage for:

```text
Users
Sessions
Tasks
Conversations
Permissions
Configuration
Agent Runs
Tool Runs
Audit Records
Plugin Metadata
MCP Metadata
System State
```

PostgreSQL provides a mature relational foundation for these workloads.

---

# 40. POSTGRESQL ROLE

PostgreSQL is the authoritative persistent relational database.

It should store:

```text
Durable Application State
```

not:

```text
Ephemeral Cache
```

or:

```text
Temporary Event Transport
```

---

# 41. JSONB

JSONB may be used for:

```text
Flexible Metadata
Provider-specific Metadata
Plugin Configuration
Tool Metadata
Event Metadata
```

but should not replace relational schema design.

---

# 42. RELATIONAL-FIRST PRINCIPLE

Important core entities should have explicit relational structures.

Example:

```text
tasks
agents
agent_runs
tool_runs
sessions
users
permissions
```

rather than placing the entire application into a generic JSON document.

---

# 43. ORM

**Selected Technology: SQLAlchemy 2.x**

Status:

```text
APPROVED
```

SQLAlchemy 2.x provides modern ORM/query APIs and asynchronous I/O support. citeturn0search3turn0search4

---

# 44. WHY SQLALCHEMY

SQLAlchemy provides:

```text
ORM
SQL Expression Language
Transactions
Connection Management
AsyncIO
Migrations Compatibility
Typed Models
Database Abstraction
```

---

# 45. SQLALCHEMY POLICY

Use modern SQLAlchemy 2.x style.

Avoid introducing legacy 1.x query patterns into new code.

SQLAlchemy's current 2.x documentation uses the modern `select()` style and `Session.execute()` pattern. citeturn0search6

---

# 46. ASYNC DATABASE ACCESS

Async database access should be used where it provides clear value.

The backend should avoid blocking the event loop with synchronous database calls in asynchronous request paths.

---

# 47. TRANSACTIONS

Database operations requiring atomicity must use explicit transactions.

Examples:

```text
Task Creation
Permission Update
Agent State Transition
Audit Record + State Change
```

---

# 48. DATABASE MIGRATIONS

A migration system is required.

Candidate:

```text
Alembic
```

Status:

```text
APPROVED CANDIDATE
```

Exact version belongs to Version Lock.

---

# 49. MIGRATION POLICY

Database schema changes must be:

```text
Versioned
Reviewable
Reversible where practical
Tested
Environment-aware
```

---

# 50. REDIS

**Selected Technology: Redis**

Status:

```text
APPROVED
```

Redis is intended for ephemeral and coordination workloads rather than replacing PostgreSQL as the durable application database.

---

# 51. REDIS USE CASES

Potential uses:

```text
Cache
Session Data
Rate Limiting
Distributed Locks
Short-Lived State
Task Coordination
Event Streams
Pub/Sub
```

---

# 52. REDIS STREAMS

Redis Streams may be used for internal event/task pipelines.

Redis documents Streams as append-only logs with consumer-group support and event/notification use cases. citeturn0search5

---

# 53. REDIS IS NOT PRIMARY DATABASE

The following must not depend exclusively on Redis:

```text
Permanent Memory
Critical User Data
Audit History
Long-Term Tasks
Configuration
```

---

# 54. CACHE POLICY

Cache should be treated as disposable.

If Redis disappears:

```text
Application
```

should recover from durable sources where architecture requires persistence.

---

# 55. BACKGROUND TASKS

FastAPI's in-process background tasks are useful for small tasks, but they are not sufficient as the general execution system for JARVIS.

FastAPI includes in-process background task support, but long-running or distributed work requires a dedicated worker architecture. citeturn0search0

---

# 56. WORKER ARCHITECTURE

Long-running tasks should execute outside the primary API process.

Conceptually:

```text
Frontend
   ↓
API
   ↓
Task Queue
   ↓
Worker
   ↓
JARVIS Core / Agent
```

---

# 57. WHY WORKERS

JARVIS tasks may take:

```text
Seconds
Minutes
Hours
```

Examples:

```text
Research
Video Analysis
Large File Processing
Coding
Browser Automation
Model Inference
Long Agent Workflows
```

The API process must remain responsive.

---

# 58. WORKER TYPES

Potential worker classes:

```text
General Worker
Agent Worker
Browser Worker
Vision Worker
Voice Worker
Model Worker
File Worker
Scheduled Worker
```

The exact topology depends on runtime requirements.

---

# 59. TASK QUEUE

A dedicated task queue is required for long-running work.

Potential technology:

```text
Redis-backed Queue
```

Status:

```text
APPROVED ARCHITECTURAL DIRECTION
```

The exact queue implementation must be finalized during implementation benchmarking.

---

# 60. TASK MODEL

Every background task should have an explicit lifecycle.

Example:

```text
CREATED
 ↓
QUEUED
 ↓
RUNNING
 ↓
WAITING
 ↓
COMPLETED
```

with failure/cancellation paths:

```text
FAILED
CANCELLED
TIMED_OUT
```

---

# 61. TASK IDENTIFIER

Every task receives a globally unique task ID.

This ID should propagate through:

```text
Frontend
Backend
Agent
Tool
Worker
Logs
Events
Database
```

---

# 62. REQUEST VS TASK

A critical distinction:

```text
Request
```

is an API interaction.

```text
Task
```

is an executable unit of work.

A single request may create a task.

A task may continue after the request ends.

---

# 63. AGENT RUN

A task may contain one or more agent runs.

Example:

```text
Task
 ├── Agent Run
 │    ├── LLM
 │    ├── Tool
 │    └── Observation
 │
 └── Agent Run
      ├── Tool
      └── Result
```

---

# 64. TOOL RUN

Every privileged or meaningful tool execution should have a tool-run record.

Conceptually:

```text
tool_run_id
task_id
agent_id
tool
arguments_hash
status
started_at
completed_at
result_reference
```

Sensitive raw arguments should be governed by security/privacy policy.

---

# 65. CANCELLATION

Tasks must support cancellation.

The API:

```text
POST /api/v1/tasks/{id}/cancel
```

should signal cancellation.

The worker must enforce cancellation cooperatively or through the appropriate runtime mechanism.

---

# 66. TIMEOUTS

Tasks must have timeout policies.

Different classes may have different defaults:

```text
HTTP Request
Tool Call
Agent Step
Background Task
Browser Session
Model Request
```

---

# 67. RETRY POLICY

Retries must be classified.

Retryable:

```text
Transient Network Error
Temporary Service Unavailable
Rate Limit
```

Usually non-retryable:

```text
Permission Denied
Invalid Input
Authentication Failure
Policy Violation
```

---

# 68. IDEMPOTENCY

Operations that may be retried should support idempotency where necessary.

Especially:

```text
Payment-like Operations
External Mutations
File Operations
Task Submission
```

---

# 69. API IDEMPOTENCY

Task creation may optionally support:

```text
Idempotency-Key
```

to prevent accidental duplicate task submission.

---

# 70. AUTHENTICATION

Authentication belongs to the backend/security layer.

Potential mechanisms:

```text
Session-based Authentication
OIDC/OAuth
Local Authentication
Device Authentication
```

Exact production mechanism belongs to `14_SECURITY_STACK.md`.

---

# 71. AUTHORIZATION

Authentication answers:

```text
Who are you?
```

Authorization answers:

```text
What are you allowed to do?
```

JARVIS requires both.

---

# 72. POLICY ENFORCEMENT

High-risk operations must pass:

```text
Identity
 ↓
Authorization
 ↓
Policy
 ↓
Capability
 ↓
Tool
 ↓
Execution
```

---

# 73. FRONTEND CANNOT AUTHORIZE

The frontend may display:

```text
Approve
```

but the backend must determine whether the operation is actually authorized.

---

# 74. TOOL GATEWAY

Tools should be invoked through a controlled backend/tool gateway.

Conceptually:

```text
Agent
 ↓
Tool Request
 ↓
Tool Gateway
 ↓
Policy
 ↓
Authorization
 ↓
Tool Adapter
 ↓
Execution
```

---

# 75. DIRECT TOOL ACCESS

Agents must not receive unrestricted access to:

```text
Shell
Filesystem
Database
Network
Browser
```

---

# 76. TOOL ADAPTERS

Each tool should have a controlled adapter.

Example:

```text
BrowserTool
FilesystemTool
GitTool
CalendarTool
DatabaseTool
ShellTool
```

---

# 77. PLUGIN BOUNDARY

Plugins should connect through a backend extension interface.

```text
Plugin
 ↓
Plugin Contract
 ↓
Backend Plugin Manager
 ↓
Capability System
```

---

# 78. MCP BOUNDARY

MCP integrations should enter through a controlled integration layer.

```text
JARVIS Backend
 ↓
MCP Client
 ↓
MCP Server
 ↓
External Capability
```

---

# 79. MCP SECURITY

The backend must validate:

```text
Server Identity
Capabilities
Tool Metadata
Arguments
Permissions
Results
```

before sensitive operations are accepted.

---

# 80. EXTERNAL API INTEGRATION

External APIs should use adapters.

Example:

```text
OpenAIAdapter
GitHubAdapter
CalendarAdapter
BrowserAdapter
```

rather than spreading provider-specific code throughout the backend.

---

# 81. PROVIDER ABSTRACTION

The backend should remain capable of switching providers.

Example:

```text
LLM Provider
   ↓
Provider Adapter
   ↓
Internal Model Interface
```

---

# 82. MODEL INDEPENDENCE

Core application services should not depend directly on:

```text
specific LLM SDK
```

where an abstraction is appropriate.

---

# 83. MODEL REQUEST

Conceptually:

```text
Agent
 ↓
Model Interface
 ↓
Provider Adapter
 ↓
Model Provider
```

---

# 84. STREAMING MODEL OUTPUT

Model streaming should become backend events.

```text
Model
 ↓
Provider Adapter
 ↓
Backend Event
 ↓
WebSocket
 ↓
Frontend
```

---

# 85. MEMORY ACCESS

Backend services should access memory through a memory service.

```text
Agent
 ↓
Memory Service
 ↓
Memory Store
```

The API should not query vector databases directly.

---

# 86. VECTOR DATABASE BOUNDARY

The vector store belongs to the Memory layer.

```text
Backend
 ↓
Memory Service
 ↓
Vector Store
```

---

# 87. OBJECT STORAGE

Large artifacts should not be stored directly in PostgreSQL.

Potential object storage:

```text
Local Filesystem
S3-compatible Storage
Object Store
```

Status:

```text
DEFINED BY 06_DATABASE_AND_STORAGE_STACK.md
```

---

# 88. ARTIFACT SERVICE

The backend should expose an artifact abstraction.

Example:

```text
Artifact
 ├── ID
 ├── Type
 ├── Size
 ├── Hash
 ├── Location
 ├── Owner
 └── Metadata
```

---

# 89. FILE DOWNLOADS

Large files should use streaming or signed/authorized artifact access rather than loading the entire file into backend memory.

---

# 90. FILE UPLOADS

Uploads should support:

```text
Validation
Size Limits
Type Detection
Hashing
Security Scanning
Storage
```

---

# 91. SESSION MANAGEMENT

Backend sessions should represent:

```text
User
Client
Device
Connection
Conversation
```

as separate concepts where necessary.

---

# 92. CONVERSATION

Conversation state should not be identical to authentication session.

```text
Authentication Session
        ≠
Conversation
```

---

# 93. USER SESSION

A session may contain:

```text
User ID
Device
Authentication Context
Client
Capabilities
Created At
Last Activity
```

---

# 94. CONVERSATION STATE

Conversation may contain:

```text
Conversation ID
Messages
Context
Tasks
Agent Runs
Attachments
Metadata
```

---

# 95. TASK STATE

Task state should be persistent enough to recover from frontend disconnects and backend restarts where required.

---

# 96. STATE MACHINE

Important backend entities should use explicit state machines rather than arbitrary strings.

Example:

```text
Task:
CREATED
QUEUED
RUNNING
WAITING
COMPLETED
FAILED
CANCELLED
TIMED_OUT
```

---

# 97. DOMAIN SERVICES

Backend application logic should be organized around domain/application services.

Conceptually:

```text
TaskService
AgentService
MemoryService
ToolService
SessionService
PermissionService
ArtifactService
SystemService
```

---

# 98. SERVICE RESPONSIBILITY

Each service should have one primary responsibility.

Avoid:

```text
GodService
```

containing every backend operation.

---

# 99. APPLICATION LAYER

The application layer coordinates workflows.

Example:

```text
TaskService
 ↓
AgentService
 ↓
ToolService
 ↓
MemoryService
```

---

# 100. DOMAIN LAYER

The domain layer should contain core business rules independent of transport.

This allows:

```text
HTTP
WebSocket
CLI
Automation
```

to use the same underlying logic.

---

# 101. API LAYER

API endpoints should remain thin.

Preferred:

```text
Request
 ↓
Validate
 ↓
Authorize
 ↓
Application Service
 ↓
Response
```

---

# 102. FAT ENDPOINTS

Avoid:

```text
Endpoint
 ↓
500 lines of business logic
```

---

# 103. DEPENDENCY INJECTION

FastAPI dependency injection should be used for:

```text
Database Sessions
Authentication
Authorization
Services
Configuration
Request Context
```

but not to create an unmanageable dependency graph.

---

# 104. REQUEST CONTEXT

Every request should have a context containing relevant identifiers.

Conceptually:

```text
request_id
trace_id
user_id
session_id
client_id
```

---

# 105. CORRELATION

IDs should propagate:

```text
HTTP
 ↓
Task
 ↓
Agent
 ↓
Tool
 ↓
Worker
 ↓
External API
```

---

# 106. OBSERVABILITY

Backend observability is mandatory.

Required categories:

```text
Logs
Metrics
Traces
Events
Health
Audit
```

---

# 107. STRUCTURED LOGGING

Logs should be structured.

Conceptually:

```json
{
  "timestamp": "...",
  "level": "INFO",
  "service": "agent",
  "task_id": "...",
  "trace_id": "...",
  "event": "agent.started"
}
```

---

# 108. LOG CONTENT

Logs must avoid exposing:

```text
API Keys
Passwords
Tokens
Private Memory
Sensitive User Content
Raw Credentials
```

---

# 109. METRICS

Backend metrics should include:

```text
Request Rate
Request Latency
Error Rate
WebSocket Connections
Task Queue Depth
Task Duration
Agent Duration
Tool Duration
Model Latency
Database Latency
Redis Latency
CPU
Memory
GPU where applicable
```

---

# 110. TRACING

Distributed tracing should correlate:

```text
Frontend Request
 ↓
API
 ↓
Task
 ↓
Agent
 ↓
Model
 ↓
Tool
 ↓
External API
```

---

# 111. HEALTH ENDPOINTS

The backend should expose:

```text
/health/live
/health/ready
```

conceptually.

---

# 112. LIVENESS

Liveness means:

```text
Process is alive
```

It should not necessarily verify every dependency.

---

# 113. READINESS

Readiness means:

```text
Backend can accept work
```

and may check:

```text
Database
Redis
Required Services
Configuration
```

---

# 114. STARTUP

Startup should perform controlled initialization.

```text
Configuration
 ↓
Logging
 ↓
Database
 ↓
Redis
 ↓
Services
 ↓
Workers / Connections
 ↓
Ready
```

---

# 115. SHUTDOWN

Shutdown should gracefully handle:

```text
HTTP Requests
WebSockets
Workers
Database Connections
Redis Connections
Background Tasks
```

---

# 116. GRACEFUL SHUTDOWN

Running tasks should receive a shutdown signal and either:

```text
Complete
Checkpoint
Resume Later
Cancel Safely
```

depending on task type.

---

# 117. DATABASE CONNECTION POOL

PostgreSQL access should use controlled connection pooling.

The pool must be sized according to deployment topology rather than arbitrarily.

---

# 118. REDIS CONNECTION MANAGEMENT

Redis clients should also use managed connections and explicit timeouts.

---

# 119. TIMEOUT POLICY

External calls should have timeouts.

No indefinite:

```text
await external_api()
```

operations.

---

# 120. NETWORK RESILIENCE

External service calls should support appropriate:

```text
Timeout
Retry
Backoff
Circuit Breaker
Fallback
```

where justified.

---

# 121. CIRCUIT BREAKER

Circuit-breaker patterns may be introduced for unstable external dependencies.

Status:

```text
CONDITIONAL / IMPLEMENTATION-LEVEL
```

---

# 122. RATE LIMITING

Backend rate limiting should protect:

```text
API
Authentication
Expensive Operations
External APIs
Tool Execution
```

---

# 123. RATE LIMIT SCOPE

Rate limits may apply per:

```text
User
Client
IP
API Key
Tool
Endpoint
```

depending on security architecture.

---

# 124. REQUEST SIZE LIMITS

Backend must limit:

```text
JSON Payload
File Upload
WebSocket Message
Artifact Upload
```

appropriately.

---

# 125. INPUT SANITIZATION

Validation is not the same as sanitization.

External content must remain untrusted after validation.

---

# 126. CONTENT TRUST MODEL

The backend must distinguish:

```text
System Instruction
User Instruction
External Content
Tool Result
MCP Result
Browser Content
Uploaded Document
Model Output
```

---

# 127. PROMPT INJECTION

The backend must not treat external tool/browser/document content as trusted instructions.

---

# 128. TOOL OUTPUT

Tool results should have typed structures and provenance.

Conceptually:

```yaml
tool_result:
  tool_id: ...
  source: ...
  trust_level: ...
  content: ...
```

---

# 129. PROVENANCE

Important information should retain source metadata where practical.

This is especially important for:

```text
Research
Browser
MCP
Documents
Memory
External APIs
```

---

# 130. AUDIT LOGGING

Security-sensitive actions should produce audit records.

Examples:

```text
Permission Granted
Permission Denied
Tool Executed
File Deleted
Credential Accessed
Plugin Installed
MCP Server Added
Configuration Changed
```

---

# 131. AUDIT VS APPLICATION LOG

Audit records are not simply debug logs.

They should have stronger:

```text
Integrity
Retention
Access Control
```

requirements.

---

# 132. ADMINISTRATION

Backend should provide controlled administrative APIs.

Examples:

```text
System Status
Configuration
Plugin Management
MCP Management
Task Management
Diagnostics
```

---

# 133. ADMIN AUTHORIZATION

Administrative endpoints require stronger authorization.

---

# 134. BACKEND CONFIGURATION

Configuration should be separated from code.

Sources may include:

```text
Environment Variables
Configuration Files
Secret Store
Database Configuration
```

---

# 135. CONFIGURATION PRECEDENCE

Configuration precedence must be deterministic.

Conceptually:

```text
Defaults
 ↓
Config File
 ↓
Environment
 ↓
Runtime Override
```

Exact precedence belongs to bootstrap/configuration architecture.

---

# 136. SECRET CONFIGURATION

Secrets must be loaded from approved secret mechanisms.

Never hard-code:

```text
API_KEY = "..."
```

---

# 137. ENVIRONMENT SEPARATION

The backend must distinguish:

```text
Development
Testing
Staging
Production
```

---

# 138. PRODUCTION DIFFERENCES

Production configuration should not be a manually edited copy of development configuration.

---

# 139. LOCAL DEVELOPMENT

The backend should be easy to start locally.

Conceptually:

```text
PostgreSQL
Redis
Backend
Frontend
```

with controlled development configuration.

---

# 140. DOCKER

Docker may be used for infrastructure and deployment.

The exact Docker architecture belongs to:

```text
15_DEVOPS_AND_DEPLOYMENT_STACK.md
```

---

# 141. CONTAINER PRINCIPLE

The backend should be container-compatible even if local-first deployment also supports native execution.

---

# 142. SCALABILITY

The backend should be capable of scaling horizontally where appropriate.

```text
Frontend
 ↓
Load Balancer
 ↓
API Instance 1
API Instance 2
API Instance 3
```

---

# 143. STATELESS API

API instances should remain as stateless as practical.

Persistent state belongs to:

```text
PostgreSQL
Redis
Object Storage
Task System
```

---

# 144. WEBSOCKET SCALING

When multiple backend instances are used, realtime connections require shared event/coordination infrastructure.

Potentially:

```text
WebSocket Instance
 ↓
Redis / Event Layer
```

---

# 145. SINGLE-MACHINE DEPLOYMENT

JARVIS must also support a single-machine deployment.

```text
One Computer
 ├── Backend
 ├── PostgreSQL
 ├── Redis
 ├── Models
 └── Frontend
```

This is important for personal/local deployments.

---

# 146. DISTRIBUTED DEPLOYMENT

Future architecture may support:

```text
Frontend
 ↓
API Cluster
 ↓
Worker Cluster
 ↓
Database
 ↓
Redis
 ↓
Model Infrastructure
```

---

# 147. LOCAL-FIRST

The architecture should not require cloud infrastructure for the basic personal JARVIS deployment.

---

# 148. CLOUD-READY

At the same time, backend architecture must not prevent cloud deployment.

---

# 149. BACKEND MODULARITY

The backend should support modular services without immediately becoming a microservices system.

---

# 150. MODULAR MONOLITH

The initial implementation should prefer:

> **Modular Monolith**

over premature microservices.

---

# 151. WHY MODULAR MONOLITH

JARVIS v1 is a complex system, but splitting every component into a network service would introduce:

```text
Network Complexity
Deployment Complexity
Debugging Complexity
Latency
Authentication Overhead
Distributed State Problems
```

too early.

---

# 152. MODULAR MONOLITH STRUCTURE

Conceptually:

```text
Backend
│
├── API
├── Auth
├── Tasks
├── Agents
├── Memory
├── Tools
├── Plugins
├── MCP
├── Voice
├── Vision
├── Browser
├── Artifacts
├── Notifications
└── System
```

inside one controlled application boundary.

---

# 153. SERVICE EXTRACTION

A module may later become a separate service when evidence demonstrates:

```text
Scaling Need
Resource Isolation
Security Isolation
Deployment Independence
Hardware Requirement
Failure Isolation
```

---

# 154. MICROSERVICE RULE

Microservices are an architectural outcome, not a starting requirement.

---

# 155. GPU SERVICES

AI workloads requiring GPUs may eventually run outside the API process.

Example:

```text
Backend
 ↓
Inference Service
 ↓
GPU
```

---

# 156. MODEL INFERENCE

The API process should not necessarily host heavy model inference directly.

This depends on model runtime architecture.

---

# 157. VOICE BACKEND

Voice processing may become:

```text
Backend
 ↓
Voice Service
 ↓
STT / TTS
```

while maintaining a stable internal interface.

---

# 158. VISION BACKEND

Vision may become:

```text
Backend
 ↓
Vision Service
 ↓
Model Runtime
```

---

# 159. BROWSER BACKEND

Browser automation should be isolated behind:

```text
Browser Service
```

or a controlled tool boundary.

---

# 160. AGENT BACKEND

Agent execution belongs to the Agent Orchestration layer.

```text
Backend
 ↓
Agent Runtime
 ↓
Planner
 ↓
Agent
 ↓
Tools
```

---

# 161. API DOES NOT RUN AGENTS DIRECTLY

A request endpoint should not become:

```text
HTTP Request
 ↓
Run 10-minute agent workflow
 ↓
HTTP response
```

Instead:

```text
HTTP Request
 ↓
Create Task
 ↓
Return Task ID
 ↓
Worker executes
 ↓
Events
```

---

# 162. SYNCHRONOUS REQUESTS

Short operations may remain synchronous.

Examples:

```text
Get Settings
Get Task
Health Check
Small CRUD
Permission Query
```

---

# 163. ASYNCHRONOUS REQUESTS

Long operations should become tasks.

Examples:

```text
Research
Coding
Video Analysis
Browser Workflow
Large Model Inference
```

---

# 164. TASK API

Conceptual API:

```text
POST /api/v1/tasks
GET  /api/v1/tasks/{id}
POST /api/v1/tasks/{id}/cancel
GET  /api/v1/tasks/{id}/events
```

---

# 165. AGENT API

Conceptual:

```text
POST /api/v1/agents/runs
GET  /api/v1/agents/runs/{id}
POST /api/v1/agents/runs/{id}/cancel
```

---

# 166. MEMORY API

Conceptual:

```text
GET    /api/v1/memory
POST   /api/v1/memory
DELETE /api/v1/memory/{id}
```

Actual endpoints depend on memory architecture.

---

# 167. TOOL API

Tool execution should generally not be an unrestricted public API.

It should be mediated through backend authorization and agent/tool services.

---

# 168. SYSTEM API

Potential:

```text
GET /api/v1/system/status
GET /api/v1/system/capabilities
GET /api/v1/system/health
```

---

# 169. CAPABILITY API

The frontend should be able to discover available capabilities.

Conceptually:

```yaml
capabilities:
  voice: true
  vision: true
  browser: true
  memory: true
  filesystem: false
  shell: false
```

---

# 170. CAPABILITY ≠ PERMISSION

A capability being available does not mean the user is authorized to use it.

```text
Capability
    ≠
Permission
```

---

# 171. USER PERMISSION

The backend evaluates:

```text
User
+
Capability
+
Requested Action
+
Policy
=
Allow / Deny / Approval Required
```

---

# 172. APPROVAL FLOW

Example:

```text
Agent
 ↓
Tool Request
 ↓
Policy Evaluation
 ↓
Approval Required
 ↓
Frontend
 ↓
User Approval
 ↓
Backend
 ↓
Tool Execution
```

---

# 173. APPROVAL MUST BE SERVER-SIDE

The frontend approval button is not itself authorization.

The backend must validate the approval context.

---

# 174. EXPIRATION

Approvals should be able to expire.

---

# 175. APPROVAL SCOPE

Approval should specify:

```text
Tool
Arguments / Scope
Duration
User
Task
```

where applicable.

---

# 176. BACKEND EVENT BUS

An internal event bus may be used for:

```text
Task Events
Agent Events
Tool Events
System Events
Notifications
```

---

# 177. EVENT BUS VS API

The API handles:

```text
Request/Response
```

The event bus handles:

```text
Asynchronous Event
```

These are separate concepts.

---

# 178. REDIS EVENT BUS

Redis Streams may serve as an implementation for selected internal event workloads.

However, not every internal event requires persistence.

---

# 179. EVENT RETENTION

Event retention should be defined per category.

Example:

```text
Debug Event
→ Short

Audit Event
→ Long

Task Event
→ Until Task Retention Policy

UI Activity
→ Very Short
```

---

# 180. BACKEND CACHE

Caching should be introduced only after identifying a real performance requirement.

---

# 181. CACHE INVALIDATION

Each cache must have:

```text
Owner
TTL
Invalidation Strategy
Fallback
```

---

# 182. DATABASE AS SOURCE OF TRUTH

Persistent state should have an explicit source of truth.

Example:

```text
User
→ PostgreSQL

Task
→ PostgreSQL

Temporary Session
→ Redis

Event Stream
→ Redis Streams

Large Artifact
→ Object Storage
```

---

# 183. BACKEND TESTING

Testing must cover:

```text
Unit
Integration
API
Contract
Database
Worker
Agent
Tool
Security
Performance
End-to-End
```

---

# 184. UNIT TESTS

Test:

```text
Domain Logic
Validation
Services
State Machines
Policy Rules
Utility Functions
```

---

# 185. API TESTS

Test:

```text
HTTP Status
Schemas
Authentication
Authorization
Validation
Errors
Streaming
```

---

# 186. WEBSOCKET TESTS

Test:

```text
Connect
Authenticate
Send
Receive
Disconnect
Reconnect
Invalid Event
Unauthorized Event
```

---

# 187. DATABASE TESTS

Test:

```text
Migrations
Transactions
Constraints
Queries
Concurrency
Rollback
```

---

# 188. WORKER TESTS

Test:

```text
Queue
Execution
Retry
Timeout
Cancellation
Failure
Recovery
```

---

# 189. TASK RECOVERY TESTS

Simulate:

```text
Worker Crash
Backend Restart
Redis Restart
Database Restart
Frontend Disconnect
Network Failure
```

---

# 190. AGENT TESTS

Test:

```text
Planning
Tool Selection
Permission
Tool Failure
Retry
Memory Retrieval
Completion
```

---

# 191. CONTRACT TESTS

Frontend/backend contracts must be tested independently.

---

# 192. SECURITY TESTS

Test:

```text
Unauthorized Access
Privilege Escalation
Injection
Invalid Tokens
Expired Sessions
Tool Abuse
Path Traversal
SSRF
File Upload
```

---

# 193. PERFORMANCE TESTS

Measure:

```text
API Latency
WebSocket Latency
Task Submission
Database Latency
Queue Latency
Concurrent Connections
```

---

# 194. LOAD TESTS

The backend should eventually be tested under:

```text
100+
1000+
```

connections/tasks where relevant.

Exact targets depend on deployment scenario.

---

# 195. BACKEND DOCUMENTATION

Every backend service should document:

```text
Purpose
Inputs
Outputs
Dependencies
Failure Modes
Security
Persistence
Events
```

---

# 196. SERVICE CONTRACT

Each service should have an explicit interface.

Conceptually:

```text
Service
 ├── Interface
 ├── Implementation
 ├── Models
 ├── Errors
 └── Tests
```

---

# 197. ERROR MODEL

Backend errors should be standardized.

Conceptually:

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "...",
    "request_id": "...",
    "details": {}
  }
}
```

---

# 198. ERROR CODES

Errors should have stable machine-readable codes.

---

# 199. INTERNAL EXCEPTIONS

Internal Python exceptions must not automatically leak stack traces to clients.

---

# 200. DEBUG MODE

Debug information must be disabled in production.

---

# 201. API DOCUMENTATION

OpenAPI should be generated and version-controlled where practical.

---

# 202. API DOC SECURITY

Interactive API documentation may be:

```text
Development
Enabled

Production
Restricted / Disabled
```

depending on security policy.

---

# 203. BACKEND PACKAGE STRUCTURE

Conceptual target:

```text
backend/
│
├── api/
│   ├── routes/
│   ├── schemas/
│   └── dependencies/
│
├── application/
│   ├── services/
│   ├── commands/
│   └── queries/
│
├── domain/
│   ├── models/
│   ├── events/
│   ├── policies/
│   └── state/
│
├── infrastructure/
│   ├── database/
│   ├── redis/
│   ├── storage/
│   ├── external/
│   └── messaging/
│
├── agents/
├── tools/
├── memory/
├── plugins/
├── mcp/
├── workers/
├── security/
├── observability/
├── configuration/
└── tests/
```

This is architectural guidance, not yet a frozen repository structure.

---

# 204. API MODULE

The API module should contain:

```text
Routes
Schemas
Dependencies
Middleware
Exception Handlers
```

---

# 205. APPLICATION MODULE

Application services coordinate use cases.

---

# 206. DOMAIN MODULE

Domain logic must remain transport-independent.

---

# 207. INFRASTRUCTURE MODULE

Infrastructure contains:

```text
Database
Redis
Storage
External APIs
Messaging
```

---

# 208. DEPENDENCY DIRECTION

Preferred dependency direction:

```text
API
 ↓
Application
 ↓
Domain

Infrastructure
 ↓
implements required interfaces
```

The domain should not depend on FastAPI.

---

# 209. DOMAIN INDEPENDENCE

This allows future alternative interfaces:

```text
HTTP
CLI
Desktop
Automation
Tests
```

to use the same domain/application services.

---

# 210. BACKEND / FRONTEND CONTRACT

The relationship is:

```text
React
 ↓
API Client
 ↓
OpenAPI Contract
 ↓
FastAPI
 ↓
Application Services
```

---

# 211. FRONTEND EVENT CONTRACT

Realtime:

```text
React
 ↓
WebSocket Client
 ↓
Typed Event Contract
 ↓
Backend Event Gateway
 ↓
Application Events
```

---

# 212. FRONTEND STATE SYNCHRONIZATION

Backend remains authoritative.

Frontend maintains:

```text
Cache
Presentation State
Temporary State
```

---

# 213. BACKEND STATE SYNCHRONIZATION

When a state changes:

```text
Database
 ↓
Domain Event
 ↓
Event Dispatcher
 ↓
WebSocket
 ↓
Frontend
```

---

# 214. EVENTUAL CONSISTENCY

Some frontend views may be eventually consistent.

The UI should communicate meaningful transitional states.

---

# 215. BACKEND VERSIONING

Backend application version should be identifiable.

Example:

```yaml
backend:
  version: ...
  commit: ...
  build: ...
```

---

# 216. API VERSION VS APPLICATION VERSION

These are separate:

```text
Backend Version
≠
API Version
```

---

# 217. BACKWARD COMPATIBILITY

API changes should maintain backward compatibility where possible.

Breaking changes require:

```text
New API Version
Migration
Deprecation
```

---

# 218. DEPRECATION

Deprecated endpoints should provide:

```text
Documentation
Warning
Removal Timeline
```

where practical.

---

# 219. DATABASE COMPATIBILITY

Application releases should be compatible with the database migration strategy.

---

# 220. ZERO-DOWNTIME MIGRATIONS

Where distributed deployment requires it, migrations should follow expand/contract patterns.

---

# 221. BACKEND STARTUP VALIDATION

Startup should validate:

```text
Configuration
Database
Redis
Required Environment
Required Models
External Dependencies
Security Configuration
```

---

# 222. STARTUP FAILURE

If required dependencies are unavailable:

```text
READY = FALSE
```

rather than silently starting in a corrupted state.

---

# 223. DEGRADED MODE

Optional capabilities may be unavailable while core backend remains operational.

Example:

```text
Backend
● Online

Voice
○ Unavailable

Vision
○ Unavailable
```

---

# 224. CAPABILITY REGISTRY

Backend should maintain a capability registry.

Potential:

```text
voice
vision
browser
memory
filesystem
shell
mcp
plugins
```

---

# 225. CAPABILITY HEALTH

Each capability may have:

```text
Available
Unavailable
Degraded
Disabled
```

---

# 226. FEATURE FLAGS

Feature flags may control:

```text
Experimental Agent
Experimental UI
New Tool
New Provider
```

but not core security boundaries.

---

# 227. EXPERIMENTAL COMPONENTS

Experimental backend components must be isolated.

---

# 228. PLUGIN LIFECYCLE

Plugins should have:

```text
Installed
Enabled
Disabled
Updated
Deprecated
Removed
```

states.

---

# 229. MCP SERVER LIFECYCLE

MCP integrations should similarly support:

```text
Registered
Connected
Available
Degraded
Disabled
Removed
```

---

# 230. EXTERNAL SERVICE HEALTH

External providers should not be assumed available.

Backend must handle:

```text
Timeout
Rate Limit
Outage
Invalid Response
Schema Change
Authentication Failure
```

---

# 231. PROVIDER FALLBACK

Provider fallback may be supported.

Example:

```text
Primary Model
 ↓
Failure
 ↓
Approved Fallback
```

but fallback policy must be explicit.

---

# 232. FALLBACK SAFETY

The backend must not silently switch to a lower-security or incompatible provider.

---

# 233. DATA PRIVACY

Backend must respect:

```text
Memory Privacy
Conversation Privacy
Artifact Privacy
Telemetry Privacy
Audit Access
```

---

# 234. DATA ACCESS CONTROL

Services should access only the data they require.

---

# 235. LEAST PRIVILEGE

The backend process should not automatically have:

```text
Full Filesystem
Root
All Network
All Credentials
```

access.

---

# 236. OS ACCESS

Privileged OS operations should occur through explicit tools/capabilities.

---

# 237. SHELL ACCESS

Shell execution is high-risk.

It must be mediated by:

```text
Policy
Permission
Sandbox
Audit
```

as defined by the Security Stack.

---

# 238. DATABASE ACCESS FROM AGENTS

Agents must not receive unrestricted SQL access.

---

# 239. BROWSER ACCESS

Agents must use the Browser Automation boundary.

---

# 240. FILESYSTEM ACCESS

Filesystem access must be scoped.

---

# 241. NETWORK ACCESS

External network access should be policy-controlled where security requires it.

---

# 242. SECRET ACCESS

Secrets should be exposed only to components that explicitly require them.

---

# 243. BACKEND SUPPLY CHAIN

Python dependencies must be evaluated for:

```text
Security
License
Maintenance
Compatibility
Version Stability
```

---

# 244. DEPENDENCY PINNING

All production dependencies must eventually be version locked.

---

# 245. VERSION LOCK INTEGRATION

The backend Version Lock must include at minimum:

```text
Python
FastAPI
Starlette
Uvicorn
Pydantic
SQLAlchemy
PostgreSQL
Redis
Migration Tool
HTTP Client
Async Runtime
Testing Stack
Observability Stack
Task Queue
```

Exact versions are intentionally deferred.

---

# 246. MANIFEST INTEGRATION

Manifest should conceptually contain:

```yaml
backend:
  language: python
  framework: fastapi
  validation: pydantic
  database:
    primary: postgresql
    orm: sqlalchemy
  cache:
    primary: redis
  realtime:
    websocket: true
  api:
    style: rest
    version: v1
  execution:
    workers: true
```

---

# 247. BOOTSTRAP INTEGRATION

Bootstrap must eventually:

```text
Install Python
Install Backend Dependencies
Validate Python Version
Provision PostgreSQL
Provision Redis
Run Migrations
Validate Configuration
Start Backend
Run Health Checks
Validate API
Validate WebSocket
```

---

# 248. COMPLIANCE CHECKER

Compliance Checker should verify:

```text
FastAPI Version
Python Version
Pydantic Version
SQLAlchemy Version
Approved Dependencies
Database Configuration
Redis Configuration
API Version
Forbidden Direct Dependencies
Secret Exposure
Layer Boundaries
Migration State
Health Endpoints
OpenAPI Contract
```

---

# 249. SYSTEM VERIFICATION

System Verification should test:

```text
Backend Starts
Database Connects
Redis Connects
API Responds
WebSocket Connects
Authentication Works
Task Creation Works
Worker Executes
Event Delivered
Frontend Can Connect
```

---

# 250. DEPLOYMENT MODES

The backend must support:

```text
Development
Testing
Staging
Production
Local Personal Deployment
Distributed Deployment
```

---

# 251. DEVELOPMENT MODE

Development may use:

```text
Local PostgreSQL
Local Redis
Hot Reload
Debug Logging
Development API Docs
```

---

# 252. TESTING MODE

Testing should use isolated resources.

No test suite should accidentally modify production data.

---

# 253. STAGING

Staging should approximate production architecture.

---

# 254. PRODUCTION

Production should use:

```text
Secure Configuration
TLS
Authentication
Authorization
Restricted Docs
Structured Logs
Metrics
Tracing
Backups
Migrations
Health Checks
```

---

# 255. BACKUP

Persistent data requiring recovery must be backed up.

At minimum:

```text
PostgreSQL
Important Artifacts
Critical Configuration
```

---

# 256. DISASTER RECOVERY

Recovery procedures should define:

```text
Database Restore
Configuration Restore
Artifact Restore
Redis Rebuild
Backend Redeploy
```

---

# 257. REDIS RECOVERY

Redis should not be the only source of critical state.

---

# 258. DATABASE FAILURE

If PostgreSQL becomes unavailable:

```text
READY = FALSE
```

for services requiring persistence.

---

# 259. REDIS FAILURE

If Redis is unavailable, capabilities that depend on it may become degraded.

The architecture should distinguish:

```text
Critical Dependency
Optional Dependency
```

---

# 260. BACKEND FAILURE

Frontend should display:

```text
Backend Offline
```

rather than silently retrying indefinitely.

---

# 261. WORKER FAILURE

Worker failures should be observable and tasks should transition into controlled states.

---

# 262. TASK RECOVERY

Recoverable tasks may return to:

```text
QUEUED
```

after worker failure.

Non-recoverable tasks should become:

```text
FAILED
```

with diagnostics.

---

# 263. DEAD LETTER

Repeatedly failing tasks may enter a dead-letter mechanism.

Status:

```text
FUTURE / CONDITIONAL
```

---

# 264. BACKEND SECURITY BOUNDARY

The final security chain is:

```text
Client
 ↓
Authentication
 ↓
Authorization
 ↓
Policy
 ↓
Capability
 ↓
Application Service
 ↓
Tool / Agent
 ↓
Execution
```

---

# 265. NO TRUST BY DEFAULT

No external input is trusted automatically.

This includes:

```text
Frontend
Browser
MCP
Plugin
File
Model
External API
```

---

# 266. MODEL OUTPUT IS UNTRUSTED

LLM output must be treated as data/instructions requiring policy enforcement, not as a trusted authority.

---

# 267. TOOL ARGUMENT VALIDATION

Tool arguments must be validated before execution.

---

# 268. TOOL RESULT VALIDATION

Tool results should also be validated before entering sensitive workflows.

---

# 269. AGENT BOUNDARY

Agent output does not automatically bypass security policy.

---

# 270. BACKEND + JARVIS CORE

The relationship:

```text
Backend
 ↓
Core Interface
 ↓
JARVIS Core
```

should be explicit.

The backend should not reach into arbitrary Core internals.

---

# 271. CORE INTERFACE

Core should expose controlled operations such as:

```text
Create Run
Resume Run
Cancel Run
Get Run State
Submit Observation
```

rather than exposing internal implementation details.

---

# 272. BACKEND + MEMORY

Backend uses:

```text
Memory Service Interface
```

rather than direct database calls from routes.

---

# 273. BACKEND + AGENTS

Backend uses:

```text
Agent Service Interface
```

rather than direct manipulation of agent internals.

---

# 274. BACKEND + TOOLS

Backend uses:

```text
Tool Gateway
```

rather than unrestricted Python function execution.

---

# 275. BACKEND + PLUGINS

Backend uses:

```text
Plugin Manager
```

rather than dynamic arbitrary module imports.

---

# 276. DYNAMIC CODE EXECUTION

Arbitrary:

```python
exec(...)
eval(...)
```

is prohibited in normal backend logic.

Any sandboxed execution must be explicitly isolated.

---

# 277. SERIALIZATION SECURITY

Unsafe deserialization mechanisms must be avoided.

---

# 278. SSRF

External URL access must be controlled to prevent SSRF.

---

# 279. PATH TRAVERSAL

Filesystem tools must normalize and validate paths.

---

# 280. COMMAND INJECTION

Shell commands must not be constructed directly from untrusted strings.

---

# 281. SQL INJECTION

Use parameterized queries/SQLAlchemy APIs.

---

# 282. FILE UPLOAD SECURITY

Uploads must be treated as untrusted.

---

# 283. BROWSER CONTENT SECURITY

Browser-derived content is external/untrusted content.

---

# 284. MCP CONTENT SECURITY

MCP tool results are untrusted external data unless explicitly trusted by policy.

---

# 285. BACKEND API RATE LIMITING

Authentication and expensive AI endpoints require stronger rate limits.

---

# 286. RESOURCE LIMITS

Backend must enforce limits on:

```text
Task Count
Concurrent Agents
File Size
Request Size
Token Budget
Tool Runtime
Browser Sessions
Model Calls
```

---

# 287. TOKEN BUDGET

Agent/model requests should have explicit budgets where appropriate.

---

# 288. COST CONTROL

Cloud model usage should be observable and optionally bounded.

---

# 289. MODEL QUOTA

Backend may enforce:

```text
Per User
Per Task
Per Agent
Per Provider
```

limits.

---

# 290. BACKEND ADMIN UI

The frontend may provide administrative views.

The backend remains responsible for authorization.

---

# 291. CLI

A future CLI may connect to the same backend application services.

This reinforces the transport-independent architecture.

---

# 292. AUTOMATION

Scheduled automation should invoke backend services rather than bypassing them.

---

# 293. SCHEDULER

Scheduling may eventually use:

```text
Scheduler
 ↓
Task Creation
 ↓
Worker
```

rather than directly executing arbitrary functions.

---

# 294. WEBHOOKS

Webhook integrations may be supported later.

All webhook input must be validated and authenticated where applicable.

---

# 295. EXTERNAL EVENT INGESTION

External events should enter through an integration boundary.

```text
External Event
 ↓
Adapter
 ↓
Validation
 ↓
Application Event
```

---

# 296. EVENT SOURCING

Full event sourcing is not required for v1.

Status:

```text
NOT REQUIRED
```

Selected events may still be persisted for audit/recovery.

---

# 297. CQRS

Full CQRS is not required for v1.

However, conceptual separation between:

```text
Commands
Queries
```

is encouraged.

---

# 298. MICROSERVICES

Full microservice decomposition is not required for v1.

---

# 299. GRAPHQL

GraphQL status:

```text
CONDITIONALLY APPROVED
```

It is not the default API protocol.

REST + OpenAPI remains the primary interface.

---

# 300. GRPC

gRPC status:

```text
CONDITIONALLY APPROVED
```

It may be used for internal high-performance service-to-service communication if future decomposition justifies it.

---

# 301. WHY REST DEFAULT

JARVIS needs:

```text
Browser Compatibility
Frontend Simplicity
Human-readable API
OpenAPI
Easy Debugging
```

REST provides these effectively.

---

# 302. INTERNAL PROTOCOL FLEXIBILITY

The internal architecture should not prohibit:

```text
REST
WebSocket
gRPC
Message Queue
```

but each protocol must have a defined purpose.

---

# 303. PROTOCOL MATRIX

| Protocol | Primary Role | Status |
|---|---|---|
| REST | Public application API | APPROVED |
| OpenAPI | HTTP contract | APPROVED |
| WebSocket | Realtime bidirectional events | APPROVED |
| SSE | Optional server streaming | OPTIONAL |
| gRPC | Future internal service communication | CONDITIONAL |
| GraphQL | Specialized future API | CONDITIONAL |
| Redis Streams | Internal event/task workloads | APPROVED |
| Raw TCP | Not required | REJECTED BY DEFAULT |

---

# 304. BACKEND TECHNOLOGY MATRIX

| Component | Technology | Status | Role |
|---|---|---|---|
| Language | Python | APPROVED | Backend/application |
| Web Framework | FastAPI | APPROVED | HTTP/API |
| ASGI | Starlette | APPROVED / UNDERLYING | Async web foundation |
| ASGI Server | Uvicorn | APPROVED CANDIDATE | Runtime server |
| Validation | Pydantic v2 | APPROVED | Schemas/validation |
| API | REST + OpenAPI | APPROVED | External contract |
| Realtime | WebSocket | APPROVED | Bidirectional events |
| Streaming | SSE | OPTIONAL | Server-to-client streaming |
| Primary DB | PostgreSQL | APPROVED | Durable relational data |
| ORM | SQLAlchemy 2.x | APPROVED | DB access |
| Migration | Alembic | APPROVED CANDIDATE | Schema migration |
| Cache | Redis | APPROVED | Cache/coordination |
| Event Stream | Redis Streams | APPROVED | Selected event workloads |
| Workers | Dedicated Worker Runtime | REQUIRED | Long-running tasks |
| Queue | Redis-backed Queue | APPROVED DIRECTION | Task execution |
| API Docs | OpenAPI | APPROVED | Contract/documentation |
| Architecture | Modular Monolith | APPROVED | V1 backend topology |
| Microservices | Future | CONDITIONAL | Scale/isolation |
| GraphQL | Future | CONDITIONAL | Specialized APIs |
| gRPC | Future | CONDITIONAL | Internal service communication |

---

# 305. PRIMARY V1 STACK

The primary backend stack is:

```text
Python
+
FastAPI
+
Starlette / ASGI
+
Pydantic v2
+
SQLAlchemy 2.x
+
PostgreSQL
+
Redis
+
WebSocket
+
Dedicated Workers
```

---

# 306. ARCHITECTURAL MODEL

```text
========================================================
JARVIS BACKEND v1
========================================================

LANGUAGE:
    Python

API:
    FastAPI

ASGI:
    Starlette

SERVER:
    Uvicorn

VALIDATION:
    Pydantic v2

API STYLE:
    REST + OpenAPI

REALTIME:
    WebSocket

PRIMARY DATABASE:
    PostgreSQL

ORM:
    SQLAlchemy 2.x

MIGRATIONS:
    Alembic

CACHE / COORDINATION:
    Redis

EVENT STREAM:
    Redis Streams
    where justified

EXECUTION:
    Dedicated Workers

ARCHITECTURE:
    Modular Monolith

========================================================
```

---

# 307. WHY MODULAR MONOLITH

The first JARVIS backend must optimize for:

```text
Correctness
Maintainability
Debuggability
Security
Development Speed
Low Latency
Clear Boundaries
```

rather than distributed complexity.

---

# 308. FUTURE EXTRACTION

When a module requires independent scaling:

```text
Module
 ↓
Service Boundary
 ↓
Independent Deployment
```

can be introduced.

---

# 309. EXAMPLE FUTURE ARCHITECTURE

```text
                 API Gateway
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
      Core          Voice         Vision
      Service       Service       Service
        │             │             │
        └─────────────┼─────────────┘
                      ▼
                  Infrastructure
```

This is future architecture, not v1.

---

# 310. DEFINITION OF DONE

Backend stack implementation is complete when:

```text
[ ] Python runtime configured
[ ] FastAPI configured
[ ] ASGI server configured
[ ] Pydantic configured
[ ] REST API implemented
[ ] OpenAPI generated
[ ] WebSocket implemented
[ ] Event schema implemented
[ ] Authentication implemented
[ ] Authorization implemented
[ ] Policy layer implemented
[ ] PostgreSQL integrated
[ ] SQLAlchemy integrated
[ ] Migrations integrated
[ ] Redis integrated
[ ] Task queue integrated
[ ] Worker runtime integrated
[ ] Task state machine implemented
[ ] Cancellation implemented
[ ] Retry policy implemented
[ ] Timeout policy implemented
[ ] Agent service integrated
[ ] Memory service integrated
[ ] Tool gateway integrated
[ ] Plugin boundary integrated
[ ] MCP boundary integrated
[ ] Artifact service integrated
[ ] Health endpoints implemented
[ ] Structured logging implemented
[ ] Metrics implemented
[ ] Tracing implemented
[ ] Audit logging implemented
[ ] API contract tests implemented
[ ] WebSocket tests implemented
[ ] Worker tests implemented
[ ] Security tests implemented
[ ] Recovery tests implemented
[ ] Version Lock integrated
[ ] Manifest integrated
[ ] Bootstrap integrated
[ ] Compliance Checker integrated
[ ] System Verification integrated
```

---

# 311. FINAL ARCHITECTURAL RULES

### Rule 1

**Python is the primary backend/application language.**

### Rule 2

**FastAPI is the primary HTTP/API framework.**

### Rule 3

**Starlette/ASGI is the underlying asynchronous web foundation.**

### Rule 4

**Pydantic v2 is the primary schema and validation system.**

### Rule 5

**REST + OpenAPI is the primary external API contract.**

### Rule 6

**WebSocket is the preferred realtime bidirectional transport.**

### Rule 7

**SSE is optional for server-only streaming.**

### Rule 8

**PostgreSQL is the authoritative relational database.**

### Rule 9

**SQLAlchemy 2.x is the primary database abstraction.**

### Rule 10

**Redis is for cache, coordination and selected event workloads, not the primary durable database.**

### Rule 11

**Long-running work must not block the primary API process.**

### Rule 12

**Long-running work must execute through dedicated workers.**

### Rule 13

**Requests and tasks are separate concepts.**

### Rule 14

**Tasks must have explicit lifecycle states.**

### Rule 15

**Task IDs must propagate across the execution chain.**

### Rule 16

**The frontend is not an authorization authority.**

### Rule 17

**Authorization must be enforced by the backend/security layer.**

### Rule 18

**Agents must not receive unrestricted system access.**

### Rule 19

**Tools must pass through controlled capability boundaries.**

### Rule 20

**Plugins must use explicit extension contracts.**

### Rule 21

**MCP integrations must pass through controlled integration boundaries.**

### Rule 22

**External content is untrusted.**

### Rule 23

**LLM output is untrusted until validated and policy-checked.**

### Rule 24

**Browser, MCP and uploaded content must not automatically become trusted instructions.**

### Rule 25

**The API layer must remain thin.**

### Rule 26

**Business logic belongs in application/domain services.**

### Rule 27

**The domain layer must not depend on FastAPI.**

### Rule 28

**Database access must remain behind the persistence/infrastructure boundary.**

### Rule 29

**The backend must remain modular.**

### Rule 30

**Modular monolith is the default v1 deployment model.**

### Rule 31

**Microservices are introduced only when justified by evidence.**

### Rule 32

**Secrets must never be hard-coded or exposed through frontend APIs.**

### Rule 33

**All external calls require explicit timeout behavior.**

### Rule 34

**Retry policies must distinguish transient failures from permanent failures.**

### Rule 35

**Important operations should be idempotent where required.**

### Rule 36

**Health and readiness are different concepts.**

### Rule 37

**Backend state must remain recoverable where required.**

### Rule 38

**Frontend disconnect must not automatically destroy backend tasks.**

### Rule 39

**Backend events must be typed and versioned.**

### Rule 40

**Observability is mandatory.**

### Rule 41

**Audit logging is separate from normal debug logging.**

### Rule 42

**Database migrations must be version-controlled.**

### Rule 43

**Production dependencies must eventually be version-locked.**

### Rule 44

**Backend configuration must be deterministic and environment-aware.**

### Rule 45

**The backend must support both local-first and future distributed deployment.**

### Rule 46

**The backend must remain model-provider agnostic.**

### Rule 47

**Provider-specific logic belongs in adapters.**

### Rule 48

**The backend must not directly expose model-provider SDKs to frontend clients.**

### Rule 49

**Backend architecture must support voice, vision, browser, memory, plugins and MCP without collapsing their boundaries.**

### Rule 50

**Version Lock is the authority for exact dependency versions.**

### Rule 51

**Manifest is the authority for operational backend configuration.**

### Rule 52

**Bootstrap is responsible for provisioning and validating the backend environment.**

### Rule 53

**Compliance Checker must enforce backend architectural boundaries.**

### Rule 54

**System Verification must validate actual backend readiness, not merely successful installation.**

---

# 312. BACKEND → FRONTEND CONTRACT

The final relationship with `10_FRONTEND_STACK.md` is:

```text
                         USER
                           │
                           ▼
                 React + TypeScript
                           │
                 TanStack Query
                           │
                     WebSocket
                           │
                           ▼
                    FastAPI Backend
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
      REST API         Event Gateway    Auth/Policy
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                  Application Services
                           │
       ┌───────────┬───────┼───────┬───────────┐
       ▼           ▼       ▼       ▼           ▼
     Tasks       Agents  Memory   Tools      Sessions
       │           │       │       │           │
       └───────────┴───────┼───────┴───────────┘
                           ▼
                      JARVIS CORE
                           │
       ┌───────────────────┼───────────────────┐
       ▼                   ▼                   ▼
    Models              Plugins               MCP
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                    Infrastructure
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
        PostgreSQL       Redis       Object Storage
```

---

# 313. BACKEND → CORE CONTRACT

The backend must treat JARVIS Core as a controlled subsystem:

```text
Backend
   ↓
Core Interface
   ↓
JARVIS Core
```

not:

```text
Backend
   ↓
Arbitrary Core Internals
```

---

# 314. BACKEND → WORKER CONTRACT

```text
API
 ↓
Task
 ↓
Queue
 ↓
Worker
 ↓
Application Service
 ↓
Core
```

---

# 315. BACKEND → DATABASE CONTRACT

```text
Application Service
 ↓
Repository / Persistence Interface
 ↓
SQLAlchemy
 ↓
PostgreSQL
```

---

# 316. BACKEND → CACHE CONTRACT

```text
Application Service
 ↓
Cache / Coordination Interface
 ↓
Redis
```

---

# 317. BACKEND → EVENT CONTRACT

```text
Domain Event
 ↓
Event Dispatcher
 ↓
Event Bus / Redis Streams
 ↓
WebSocket Gateway
 ↓
Frontend
```

---

# 318. BACKEND → TOOL CONTRACT

```text
Agent
 ↓
Tool Gateway
 ↓
Authorization
 ↓
Policy
 ↓
Capability
 ↓
Tool Adapter
 ↓
Execution
```

---

# 319. BACKEND → PLUGIN CONTRACT

```text
Plugin Manager
 ↓
Plugin Contract
 ↓
Capability Boundary
 ↓
Plugin
```

---

# 320. BACKEND → MCP CONTRACT

```text
MCP Manager
 ↓
MCP Client
 ↓
MCP Server
 ↓
External Capability
```

---

# 321. FINAL V1 ARCHITECTURE

```text
========================================================
                 JARVIS BACKEND v1
========================================================

                     CLIENTS
                        │
                        ▼
                ┌───────────────┐
                │    FastAPI    │
                └───────┬───────┘
                        │
            ┌───────────┼───────────┐
            │           │           │
            ▼           ▼           ▼
         REST       WebSocket    Auth/Policy
            │           │           │
            └───────────┼───────────┘
                        ▼
              APPLICATION SERVICES
                        │
       ┌────────────────┼────────────────┐
       │                │                │
       ▼                ▼                ▼
     Tasks            Agents           Memory
       │                │                │
       ▼                ▼                ▼
    Workers          Core Interface   Memory Service
       │                │                │
       └────────────────┼────────────────┘
                        ▼
                   JARVIS CORE
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
      Models         Plugins            MCP
        │               │               │
        └───────────────┼───────────────┘
                        ▼
                 INFRASTRUCTURE
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     PostgreSQL       Redis       Object Storage

========================================================
PRIMARY STACK
========================================================

Python
FastAPI
Starlette / ASGI
Uvicorn
Pydantic v2
REST + OpenAPI
WebSocket
PostgreSQL
SQLAlchemy 2.x
Alembic
Redis
Redis Streams
Dedicated Workers
Modular Monolith

========================================================
```

---

# 322. SOURCE BASIS

Primary technology decisions are based on official project documentation.

Major references:

- FastAPI official documentation — OpenAPI, JSON Schema, WebSocket, streaming, dependency injection and testing capabilities. citeturn0search0
- Starlette official documentation — ASGI foundation and WebSocket capabilities. citeturn0search1turn0search2
- SQLAlchemy 2.x official documentation — ORM, modern query API and asynchronous I/O support. citeturn0search3turn0search4turn0search6
- PostgreSQL official documentation — relational database and JSON/JSONB capabilities. citeturn0search11
- Redis official documentation — Streams, consumer groups and event-stream capabilities. citeturn0search5

Exact dependency versions are intentionally **not frozen in this document**.

They belong to:

```text
VERSION LOCK v1
```

and:

```text
21_APPROVED_SOFTWARE_MATRIX.md
```

---

# 323. HANDOFF TO NEXT PHASE

The backend dependency chain is:

```text
11_BACKEND_STACK.md
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
          │
          ▼
ARCHITECTURE COMPLIANCE CHECKER
          │
          ▼
SYSTEM VERIFICATION
          │
          ▼
BACKEND IMPLEMENTATION
          │
          ▼
JARVIS CORE
```

---

# 324. FINAL DECISION

```text
========================================================
JARVIS BACKEND STACK — FINAL v1 DECISION
========================================================

PRIMARY LANGUAGE:
    Python
    APPROVED

WEB FRAMEWORK:
    FastAPI
    APPROVED

ASGI FOUNDATION:
    Starlette
    APPROVED / UNDERLYING

ASGI SERVER:
    Uvicorn
    APPROVED CANDIDATE

VALIDATION:
    Pydantic v2
    APPROVED

API:
    REST + OpenAPI
    APPROVED

REALTIME:
    WebSocket
    APPROVED

SERVER STREAMING:
    SSE
    OPTIONAL

PRIMARY DATABASE:
    PostgreSQL
    APPROVED

ORM:
    SQLAlchemy 2.x
    APPROVED

MIGRATIONS:
    Alembic
    APPROVED CANDIDATE

CACHE:
    Redis
    APPROVED

EVENT STREAM:
    Redis Streams
    APPROVED WHERE JUSTIFIED

TASK EXECUTION:
    Dedicated Workers
    REQUIRED

ARCHITECTURE:
    Modular Monolith
    APPROVED

MICROSERVICES:
    CONDITIONAL / FUTURE

GRAPHQL:
    CONDITIONAL / FUTURE

gRPC:
    CONDITIONAL / FUTURE

DIRECT FRONTEND → DATABASE:
    PROHIBITED

DIRECT FRONTEND → CORE:
    PROHIBITED

DIRECT AGENT → OS:
    PROHIBITED

DIRECT AGENT → DATABASE:
    PROHIBITED

UNCONTROLLED TOOL EXECUTION:
    PROHIBITED

FRONTEND AUTHORIZATION:
    PROHIBITED

MODEL PROVIDER COUPLING:
    PROHIBITED

========================================================

CORE PRINCIPLE:

CLIENT
  ↓
API / EVENTS
  ↓
BACKEND
  ↓
POLICY / CAPABILITY
  ↓
APPLICATION SERVICES
  ↓
CORE / WORKERS
  ↓
INFRASTRUCTURE

========================================================
```

**Final architectural decision:** JARVIS v1 backend'i **Python + FastAPI + Pydantic + SQLAlchemy + PostgreSQL + Redis + WebSocket + dedicated workers** üzerine kurulacak ve başlangıçta **modular monolith** olarak geliştirilecek. Backend; frontend ile JARVIS Core arasında yalnızca bir HTTP API değil, aynı zamanda **authentication, authorization, policy enforcement, task orchestration, event delivery, persistence, capability control ve observability sınırı** olacak.

Böylece `10_FRONTEND_STACK.md` ile birlikte elimizde artık temel kullanıcı ve servis katmanları da tanımlanmış durumda:

```text
09 COMPUTER VISION
        ↓
10 FRONTEND
        ↓
11 BACKEND
        ↓
12 PLUGIN / EXTENSION
        ↓
13 MCP / EXTERNAL INTEGRATION
        ↓
14 SECURITY
        ↓
15 DEVOPS / DEPLOYMENT
        ↓
...
```

Bir sonraki dosya bu sırayla **`12_PLUGIN_AND_EXTENSION_STACK.md`** olacak.