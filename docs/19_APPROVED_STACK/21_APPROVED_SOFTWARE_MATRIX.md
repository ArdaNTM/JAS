# 21 — APPROVED SOFTWARE MATRIX

**Document ID:** JAS-AS-21  
**Document:** `21_APPROVED_SOFTWARE_MATRIX.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED MASTER SOFTWARE MATRIX  
**Primary Domain:** Software Inventory, Architecture Mapping, Technology Governance, Dependency Classification, Runtime Composition and Version-Lock Preparation

**Depends On:**

```text
JAS v1
00_APPROVED_STACK_OVERVIEW.md
01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md
02_CORE_RUNTIME_AND_PROGRAMMING_LANGUAGES.md
03_AI_AND_LLM_FRAMEWORKS.md
04_AGENT_ORCHESTRATION_STACK.md
05_MEMORY_AND_VECTOR_DATABASE_STACK.md
06_DATABASE_AND_STORAGE_STACK.md
07_BROWSER_AUTOMATION_STACK.md
08_VOICE_AND_AUDIO_STACK.md
09_COMPUTER_VISION_STACK.md
10_FRONTEND_STACK.md
11_BACKEND_STACK.md
12_PLUGIN_AND_EXTENSION_STACK.md
13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md
14_SECURITY_STACK.md
15_DEVOPS_AND_DEPLOYMENT_STACK.md
16_MONITORING_AND_OBSERVABILITY_STACK.md
17_TESTING_AND_QUALITY_ASSURANCE_STACK.md
18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md
19_APPROVED_MODELS.md
20_APPROVED_MCP_SERVERS.md
```

**Feeds Into:**

```text
VERSION LOCK
MANIFEST
BOOTSTRAP
ARCHITECTURE COMPLIANCE CHECKER
SYSTEM VERIFICATION
DEPENDENCY GRAPH
SOFTWARE BILL OF MATERIALS
LICENSE / COMPLIANCE SYSTEM
DEPLOYMENT SYSTEM
```

---

# 1. PURPOSE

This document is the **master software inventory and architecture mapping document** for JARVIS.

Its purpose is to answer one question:

> **Which software technologies constitute the approved JARVIS technology stack, what does each technology do, where does it belong, what is its trust/status level, and how will it be carried into Version Lock and Manifest?**

This document is not merely a package list.

It represents the relationship:

```text
JAS Architecture
       ↓
Approved Technology
       ↓
Software Role
       ↓
Architecture Layer
       ↓
Security Boundary
       ↓
Runtime Dependency
       ↓
Version Lock
       ↓
Manifest
       ↓
Bootstrap
```

---

# 2. MASTER PRINCIPLE

The Software Matrix is the authoritative **cross-reference layer** between architectural decisions and concrete software components.

It does not replace the individual Approved Stack documents.

Instead:

```text
Individual Stack Documents
        ↓
Detailed Technology Decisions
        ↓
Software Matrix
        ↓
Version Lock
```

---

# 3. SOFTWARE MATRIX ≠ VERSION LOCK

This distinction is mandatory.

The Software Matrix answers:

```text
What?
Why?
Where?
Role?
Status?
Dependency?
Security class?
```

Version Lock answers:

```text
Exactly which version?
Exactly which revision?
Exactly which digest?
Exactly which model revision?
Exactly which artifact?
```

Therefore:

```text
Software Matrix
    ≠
Version Lock
```

---

# 4. SOFTWARE MATRIX ≠ MANIFEST

The Software Matrix describes the approved software inventory.

The Manifest will later describe the **operational composition of a JARVIS installation**.

Therefore:

```text
Software Matrix
        ↓
Approved Inventory

Manifest
        ↓
Required Runtime Composition
```

---

# 5. STATUS MODEL

Every software component must have one of the following states:

```text
APPROVED
CONDITIONALLY APPROVED
EXPERIMENTAL
EVALUATION
DEPRECATED
REJECTED
```

---

# 6. APPROVED

`APPROVED` means:

```text
Technology selected
+
Architecture compatible
+
Security acceptable
+
License acceptable
+
Operationally viable
```

It may be included in production architecture subject to normal configuration and version locking.

---

# 7. CONDITIONALLY APPROVED

`CONDITIONALLY APPROVED` means the technology is accepted only under explicit constraints.

Examples:

```text
Restricted permissions
Read-only mode
Sandbox
Specific platform
Specific deployment model
Explicit user approval
```

---

# 8. EXPERIMENTAL

Experimental software may be evaluated or used in controlled development environments.

It must not become an implicit production dependency.

---

# 9. EVALUATION

Evaluation means the technology has not yet received an architectural approval decision.

---

# 10. DEPRECATED

Deprecated technologies remain documented for compatibility/migration purposes.

They must not be selected for new components.

---

# 11. REJECTED

Rejected technologies are prohibited from the approved JARVIS stack.

The rationale belongs in:

```text
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

---

# 12. APPROVAL DOES NOT MEAN "LATEST"

A technology may be approved while its latest release is not automatically approved.

The correct relationship is:

```text
Technology
    ↓
Approved

Specific Version
    ↓
Version Lock Approval
```

---

# 13. VERSION POLICY

Exact versions are intentionally excluded from most entries in this document.

The process is:

```text
Technology Approved
        ↓
Candidate Version Selected
        ↓
Compatibility Evaluation
        ↓
Security Evaluation
        ↓
Version Lock
```

---

# 14. VERSION LOCK REQUIREMENTS

Every production software component eventually requires:

```text
Package Name
Version
Source
Revision
Checksum/Digest where applicable
License
Platform
Runtime
```

---

# 15. PRIMARY SOFTWARE STACK

The initial JARVIS software stack is divided into:

```text
Runtime
AI / LLM
Agent
Memory
Data
Browser
Voice
Vision
Frontend
Backend
Plugin
MCP
Security
DevOps
Observability
Testing
Build
Models
```

---

# 16. MASTER MATRIX

The following is the initial JARVIS Software Matrix.

| ID | Domain | Software | Role | Status | JAS Layer | Trust |
|---|---|---|---|---|---|---|
| SW-001 | Runtime | Python | Primary application runtime | APPROVED | Core | T1 |
| SW-002 | Runtime | TypeScript | Frontend / typed JS runtime layer | APPROVED | Frontend | T1 |
| SW-003 | Runtime | Rust | Performance/security-critical supporting runtime | CONDITIONALLY APPROVED | Infrastructure | T2 |
| SW-004 | Runtime | C/C++ | Native / performance-critical components | CONDITIONALLY APPROVED | Infrastructure | T3 |
| SW-005 | Backend | FastAPI | API/application backend | APPROVED | Backend | T2 |
| SW-006 | Backend | Pydantic | Data validation/schema layer | APPROVED | Backend/Core | T1 |
| SW-007 | Agent | LangGraph | Agent orchestration/stateful workflows | APPROVED | Agent | T2 |
| SW-008 | Memory | Qdrant | Vector/semantic retrieval | APPROVED | Memory | T2 |
| SW-009 | Database | PostgreSQL | Primary relational database | APPROVED | Data | T2 |
| SW-010 | Cache | Redis | Cache / ephemeral state / coordination | APPROVED | Infrastructure | T2 |
| SW-011 | Browser | Playwright | Browser automation | APPROVED | Browser | T3 |
| SW-012 | Voice | Whisper-compatible STT | Speech recognition | APPROVED | Voice | T2 |
| SW-013 | Vision | Vision model runtime | Image/video understanding | APPROVED | Vision | T3 |
| SW-014 | Frontend | React | UI framework | APPROVED | Frontend | T1 |
| SW-015 | Frontend | Vite | Frontend build/development tool | APPROVED | Frontend | T1 |
| SW-016 | Plugin | JARVIS Plugin SDK | Extension API | APPROVED | Plugins | T2 |
| SW-017 | MCP | MCP Client SDK | MCP integration | APPROVED | MCP | T3 |
| SW-018 | MCP | Approved MCP Servers | External capability providers | CONDITIONAL | MCP | T3–T5 |
| SW-019 | Security | OS security primitives | Host security | APPROVED | Security | T4 |
| SW-020 | Security | Secret Management | Credential protection | APPROVED | Security | T5 |
| SW-021 | Deployment | Docker | Container runtime | APPROVED | Deployment | T4 |
| SW-022 | Observability | OpenTelemetry | Telemetry instrumentation | APPROVED | Observability | T2 |
| SW-023 | Testing | pytest | Python testing | APPROVED | Testing | T1 |
| SW-024 | Testing | Playwright Test / pytest integration | Browser E2E testing | APPROVED | Testing | T2 |
| SW-025 | Quality | Ruff | Linting / formatting | APPROVED | Build/QA | T1 |
| SW-026 | Build | uv | Python package/project management | APPROVED | Build | T2 |
| SW-027 | Build | Node.js | Frontend/tooling runtime | APPROVED | Build | T1 |
| SW-028 | Build | pnpm/npm-compatible ecosystem | JS package management | CONDITIONALLY APPROVED | Build | T2 |
| SW-029 | CI | Git | Source control | APPROVED | DevOps | T2 |
| SW-030 | CI | GitHub | Repository/CI platform integration | CONDITIONALLY APPROVED | DevOps | T3 |
| SW-031 | Container | OCI-compatible images | Deployment artifact | APPROVED | Deployment | T4 |
| SW-032 | Model Runtime | Local model runtime | Local inference | APPROVED | AI | T3 |
| SW-033 | Model Provider | Cloud model provider abstraction | External inference | APPROVED | AI | T3 |
| SW-034 | Data | SQLite | Local lightweight state | APPROVED | Data | T2 |
| SW-035 | Data | Object storage | Binary/artifact storage | APPROVED | Data | T3 |
| SW-036 | Logging | Structured application logging | Logs | APPROVED | Observability | T1 |
| SW-037 | Metrics | OpenTelemetry Metrics | Metrics | APPROVED | Observability | T1 |
| SW-038 | Tracing | OpenTelemetry Traces | Distributed tracing | APPROVED | Observability | T2 |
| SW-039 | Quality | Contract testing framework | Interface validation | APPROVED | Testing | T1 |
| SW-040 | Security | Dependency scanner | Supply-chain security | APPROVED | Security | T2 |

---

# 17. RUNTIME MATRIX

## 17.1 Python

**ID:** `SW-001`

**Status:**

```text
APPROVED
```

**Primary Role:**

```text
Core application runtime
AI orchestration
Backend
Agents
Memory
Tools
Automation
Testing
Bootstrap
```

Python is the primary application development language for JARVIS.

The Python runtime should remain the dominant language for high-level system logic.

---

# 18. PYTHON VERSION POLICY

Python version selection belongs to Version Lock.

The Python 3.14 series is currently a stable major release, but the project must not hard-code a version merely because it is newest. Dependency compatibility and support windows must be evaluated before the final lock. citeturn0search11

---

# 19. TYPESCRIPT

**ID:** `SW-002`

**Status:**

```text
APPROVED
```

**Role:**

```text
Frontend
Web UI
Typed client logic
Frontend SDK
Build ecosystem
```

TypeScript is the preferred language for the JARVIS frontend layer.

---

# 20. TYPESCRIPT BOUNDARY

TypeScript should not become the primary backend language unless a later architecture revision explicitly approves such a change.

---

# 21. RUST

**ID:** `SW-003`

**Status:**

```text
CONDITIONALLY APPROVED
```

Rust may be used for:

```text
Performance-critical components
Security-sensitive native services
High-concurrency components
Native integrations
```

It is not the default JARVIS application language.

---

# 22. C/C++

**ID:** `SW-004`

**Status:**

```text
CONDITIONALLY APPROVED
```

C/C++ may be used for:

```text
Native libraries
GPU integrations
Codec integrations
Hardware interfaces
Performance-critical components
```

C/C++ should not be used for ordinary JARVIS application logic.

---

# 23. RUNTIME LANGUAGE RULE

The preferred hierarchy is:

```text
Python
   ↓
Primary Application Logic

TypeScript
   ↓
Frontend

Rust
   ↓
Selected Native / Performance Components

C/C++
   ↓
Existing Native / GPU / Codec / Hardware Components
```

---

# 24. BACKEND MATRIX

## FastAPI

**ID:** `SW-005`

**Status:**

```text
APPROVED
```

**Role:**

```text
HTTP API
Backend services
Health endpoints
Streaming
Internal service interfaces
```

FastAPI is the approved primary HTTP API framework.

---

# 25. PYDANTIC

**ID:** `SW-006`

**Status:**

```text
APPROVED
```

**Role:**

```text
Schema validation
Configuration models
API models
Structured tool inputs
Structured outputs
```

Pydantic forms an important typed boundary between model-generated data and application execution.

---

# 26. BACKEND PRINCIPLE

The backend must not become the JARVIS reasoning engine.

Correct architecture:

```text
Frontend
   ↓
Backend API
   ↓
Application Services
   ↓
JARVIS Core
   ↓
Agents
```

---

# 27. AGENT ORCHESTRATION

## LangGraph

**ID:** `SW-007`

**Status:**

```text
APPROVED
```

**Role:**

```text
Agent workflows
Stateful orchestration
Durable workflows
Checkpointing
Human-in-the-loop
Execution graphs
```

LangGraph is selected as the initial agent orchestration framework.

---

# 28. AGENT FRAMEWORK BOUNDARY

LangGraph must not become the entire JARVIS architecture.

It is an orchestration component.

```text
JARVIS Core
    ↓
Agent Runtime
    ↓
LangGraph
```

---

# 29. CUSTOM ORCHESTRATION

Custom JARVIS orchestration may exist around LangGraph where required.

The project must avoid framework lock-in at the architectural boundary.

---

# 30. MEMORY MATRIX

## Qdrant

**ID:** `SW-008`

**Status:**

```text
APPROVED
```

**Role:**

```text
Vector search
Semantic retrieval
Embedding storage
Hybrid retrieval
Memory indexing
```

Qdrant is selected as the primary dedicated vector retrieval system.

Qdrant supports vector search, payloads, filtering, hybrid search and related retrieval capabilities. citeturn0search2turn0search7

---

# 31. QDRANT BOUNDARY

Qdrant is not the complete JARVIS memory architecture.

It is:

```text
Memory Infrastructure
```

not:

```text
Memory Governance
```

---

# 32. MEMORY ARCHITECTURE

```text
Memory Governance
        ↓
Memory Service
        ↓
Retrieval
        ↓
Qdrant
        ↓
Vectors / Payloads
```

---

# 33. POSTGRESQL

**ID:** `SW-009`

**Status:**

```text
APPROVED
```

**Role:**

```text
Primary relational database
Structured state
Users
Tasks
Permissions
Metadata
Audit references
System configuration
```

PostgreSQL is the primary relational data store.

PostgreSQL major versions have a five-year support lifecycle, making its long-term support model appropriate for the JARVIS platform. citeturn0search3

---

# 34. POSTGRESQL VERSION POLICY

The project will select a supported PostgreSQL major version during Version Lock.

The current minor release of the selected major version should be preferred unless compatibility testing requires otherwise. citeturn0search3

---

# 35. REDIS

**ID:** `SW-010`

**Status:**

```text
APPROVED
```

**Role:**

```text
Cache
Ephemeral state
Rate limiting
Distributed coordination
Queues where appropriate
Short-lived session state
```

Redis is not the authoritative long-term database.

---

# 36. REDIS BOUNDARY

Persistent authoritative data belongs in PostgreSQL or another explicitly selected storage system.

---

# 37. SQLITE

**ID:** `SW-034`

**Status:**

```text
APPROVED
```

SQLite may be used for:

```text
Local state
Development
Offline operation
Small embedded metadata
Local caches
Single-process state
```

It should not replace PostgreSQL for multi-service production state.

---

# 38. OBJECT STORAGE

**ID:** `SW-035`

**Status:**

```text
APPROVED
```

Object storage is intended for:

```text
Images
Audio
Video
Documents
Model artifacts
Generated files
Backups
Large binary artifacts
```

The concrete implementation may be:

```text
Local object storage
S3-compatible storage
Cloud object storage
```

depending on deployment.

---

# 39. BROWSER AUTOMATION

## Playwright

**ID:** `SW-011`

**Status:**

```text
APPROVED
```

**Role:**

```text
Browser automation
Browser agent
E2E testing
Web interaction
Screenshots
Downloads
Uploads
Browser sessions
```

Playwright supports Chromium, Firefox and WebKit and provides both sync and async Python APIs. citeturn0search5turn0search15

---

# 40. PLAYWRIGHT VERSION/BROWSER COUPLING

Playwright versions are coupled to the browser binaries they manage.

Therefore the Version Lock must lock both:

```text
Playwright Version
+
Browser Revision
```

where required. citeturn0search0

---

# 41. PLAYWRIGHT BROWSER BASELINE

Initial supported browser engines:

```text
Chromium
Firefox
WebKit
```

---

# 42. PRIMARY BROWSER

The default JARVIS browser automation target should be Chromium unless a task explicitly requires another engine.

---

# 43. BRANDED BROWSERS

Chrome and Edge may be used when required.

However:

```text
Playwright Chromium
```

and:

```text
Installed Google Chrome / Microsoft Edge
```

are not considered identical deployment artifacts.

---

# 44. BROWSER SECURITY

Playwright sessions must integrate with:

```text
Security Policy
Credential Isolation
Browser Profile Isolation
Network Policy
Download Policy
Upload Policy
```

---

# 45. VOICE MATRIX

## Speech-to-Text

**ID:** `SW-012`

**Status:**

```text
APPROVED
```

**Role:**

```text
Speech recognition
Voice command input
Transcription
Streaming transcription
```

The concrete STT implementation may be local or cloud-backed.

---

# 46. STT ARCHITECTURE

```text
Microphone
    ↓
Audio Capture
    ↓
VAD
    ↓
STT
    ↓
Intent
```

---

# 47. STT MODEL LOCK

The exact model is governed by:

```text
19_APPROVED_MODELS.md
```

and eventually:

```text
models.lock
```

---

# 48. TEXT-TO-SPEECH

TTS is an approved architectural capability.

The exact implementation is model/provider dependent.

---

# 49. TTS REQUIREMENTS

The selected TTS implementation should support, where possible:

```text
Streaming
Low latency
Interruption
Multiple voices
Local/cloud abstraction
```

---

# 50. VOICE PROVIDER ABSTRACTION

Voice providers must not be hard-coded into the Core.

Architecture:

```text
Voice Service
      ↓
Provider Interface
      ↓
Local / Cloud TTS
```

---

# 51. COMPUTER VISION

## Vision Runtime

**ID:** `SW-013`

**Status:**

```text
APPROVED
```

**Role:**

```text
Image understanding
Screenshot understanding
OCR
Object detection
Video analysis
Visual reasoning
```

---

# 52. VISION IMPLEMENTATION

Vision is intentionally provider/model abstracted.

Possible implementations include:

```text
Local vision models
Cloud vision-capable LLMs
Specialized CV models
OCR engines
```

The exact model belongs in `19_APPROVED_MODELS.md`.

---

# 53. VISION BOUNDARY

Vision models must not directly control the operating system.

Correct flow:

```text
Vision
 ↓
Perception
 ↓
Agent
 ↓
Policy
 ↓
Tool
```

---

# 54. FRONTEND MATRIX

## React

**ID:** `SW-014`

**Status:**

```text
APPROVED
```

**Role:**

```text
JARVIS UI
Chat
Voice UI
System dashboard
Agent activity
Settings
Permissions
Memory UI
```

---

# 55. REACT BOUNDARY

React is a presentation layer.

It must not directly access privileged infrastructure.

---

# 56. VITE

**ID:** `SW-015`

**Status:**

```text
APPROVED
```

**Role:**

```text
Frontend development
Build
Bundling
Development server
```

---

# 57. FRONTEND ARCHITECTURE

```text
React
 ↓
TypeScript
 ↓
Frontend Services
 ↓
Backend API
 ↓
JARVIS Core
```

---

# 58. FRONTEND SECURITY

Frontend credentials must not contain:

```text
Database passwords
Model provider secrets
MCP secrets
OS credentials
```

---

# 59. PLUGIN SYSTEM

## JARVIS Plugin SDK

**ID:** `SW-016`

**Status:**

```text
APPROVED
```

The JARVIS Plugin SDK is an internal architectural interface.

It is not an external third-party package.

---

# 60. PLUGIN PURPOSE

Plugins provide:

```text
Capability Extensions
Domain Integrations
Optional Features
User Extensions
```

---

# 61. PLUGIN ISOLATION

Plugins must not automatically receive:

```text
Filesystem
Network
Shell
Database
Credentials
```

access.

---

# 62. PLUGIN CAPABILITY MODEL

```text
Plugin
 ↓
Declared Capabilities
 ↓
Permission Policy
 ↓
Execution
```

---

# 63. MCP CLIENT

## MCP Client SDK

**ID:** `SW-017`

**Status:**

```text
APPROVED
```

The MCP client provides the standardized integration interface to approved MCP servers.

---

# 64. MCP VERSION

The MCP protocol version and client SDK version must be explicitly version locked.

---

# 65. MCP SERVER INVENTORY

**ID:** `SW-018`

**Status:**

```text
CONDITIONALLY APPROVED
```

MCP servers are not one software package.

They are a governed collection of external capability providers.

---

# 66. MCP SERVER TRUST

```text
MCP Registry
    ≠
JARVIS Approval
```

Only individually reviewed servers enter the approved inventory.

---

# 67. MCP BASELINE

Current baseline:

```text
Time
        APPROVED

Filesystem
        CONDITIONAL

Git
        CONDITIONAL

Fetch
        CONDITIONAL

Memory
        CONDITIONAL

Browser
        CONDITIONAL

Database
        CONDITIONAL

Docker
        CONDITIONAL

GitHub
        CONDITIONAL

Sequential Thinking
        EXPERIMENTAL

Everything
        EVALUATION
```

---

# 68. SECURITY STACK

## OS Security Primitives

**ID:** `SW-019`

**Status:**

```text
APPROVED
```

Operating system security mechanisms are part of the JARVIS security boundary.

---

# 69. SECURITY RESPONSIBILITIES

The security layer includes:

```text
Authentication
Authorization
Permissions
Process Isolation
Filesystem Restrictions
Network Restrictions
Credential Isolation
Audit
Sandboxing
```

---

# 70. SECRET MANAGEMENT

**ID:** `SW-020`

**Status:**

```text
APPROVED
```

The exact secret-management implementation is deployment dependent.

Possible implementations:

```text
OS credential store
Dedicated secret manager
Container secret mechanism
Cloud secret manager
Encrypted local vault
```

---

# 71. SECRET RULE

No production secret may be hard-coded into:

```text
Source Code
Frontend
Prompt
Model Context
Git Repository
MCP Tool Output
```

---

# 72. DOCKER

**ID:** `SW-021`

**Status:**

```text
APPROVED
```

**Role:**

```text
Containerization
Service isolation
Reproducible environments
Local deployment
CI environments
Production services
```

Docker containers provide process/filesystem/network isolation boundaries, although the actual security level depends on configuration. citeturn0search6turn0search9

---

# 73. DOCKER SECURITY

Production containers should prefer:

```text
Non-root
Minimal image
Read-only filesystem where practical
Dropped capabilities
Resource limits
Explicit network
Explicit volumes
```

---

# 74. DOCKER SOCKET

Unrestricted Docker socket access is not allowed by default.

---

# 75. CONTAINER IMAGE POLICY

Production images must be versioned and preferably pinned by immutable digest.

---

# 76. OCI

**ID:** `SW-031`

**Status:**

```text
APPROVED
```

OCI-compatible images/artifacts are the preferred portable container artifact format.

---

# 77. OBSERVABILITY

## OpenTelemetry

**ID:** `SW-022`

**Status:**

```text
APPROVED
```

OpenTelemetry is the approved vendor-neutral telemetry instrumentation layer.

It supports traces, metrics and logs and provides a vendor-neutral Collector architecture. citeturn0search1

---

# 78. OPENTELEMETRY ROLE

```text
Application
 ↓
Instrumentation
 ↓
OpenTelemetry
 ↓
Collector / Exporter
 ↓
Observability Backend
```

---

# 79. TELEMETRY TYPES

JARVIS should support:

```text
Logs
Metrics
Traces
Events
Audit Events
```

---

# 80. LOGGING

**ID:** `SW-036`

**Status:**

```text
APPROVED
```

Application logging must be structured.

---

# 81. STRUCTURED LOGGING

Preferred fields:

```text
timestamp
level
service
component
request_id
trace_id
agent_id
tool_id
event
status
duration
```

---

# 82. SENSITIVE LOGGING

Logs must not contain:

```text
Passwords
API Keys
Access Tokens
Private Keys
Full Sensitive Documents
```

---

# 83. METRICS

**ID:** `SW-037`

**Status:**

```text
APPROVED
```

Metrics include:

```text
Latency
Throughput
Error Rate
CPU
Memory
GPU
Token Usage
Tool Usage
Agent Duration
Browser Duration
MCP Duration
```

---

# 84. TRACING

**ID:** `SW-038`

**Status:**

```text
APPROVED
```

Tracing must allow the system to reconstruct execution paths without exposing sensitive content unnecessarily.

---

# 85. TESTING

## pytest

**ID:** `SW-023`

**Status:**

```text
APPROVED
```

**Role:**

```text
Unit tests
Integration tests
Backend tests
Agent tests
Core tests
```

---

# 86. PLAYWRIGHT TESTING

**ID:** `SW-024`

**Status:**

```text
APPROVED
```

Playwright's official Python documentation recommends its pytest integration for E2E testing. citeturn0search5

---

# 87. TESTING LAYERS

```text
Unit
 ↓
Component
 ↓
Integration
 ↓
Contract
 ↓
System
 ↓
E2E
 ↓
Performance
 ↓
Security
```

---

# 88. LLM EVALUATION

LLM and agent evaluation are separate from ordinary software testing.

Required categories:

```text
Model Quality
Tool Selection
Planning
Memory Retrieval
Hallucination
Safety
Regression
```

---

# 89. RUFF

**ID:** `SW-025`

**Status:**

```text
APPROVED
```

**Role:**

```text
Python linting
Formatting
Static quality checks
```

---

# 90. RUFF POLICY

Ruff should be integrated into:

```text
Local Development
Pre-commit
CI
Bootstrap Validation
```

---

# 91. UV

**ID:** `SW-026`

**Status:**

```text
APPROVED
```

**Role:**

```text
Python project management
Dependency resolution
Virtual environments
Locking
Package workflows
```

---

# 92. UV PRINCIPLE

The Python dependency system should prioritize:

```text
Reproducibility
Speed
Locking
Isolation
Cross-platform behavior
```

---

# 93. NODE.JS

**ID:** `SW-027`

**Status:**

```text
APPROVED
```

**Role:**

```text
Frontend build tooling
TypeScript ecosystem
JavaScript tooling
Developer utilities
```

Node.js is not the primary JARVIS backend runtime.

---

# 94. JAVASCRIPT PACKAGE MANAGEMENT

**ID:** `SW-028`

**Status:**

```text
CONDITIONALLY APPROVED
```

The exact package manager will be selected and locked in the Build Toolchain and Version Lock stages.

---

# 95. PACKAGE MANAGER PRINCIPLE

The project must avoid simultaneously introducing multiple package managers for the same ecosystem without a documented reason.

---

# 96. GIT

**ID:** `SW-029`

**Status:**

```text
APPROVED
```

**Role:**

```text
Source control
Version history
Branching
Release management
```

Git is the authoritative source-control system.

---

# 97. GITHUB

**ID:** `SW-030`

**Status:**

```text
CONDITIONALLY APPROVED
```

GitHub may provide:

```text
Repository Hosting
CI
Issue Tracking
Pull Requests
Release Management
MCP Integration
```

but the JARVIS architecture must remain portable enough not to make GitHub the internal source-control abstraction itself.

---

# 98. LOCAL GIT

Core development must remain functional with local Git even when external GitHub services are unavailable.

---

# 99. CI/CD

CI/CD implementation may use GitHub Actions or another approved CI platform.

The CI interface must remain abstracted from application logic.

---

# 100. MODEL RUNTIME

**ID:** `SW-032`

**Status:**

```text
APPROVED
```

Local model runtime is an architectural capability.

The exact runtime is selected through:

```text
03_AI_AND_LLM_FRAMEWORKS.md
19_APPROVED_MODELS.md
```

---

# 101. LOCAL MODEL PRINCIPLE

Local inference should be supported where practical for:

```text
Privacy
Offline operation
Latency
Cost control
Sensitive workloads
```

---

# 102. CLOUD MODEL PROVIDER

**ID:** `SW-033`

**Status:**

```text
APPROVED
```

Cloud model providers may be used through a provider abstraction.

---

# 103. MODEL PROVIDER ABSTRACTION

```text
JARVIS Model Interface
       ↓
Provider Router
       ├── Local
       ├── Cloud A
       ├── Cloud B
       └── Future Provider
```

---

# 104. NO PROVIDER LOCK-IN

The Core must not depend directly on provider-specific APIs wherever an abstraction is practical.

---

# 105. MODEL SELECTION

Model selection is governed by:

```text
19_APPROVED_MODELS.md
```

---

# 106. MODEL VERSION LOCK

Exact:

```text
Model
Revision
Quantization
Runtime
Provider
```

must be locked before production deployment.

---

# 107. DATABASE MATRIX

The initial data architecture is:

```text
PostgreSQL
    ↓
Authoritative relational state

Qdrant
    ↓
Vector retrieval

Redis
    ↓
Ephemeral/cache/coordination

SQLite
    ↓
Local embedded state

Object Storage
    ↓
Large binary artifacts
```

---

# 108. DATA RESPONSIBILITY

No database should become the universal storage system.

---

# 109. CACHE RESPONSIBILITY

Redis is not a source of truth for durable business state.

---

# 110. VECTOR RESPONSIBILITY

Qdrant is not a replacement for relational state.

---

# 111. OBJECT STORAGE RESPONSIBILITY

Object storage is not a replacement for metadata databases.

---

# 112. BROWSER SOFTWARE MATRIX

Browser stack:

```text
Playwright
Chromium
Firefox
WebKit
```

with browser binaries managed and pinned through the Playwright installation/version process.

Playwright explicitly couples each Playwright release to specific browser binaries. citeturn0search0

---

# 113. VOICE SOFTWARE MATRIX

```text
Audio Capture
VAD
STT
TTS
Audio Playback
```

Each component remains replaceable behind the Voice Service interface.

---

# 114. VISION SOFTWARE MATRIX

```text
Vision Model
OCR
Object Detection
Image Processing
Video Processing
```

remain provider/model abstracted.

---

# 115. MCP SOFTWARE MATRIX

```text
MCP Client
MCP Gateway
MCP Registry
Approved MCP Servers
```

---

# 116. MCP REGISTRY

The official MCP Registry is a discovery mechanism for MCP servers.

JARVIS maintains its own approval inventory.

The existence of a server in the registry does not automatically grant production approval. citeturn0search14

---

# 117. SECURITY SOFTWARE MATRIX

Security components are divided into:

```text
Identity
Authentication
Authorization
Secrets
Sandboxing
Network Policy
Filesystem Policy
Audit
Supply Chain
```

---

# 118. SECURITY IMPLEMENTATION POLICY

Security must be implemented at multiple layers.

```text
OS
 ↓
Container
 ↓
Service
 ↓
Application
 ↓
Agent
 ↓
Tool
 ↓
MCP
```

---

# 119. NO SINGLE SECURITY LAYER

No single component is considered sufficient for complete JARVIS security.

---

# 120. DEPLOYMENT SOFTWARE MATRIX

```text
Docker
OCI
Git
CI/CD
Environment Configuration
Secrets
Health Checks
Backup
Monitoring
```

---

# 121. ENVIRONMENT MATRIX

JARVIS defines:

| Environment | Purpose | Risk |
|---|---|---|
| Development | Active development | Medium |
| Testing | Automated validation | Low/controlled |
| Staging | Production-like validation | High |
| Production | Real user/system operation | Highest |

---

# 122. DEVELOPMENT SOFTWARE

Development may use:

```text
Debug Tools
Local Models
Experimental MCP
Mock Services
Test Databases
```

that are prohibited from production.

---

# 123. STAGING SOFTWARE

Staging should match production architecture as closely as practical.

---

# 124. PRODUCTION SOFTWARE

Production must use only:

```text
APPROVED
```

or explicitly:

```text
CONDITIONALLY APPROVED
```

components satisfying their conditions.

---

# 125. EXPERIMENTAL COMPONENT RULE

Experimental software must never silently cross into production.

---

# 126. DEPENDENCY GRAPH

The master software dependency relationship is:

```text
                    JARVIS
                       │
             ┌─────────┴─────────┐
             │                   │
           Core              Frontend
             │                   │
          Python             TypeScript
             │                   │
          Agents              React
             │                   │
        LangGraph              Vite
             │
       ┌─────┼─────┐
       │     │     │
    Memory  Tools  Backend
       │     │       │
    Qdrant MCP    FastAPI
       │     │       │
       │   Security Pydantic
       │
    PostgreSQL
       │
    Redis
```

---

# 127. BROWSER DEPENDENCY GRAPH

```text
Browser Agent
      ↓
Playwright
      ↓
Browser Runtime
      ├── Chromium
      ├── Firefox
      └── WebKit
```

---

# 128. MCP DEPENDENCY GRAPH

```text
Agent
  ↓
Tool Interface
  ↓
MCP Gateway
  ↓
MCP Client SDK
  ↓
MCP Server
  ↓
External System
```

---

# 129. OBSERVABILITY DEPENDENCY GRAPH

```text
JARVIS Services
      ↓
Instrumentation
      ↓
OpenTelemetry
      ↓
Collector
      ↓
Telemetry Backend
```

---

# 130. DEPLOYMENT DEPENDENCY GRAPH

```text
Source
 ↓
Git
 ↓
Build
 ↓
Container Image
 ↓
OCI Artifact
 ↓
Deployment
 ↓
Health Check
 ↓
Monitoring
```

---

# 131. TESTING DEPENDENCY GRAPH

```text
Source
 ↓
pytest
 ↓
Unit / Integration
 ↓
Playwright
 ↓
E2E
 ↓
LLM / Agent Evaluation
 ↓
Security
```

---

# 132. BOOTSTRAP DEPENDENCY GRAPH

Bootstrap must eventually resolve:

```text
Python
Node.js
Package Manager
Docker
Git
Application Dependencies
Models
MCP Servers
Browser Binaries
Configuration
Secrets References
```

---

# 133. BOOTSTRAP PRINCIPLE

Bootstrap must consume:

```text
Manifest
+
Version Lock
+
Approved Software Matrix
```

rather than maintaining a separate conflicting technology list.

---

# 134. SOFTWARE MATRIX AS SOURCE FOR BOOTSTRAP

The Bootstrap system may use this document as an inventory reference.

However, exact installation versions belong to Version Lock.

---

# 135. COMPLIANCE CHECKER

The Architecture Compliance Checker should verify software against this matrix.

---

# 136. COMPLIANCE EXAMPLE

If code introduces:

```text
New Database
```

the checker should be able to determine:

```text
Is it in the Approved Software Matrix?
```

If not:

```text
COMPLIANCE FAILED
```

unless the component is explicitly marked experimental and the environment allows it.

---

# 137. UNAPPROVED DEPENDENCY

A new production dependency requires:

```text
Technology Evaluation
↓
Approved Stack Update
↓
Software Matrix Update
↓
Version Lock Update
↓
Manifest Update
```

---

# 138. DEPENDENCY DRIFT

Dependency drift is prohibited in production.

---

# 139. DRIFT DETECTION

System Verification should detect:

```text
Unexpected Package
Unexpected Version
Unexpected Binary
Unexpected Container
Unexpected MCP Server
Unexpected Model
```

---

# 140. SOFTWARE BILL OF MATERIALS

JARVIS should eventually generate an SBOM from the locked software environment.

---

# 141. SBOM PURPOSE

The SBOM should identify:

```text
Direct Dependencies
Transitive Dependencies
Versions
Licenses
Vulnerabilities
Artifacts
```

---

# 142. LICENSE MATRIX

Every software component must eventually map to:

```text
License
Copyright
Attribution
Distribution Restrictions
Commercial Restrictions
```

---

# 143. LICENSE STATUS

License status belongs to:

```text
23_LICENSE_AND_COMPLIANCE.md
```

The Software Matrix provides the cross-reference.

---

# 144. SECURITY MATRIX

Every component should have a security classification.

Suggested classification:

```text
T0
T1
T2
T3
T4
T5
```

matching the capability trust model.

---

# 145. TRUST LEVELS

```text
T0 — Informational
T1 — Read-only local
T2 — Read-only external
T3 — Controlled write
T4 — Privileged
T5 — Administrative
```

---

# 146. SOFTWARE TRUST ≠ TOOL TRUST

A software package may be trusted while a tool exposed by it is high-risk.

Example:

```text
Playwright
    ↓
Trusted software

Browser "delete account" action
    ↓
High-risk capability
```

---

# 147. SOFTWARE CAPABILITY MATRIX

| Component | Read | Write | Execute | External Side Effect | Privileged |
|---|---:|---:|---:|---:|---:|
| Python | Yes | Yes | Yes | Indirect | Potentially |
| FastAPI | Yes | Yes | Service | Yes | No |
| Qdrant | Yes | Yes | No | No | No |
| PostgreSQL | Yes | Yes | SQL | No/Indirect | Potentially |
| Redis | Yes | Yes | Limited | No | No |
| Playwright | Yes | Yes | Browser actions | Yes | Potentially |
| Docker | Yes | Yes | Yes | Yes | Yes |
| MCP | Yes | Yes | Tool-dependent | Yes | Tool-dependent |
| OpenTelemetry | Yes | Telemetry | No | No | No |
| Git | Yes | Yes | Commands | Remote side effects | Potentially |

---

# 148. SOFTWARE LIFECYCLE

Every component follows:

```text
Candidate
   ↓
Evaluated
   ↓
Approved
   ↓
Version Locked
   ↓
Production
   ↓
Maintained
   ↓
Deprecated
   ↓
Removed
```

---

# 149. SOFTWARE UPDATE

Updates are not automatic approval.

---

# 150. UPDATE PROCESS

```text
New Release
   ↓
Security Review
   ↓
Compatibility Review
   ↓
Regression Tests
   ↓
Performance Tests
   ↓
Approval
   ↓
Version Lock
```

---

# 151. SECURITY UPDATE

Critical security fixes may use an expedited process.

---

# 152. BREAKING UPDATE

Breaking releases require explicit compatibility testing.

---

# 153. ROLLBACK

Every critical software component must have a rollback path.

---

# 154. ROLLBACK DATA

Rollback should identify:

```text
Previous Version
Previous Image
Previous Config
Previous Database Migration
```

where applicable.

---

# 155. SOFTWARE REPLACEMENT

Replacement requires:

```text
Capability Compatibility
API Compatibility
Security Compatibility
Performance Evaluation
Migration Plan
```

---

# 156. NO TECHNOLOGY FASHION

Technology selection is not based on:

```text
GitHub Stars
Social Media Popularity
Trend
Hype
LLM Recommendation
```

---

# 157. TECHNOLOGY DECISION AUTHORITY

The hierarchy is:

```text
JAS
 ↓
Approved Stack
 ↓
Software Matrix
 ↓
Version Lock
 ↓
Manifest
 ↓
Code
```

---

# 158. CODE CANNOT OVERRIDE MATRIX

If code introduces an unapproved dependency:

```text
Code
    ≠
Architecture Authority
```

---

# 159. MATRIX CANNOT OVERRIDE JAS

If the matrix conflicts with JAS:

```text
JAS
```

has authority.

The matrix must be corrected.

---

# 160. MATRIX REVISION

Changes require:

```text
Reason
Impact
Affected Components
Security Impact
License Impact
Version Impact
Bootstrap Impact
Manifest Impact
```

---

# 161. SOFTWARE MATRIX VERSIONING

This document is versioned independently:

```text
v1.0
v1.1
v1.2
...
```

---

# 162. MAJOR MATRIX REVISION

A major revision may be required for:

```text
Major Architecture Change
Core Runtime Change
Database Architecture Change
Agent Framework Change
Security Architecture Change
Deployment Architecture Change
```

---

# 163. MINOR MATRIX REVISION

Minor revisions may add:

```text
Approved Tool
New Optional Integration
New Supporting Utility
```

without changing core architecture.

---

# 164. PATCH REVISION

Patch changes include:

```text
Clarification
Documentation
Metadata
Non-functional correction
```

---

# 165. APPROVAL RECORD

Every major software decision should record:

```text
Technology
Version at Evaluation
Alternatives
Reason
Security
License
Performance
Decision
```

---

# 166. SOFTWARE ALTERNATIVES

Alternatives are not erased.

They are documented in:

```text
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

when rejected.

---

# 167. CURRENT PRIMARY STACK

The current primary JARVIS stack is:

```text
============================================================
                 JARVIS PRIMARY STACK
============================================================

LANGUAGE / RUNTIME
------------------------------------------------------------
Python
TypeScript

BACKEND
------------------------------------------------------------
FastAPI
Pydantic

AGENTS
------------------------------------------------------------
LangGraph

MEMORY
------------------------------------------------------------
Qdrant

DATA
------------------------------------------------------------
PostgreSQL
Redis
SQLite
Object Storage

BROWSER
------------------------------------------------------------
Playwright
Chromium
Firefox
WebKit

FRONTEND
------------------------------------------------------------
React
TypeScript
Vite

MCP
------------------------------------------------------------
MCP Client SDK
MCP Gateway
Approved MCP Servers

SECURITY
------------------------------------------------------------
OS Security
Secret Management
Sandboxing
Authorization
Audit

DEPLOYMENT
------------------------------------------------------------
Docker
OCI

OBSERVABILITY
------------------------------------------------------------
OpenTelemetry
Structured Logging
Metrics
Tracing

TESTING
------------------------------------------------------------
pytest
Playwright Testing
Contract Testing
LLM / Agent Evaluation

BUILD
------------------------------------------------------------
uv
Node.js
Approved JS Package Manager
Ruff
Git

MODELS
------------------------------------------------------------
Approved Model Inventory

============================================================
```

---

# 168. CONDITIONAL STACK

The following technologies are approved only for specific use cases:

```text
Rust
C/C++
Community MCP Servers
Docker privileged capabilities
Shell execution
Authenticated browser automation
Database write access
External API write access
Cloud model providers
```

---

# 169. EXPERIMENTAL STACK

Initial experimental category:

```text
Sequential Thinking MCP
```

Additional experimental technologies must not become dependencies of the stable core without approval.

---

# 170. EVALUATION STACK

Evaluation technologies may include:

```text
Experimental MCP Servers
Alternative Agent Frameworks
Alternative Vector Databases
Alternative Model Runtimes
Alternative Voice Engines
Alternative Vision Engines
```

---

# 171. PRIMARY VS SECONDARY TECHNOLOGIES

The matrix distinguishes:

```text
Primary
Secondary
Optional
Conditional
Experimental
```

---

# 172. PRIMARY

A primary technology is the default implementation.

---

# 173. SECONDARY

A secondary technology supports the primary architecture.

---

# 174. OPTIONAL

Optional software provides additional functionality without being required for the minimal JARVIS installation.

---

# 175. CONDITIONAL

Conditional software is available only under defined constraints.

---

# 176. EXPERIMENTAL

Experimental software is not part of the stable production baseline.

---

# 177. REQUIRED VS OPTIONAL

The Manifest will later classify components as:

```text
REQUIRED
OPTIONAL
PLATFORM-SPECIFIC
DEVELOPMENT-ONLY
TESTING-ONLY
EXPERIMENTAL
```

---

# 178. MINIMAL JARVIS INSTALLATION

The minimum production system should require only:

```text
Python
Backend
Core
Agent Runtime
Primary Database
Memory Infrastructure
Security
Observability
Testing/Verification
Deployment Runtime
```

Other components may be optional.

---

# 179. FULL JARVIS INSTALLATION

A full installation may additionally include:

```text
Voice
Vision
Browser
MCP
Plugins
Frontend
Local Models
External Integrations
```

---

# 180. OFFLINE JARVIS

An offline profile should minimize:

```text
Cloud APIs
Remote MCP
External Network
External Authentication
```

---

# 181. CLOUD-ENABLED JARVIS

A cloud-enabled profile may use:

```text
Cloud LLM
Cloud TTS
Cloud STT
Cloud Storage
Remote MCP
External APIs
```

subject to security policy.

---

# 182. HYBRID JARVIS

The preferred long-term deployment model is:

```text
Local Core
+
Local Security
+
Local State
+
Optional Cloud Intelligence
```

where privacy and operational requirements permit.

---

# 183. PLATFORM MATRIX

| Component | Windows | Linux | macOS |
|---|---:|---:|---:|
| Python | Yes | Yes | Yes |
| TypeScript | Yes | Yes | Yes |
| FastAPI | Yes | Yes | Yes |
| LangGraph | Yes | Yes | Yes |
| PostgreSQL | Yes | Yes | Yes |
| Qdrant | Yes | Yes | Yes |
| Redis | Yes | Yes | Yes |
| Playwright | Yes | Yes | Yes |
| Docker | Yes* | Yes | Yes |
| React/Vite | Yes | Yes | Yes |
| OpenTelemetry | Yes | Yes | Yes |
| pytest | Yes | Yes | Yes |

`*` Docker Desktop/platform-specific deployment behavior must be evaluated separately.

---

# 184. GPU MATRIX

GPU support is model/runtime dependent.

Potential GPU stacks include:

```text
CUDA
ROCm
CPU-only
Platform-specific acceleration
```

The exact GPU stack is governed by model/runtime requirements.

---

# 185. GPU PRINCIPLE

GPU dependencies must not be introduced into components that can operate without GPU acceleration unless required.

---

# 186. NATIVE DEPENDENCIES

Native dependencies must be recorded in:

```text
Version Lock
Bootstrap
System Verification
```

---

# 187. SYSTEM REQUIREMENTS

Bootstrap must eventually verify:

```text
CPU
RAM
GPU
VRAM
Disk
OS
Python
Node
Docker
Network
```

---

# 188. BROWSER REQUIREMENTS

Bootstrap must verify Playwright browser binaries separately from the Python package.

---

# 189. MODEL REQUIREMENTS

Bootstrap must verify:

```text
Model
Runtime
VRAM
Disk
Quantization
Provider
```

---

# 190. SOFTWARE MATRIX AND HARDWARE

Software approval does not imply universal hardware compatibility.

---

# 191. HARDWARE COMPATIBILITY

Each hardware-sensitive component should eventually define:

```text
Minimum
Recommended
Supported
Unsupported
```

profiles.

---

# 192. RESOURCE CLASSIFICATION

Each component should eventually have:

```text
CPU Profile
RAM Profile
GPU Profile
Disk Profile
Network Profile
```

---

# 193. PERFORMANCE CLASS

Suggested categories:

```text
LOW
MEDIUM
HIGH
GPU-DEPENDENT
NETWORK-DEPENDENT
```

---

# 194. SOFTWARE MATRIX PERFORMANCE

Initial classification:

| Component | CPU | RAM | GPU | Network |
|---|---|---|---|---|
| Python Core | Medium | Medium | No | Optional |
| FastAPI | Low/Medium | Low | No | Yes |
| LangGraph | Medium | Medium | No | Optional |
| Qdrant | Medium | Medium/High | Optional | Local |
| PostgreSQL | Medium | Medium | No | Local |
| Redis | Low | Medium | No | Local |
| Playwright | Medium/High | Medium | No | Usually |
| Voice | Medium/High | Medium | Optional | Optional |
| Vision | High | High | Often | Optional |
| React/Vite | Low/Medium | Low/Medium | No | Development |
| Docker | Low overhead | Medium | Optional | Optional |
| OpenTelemetry | Low | Low/Medium | No | Optional |

---

# 195. SOFTWARE MATRIX AND COST

External services should eventually record:

```text
Free
Open Source
Self-hosted
Usage-based
Subscription
Enterprise
```

---

# 196. COST PRINCIPLE

Cost is a selection criterion but cannot override:

```text
Security
Reliability
Architecture Compatibility
License
```

---

# 197. SOFTWARE MATRIX AND PRIVACY

Each external software component must eventually classify:

```text
Local
Remote
Cloud
Data Transferred
Sensitive Data Risk
```

---

# 198. PRIVACY MATRIX

| Component | Local Capable | External Data Possible | Sensitive Data Risk |
|---|---:|---:|---|
| Python Core | Yes | Optional | High |
| PostgreSQL | Yes | Optional | High |
| Qdrant | Yes | Optional | High |
| Redis | Yes | Optional | Medium |
| Playwright | Yes | Yes | High |
| Cloud LLM | No | Yes | High |
| Local LLM | Yes | No | High |
| OpenTelemetry | Yes | Yes | Medium |
| MCP | Yes | Yes | High |

---

# 199. SOFTWARE MATRIX AND SECURITY

Security classification must be based on **capability**, not merely package reputation.

---

# 200. SUPPLY CHAIN

Every production dependency participates in the software supply chain.

Required controls:

```text
Source Verification
Version Pinning
Dependency Lock
Vulnerability Scanning
License Review
Artifact Verification
SBOM
```

---

# 201. DIRECT DEPENDENCIES

Direct dependencies are explicitly declared by JARVIS.

---

# 202. TRANSITIVE DEPENDENCIES

Transitive dependencies must be captured in the final lock/SBOM.

---

# 203. OPTIONAL DEPENDENCIES

Optional dependencies must not become mandatory through accidental imports.

---

# 204. DEVELOPMENT DEPENDENCIES

Development-only dependencies must be separated from production runtime dependencies.

---

# 205. TEST DEPENDENCIES

Test dependencies must be classified separately.

---

# 206. BUILD DEPENDENCIES

Build tooling must not automatically become runtime dependencies.

---

# 207. SOFTWARE CATEGORY MATRIX

| Category | Production | Development | Testing | Experimental |
|---|---:|---:|---:|---:|
| Python | Yes | Yes | Yes | Yes |
| TypeScript | Yes | Yes | Yes | Yes |
| FastAPI | Yes | Yes | Yes | Yes |
| LangGraph | Yes | Yes | Yes | Yes |
| Qdrant | Yes | Yes | Yes | Yes |
| PostgreSQL | Yes | Yes | Yes | Yes |
| Redis | Yes | Yes | Yes | Yes |
| Playwright | Yes | Yes | Yes | Yes |
| React | Yes | Yes | Yes | Yes |
| Docker | Yes | Yes | Yes | Yes |
| MCP | Conditional | Yes | Yes | Yes |
| Experimental MCP | No | Yes | Yes | Yes |

---

# 208. SOFTWARE MATRIX QUALITY GATE

Before Version Lock begins, every `APPROVED` component must have:

```text
Defined Role
Defined Layer
Defined Owner
Defined Status
Defined Security Class
Defined License Review
Defined Source
Defined Version Strategy
```

---

# 209. VERSION LOCK READINESS

A component is Version-Lock-ready when:

```text
Technology Selected
+
Source Identified
+
Version Candidate Identified
+
Compatibility Tested
+
License Checked
+
Security Checked
```

---

# 210. MANIFEST READINESS

A component is Manifest-ready when:

```text
Required/Optional status
+
Runtime requirements
+
Installation method
+
Configuration method
+
Health check
```

are known.

---

# 211. BOOTSTRAP READINESS

A component is Bootstrap-ready when:

```text
Installation source
+
Installation command/process
+
Version
+
Verification method
+
Failure handling
```

are known.

---

# 212. SYSTEM VERIFICATION READINESS

A component is Verification-ready when the system knows how to prove:

```text
Installed
Correct Version
Correct Configuration
Healthy
Compatible
```

---

# 213. COMPLIANCE READINESS

A component is Compliance-ready when its presence and version can be checked automatically.

---

# 214. MASTER READINESS TABLE

| Component | Matrix | Version Lock | Manifest | Bootstrap | Verification | Compliance |
|---|---:|---:|---:|---:|---:|---:|
| Python | ✓ | Pending | Pending | Pending | Pending | Pending |
| FastAPI | ✓ | Pending | Pending | Pending | Pending | Pending |
| LangGraph | ✓ | Pending | Pending | Pending | Pending | Pending |
| Qdrant | ✓ | Pending | Pending | Pending | Pending | Pending |
| PostgreSQL | ✓ | Pending | Pending | Pending | Pending | Pending |
| Redis | ✓ | Pending | Pending | Pending | Pending | Pending |
| Playwright | ✓ | Pending | Pending | Pending | Pending | Pending |
| React | ✓ | Pending | Pending | Pending | Pending | Pending |
| Vite | ✓ | Pending | Pending | Pending | Pending | Pending |
| Docker | ✓ | Pending | Pending | Pending | Pending | Pending |
| OpenTelemetry | ✓ | Pending | Pending | Pending | Pending | Pending |
| pytest | ✓ | Pending | Pending | Pending | Pending | Pending |
| uv | ✓ | Pending | Pending | Pending | Pending | Pending |
| MCP | ✓ | Pending | Pending | Pending | Pending | Pending |

---

# 215. CURRENT MATRIX STATUS

```text
============================================================
             APPROVED SOFTWARE MATRIX v1
============================================================

ARCHITECTURAL SELECTION
        COMPLETE

SOFTWARE ROLE MAPPING
        COMPLETE

PRIMARY STACK
        DEFINED

CONDITIONAL STACK
        DEFINED

EXPERIMENTAL STACK
        DEFINED

EXACT VERSIONS
        NOT YET LOCKED

ARTIFACT DIGESTS
        NOT YET LOCKED

MODEL REVISIONS
        NOT YET LOCKED

MCP SERVER REVISIONS
        NOT YET LOCKED

MANIFEST
        NOT YET CREATED

BOOTSTRAP
        NOT YET CREATED

COMPLIANCE CHECKER
        NOT YET CREATED

SYSTEM VERIFICATION
        NOT YET CREATED

============================================================
```

---

# 216. CRITICAL RULE

The matrix must never contain a technology that was not evaluated through the Approved Stack governance process.

---

# 217. CRITICAL RULE — NO DUPLICATION

If a technology decision changes, update the relevant domain document first.

Then update this matrix.

Correct:

```text
Domain Decision
      ↓
Software Matrix
```

Incorrect:

```text
Software Matrix
      ↓
Invent New Architecture
```

---

# 218. CRITICAL RULE — NO VERSION DRIFT

Once Version Lock exists, this document must not be used to silently change production versions.

Version changes must occur through Version Lock governance.

---

# 219. CRITICAL RULE — NO CODE-DRIVEN APPROVAL

A package does not become approved because developers already imported it.

The process remains:

```text
Evaluate
↓
Approve
↓
Matrix
↓
Version Lock
↓
Code
```

---

# 220. CRITICAL RULE — NO MODEL-DRIVEN APPROVAL

The JARVIS LLM must not be allowed to decide that a new package is safe to install.

---

# 221. CRITICAL RULE — NO AUTO-INSTALL

Production JARVIS must never install arbitrary software because an agent requested it.

---

# 222. CRITICAL RULE — SOFTWARE PROVENANCE

Every production dependency must have traceable provenance.

---

# 223. CRITICAL RULE — REPRODUCIBILITY

A clean environment must be able to reconstruct the approved software environment from:

```text
Software Matrix
+
Version Lock
+
Manifest
+
Bootstrap
```

---

# 224. CRITICAL RULE — OBSERVABILITY

Every critical runtime component must be observable.

---

# 225. CRITICAL RULE — SECURITY

Every component that can:

```text
Execute
Write
Communicate
Authenticate
Modify
```

must have explicit security classification.

---

# 226. CRITICAL RULE — REPLACEMENT

Every major external technology should have a documented replacement strategy where practical.

---

# 227. TECHNOLOGY LOCK-IN

The following layers should remain abstracted:

```text
LLM Provider
STT Provider
TTS Provider
Vision Provider
Object Storage Provider
MCP Server
Cloud Provider
Telemetry Backend
```

---

# 228. TECHNOLOGY THAT SHOULD NOT BE ABSTRACTED EXCESSIVELY

The following may remain relatively concrete:

```text
Python
FastAPI
Pydantic
PostgreSQL
Qdrant
Redis
Playwright
React
Docker
OpenTelemetry
```

because excessive abstraction would add complexity without meaningful portability benefit.

---

# 229. ARCHITECTURAL BALANCE

The goal is:

```text
Portable where valuable
Concrete where beneficial
Abstract where external dependency risk exists
```

---

# 230. JARVIS PRIMARY TECHNOLOGY MAP

```text
                         JARVIS
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
      CORE                INTERFACE          INFRASTRUCTURE
        │                   │                   │
     Python              React/TS            Docker
        │                   │                   │
    LangGraph             Vite             PostgreSQL
        │                                      Qdrant
        │                                      Redis
        │
   ┌────┼─────────┐
   │    │         │
 Memory Tools   Services
   │    │         │
Qdrant MCP     FastAPI
        │
        ├──────── Browser
        │          │
        │       Playwright
        │
        ├──────── Voice
        │
        ├──────── Vision
        │
        └──────── Plugins
```

---

# 231. FINAL SOFTWARE GOVERNANCE CHAIN

```text
Technology Candidate
        ↓
Research
        ↓
Comparison
        ↓
Evaluation
        ↓
Approved Stack Decision
        ↓
Software Matrix
        ↓
Version Selection
        ↓
Version Lock
        ↓
Manifest
        ↓
Bootstrap
        ↓
Compliance Checker
        ↓
System Verification
        ↓
Production
```

---

# 232. FINAL MASTER MATRIX — COMPACT VIEW

| ID | Software | Status | Primary Role | JAS Layer | Version Lock |
|---|---|---|---|---|---|
| SW-001 | Python | APPROVED | Core runtime | Core | Required |
| SW-002 | TypeScript | APPROVED | Frontend language | Frontend | Required |
| SW-003 | Rust | CONDITIONAL | Native/performance | Infrastructure | If used |
| SW-004 | C/C++ | CONDITIONAL | Native/GPU | Infrastructure | If used |
| SW-005 | FastAPI | APPROVED | Backend API | Backend | Required |
| SW-006 | Pydantic | APPROVED | Schemas/validation | Core/Backend | Required |
| SW-007 | LangGraph | APPROVED | Agent orchestration | Agents | Required |
| SW-008 | Qdrant | APPROVED | Vector memory | Memory | Required |
| SW-009 | PostgreSQL | APPROVED | Relational data | Data | Required |
| SW-010 | Redis | APPROVED | Cache/coordination | Infrastructure | Required/Optional by profile |
| SW-011 | Playwright | APPROVED | Browser automation | Browser | Required for browser profile |
| SW-012 | STT stack | APPROVED | Speech recognition | Voice | Profile dependent |
| SW-013 | Vision stack | APPROVED | Visual perception | Vision | Profile dependent |
| SW-014 | React | APPROVED | Frontend UI | Frontend | Required for full UI |
| SW-015 | Vite | APPROVED | Frontend build | Frontend | Required for React frontend |
| SW-016 | Plugin SDK | APPROVED | Extensions | Plugins | Required |
| SW-017 | MCP Client SDK | APPROVED | MCP integration | MCP | Required |
| SW-018 | MCP Servers | CONDITIONAL | External capabilities | MCP | Per-server |
| SW-019 | OS Security | APPROVED | Host security | Security | Required |
| SW-020 | Secret Management | APPROVED | Credential security | Security | Required |
| SW-021 | Docker | APPROVED | Containers | Deployment | Required/Recommended |
| SW-022 | OpenTelemetry | APPROVED | Observability | Observability | Required |
| SW-023 | pytest | APPROVED | Testing | QA | Development/CI |
| SW-024 | Playwright Testing | APPROVED | E2E | QA | Development/CI |
| SW-025 | Ruff | APPROVED | Code quality | QA | Development/CI |
| SW-026 | uv | APPROVED | Python dependency management | Build | Required |
| SW-027 | Node.js | APPROVED | JS tooling | Build | Required for frontend |
| SW-028 | JS package manager | CONDITIONAL | JS dependencies | Build | Required for frontend |
| SW-029 | Git | APPROVED | Source control | DevOps | Required |
| SW-030 | GitHub | CONDITIONAL | Remote development/CI | DevOps | Optional |
| SW-031 | OCI | APPROVED | Container artifact | Deployment | Required for container profile |
| SW-032 | Local model runtime | APPROVED | Local inference | AI | Profile dependent |
| SW-033 | Cloud model abstraction | APPROVED | Remote inference | AI | Profile dependent |
| SW-034 | SQLite | APPROVED | Embedded state | Data | Optional |
| SW-035 | Object storage | APPROVED | Binary artifacts | Data | Required for full artifact profile |
| SW-036 | Structured logging | APPROVED | Logs | Observability | Required |
| SW-037 | Metrics | APPROVED | Metrics | Observability | Required |
| SW-038 | Tracing | APPROVED | Traces | Observability | Required |
| SW-039 | Contract testing | APPROVED | Interface QA | Testing | Required |
| SW-040 | Dependency scanning | APPROVED | Supply-chain security | Security | Required |

---

# 233. FINAL DECISION

The JARVIS Software Matrix v1 establishes the approved technology inventory.

The primary stable stack is:

```text
Python
TypeScript
FastAPI
Pydantic
LangGraph
Qdrant
PostgreSQL
Redis
Playwright
React
Vite
MCP Client
Plugin SDK
Docker
OpenTelemetry
pytest
Ruff
uv
Node.js
Git
```

with additional conditional systems:

```text
Rust
C/C++
Cloud Model Providers
Voice Providers
Vision Providers
MCP Servers
GitHub
Docker Privileged Operations
Authenticated Browser Automation
Database Write Operations
```

---

# 234. FINAL ARCHITECTURAL INTERPRETATION

The Software Matrix does not mean:

> "These are the only technologies JARVIS will ever use."

It means:

> "These are the technologies that the current JAS v1 architecture has selected as its controlled baseline."

Future additions must pass through the governance process.

---

# 235. FUTURE TECHNOLOGY ADDITION

A new technology must follow:

```text
Candidate
   ↓
Research
   ↓
Comparison
   ↓
Security
   ↓
License
   ↓
Architecture Compatibility
   ↓
Bootstrap Compatibility
   ↓
Decision
   ↓
Software Matrix
```

---

# 236. FUTURE TECHNOLOGY REMOVAL

Removal follows:

```text
Problem
   ↓
Evidence
   ↓
Alternative
   ↓
Migration Plan
   ↓
Approval
   ↓
Version Lock Change
   ↓
Manifest Change
   ↓
Deployment
   ↓
Deprecation
   ↓
Removal
```

---

# 237. FINAL SOURCE OF TRUTH HIERARCHY

The complete architecture governance hierarchy is:

```text
                    JAS v1
                      │
                      ▼
              APPROVED STACK
                      │
                      ▼
           SOFTWARE MATRIX v1
                      │
                      ▼
               VERSION LOCK
                      │
                      ▼
                  MANIFEST
                      │
                      ▼
                 BOOTSTRAP
                      │
                      ▼
          COMPLIANCE CHECKER
                      │
                      ▼
           SYSTEM VERIFICATION
                      │
                      ▼
                 JARVIS CORE
```

---

# 238. FINAL RULE

> **The Software Matrix defines what software JARVIS is allowed to be built from. Version Lock will define exactly which immutable software versions JARVIS is built from.**

This distinction must remain intact throughout the entire project.

---

# 239. NEXT DOCUMENT

The next document in the Approved Stack sequence is:

```text
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

Its purpose will be to create the formal negative decision record:

```text
Candidate
   ↓
Evaluation
   ↓
Rejected
   ↓
Reason
   ↓
Evidence
   ↓
Alternative
```

This will prevent previously rejected technologies from being repeatedly reconsidered without new evidence.

---

# 240. APPROVED SOFTWARE MATRIX v1 — STATUS

```text
============================================================

JAS-AS-21
APPROVED SOFTWARE MATRIX v1

STATUS:
APPROVED

ARCHITECTURAL BASELINE:
DEFINED

PRIMARY TECHNOLOGIES:
DEFINED

CONDITIONAL TECHNOLOGIES:
DEFINED

EXPERIMENTAL TECHNOLOGIES:
DEFINED

SOFTWARE ROLES:
DEFINED

JAS LAYER MAPPING:
DEFINED

SECURITY CLASSIFICATION:
DEFINED

DEPENDENCY MODEL:
DEFINED

VERSION LOCK:
NEXT PHASE

MANIFEST:
FUTURE PHASE

BOOTSTRAP:
FUTURE PHASE

COMPLIANCE:
FUTURE PHASE

SYSTEM VERIFICATION:
FUTURE PHASE

============================================================
```

**END OF `21_APPROVED_SOFTWARE_MATRIX.md`**