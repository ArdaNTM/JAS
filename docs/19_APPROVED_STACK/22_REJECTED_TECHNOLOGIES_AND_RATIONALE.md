# 22 — REJECTED TECHNOLOGIES AND RATIONALE

**Document ID:** JAS-AS-22  
**Document:** `22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED NEGATIVE DECISION REGISTER  
**Primary Domain:** Technology Rejection, Alternative Analysis, Architectural Governance, Decision Traceability

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
21_APPROVED_SOFTWARE_MATRIX.md
```

**Feeds Into:**

```text
Technology Governance
Version Lock
Manifest
Bootstrap
Architecture Compliance Checker
Future Technology Re-evaluation
Migration Planning
Security Review
License Review
```

---

# 1. PURPOSE

This document records technologies that were evaluated and **not selected for the JAS v1 Approved Stack**.

Its purpose is to prevent repeated architectural reconsideration without new evidence.

The document answers:

```text
What was considered?
Why was it considered?
Why was it not selected?
What replaced it?
Under what conditions could it be reconsidered?
```

---

# 2. CORE PRINCIPLE

A rejected technology is not necessarily a bad technology.

The correct interpretation is:

```text
REJECTED FOR JAS v1
```

not:

```text
BAD TECHNOLOGY
```

A technology can be:

```text
Excellent
Popular
Production-proven
Well-maintained
```

and still be rejected because another technology fits JARVIS better.

---

# 3. REJECTION SCOPE

Every rejection in this document is scoped to:

```text
JAS v1
```

unless explicitly stated otherwise.

---

# 4. REJECTION STATES

The rejection register uses the following states:

```text
REJECTED
DEFERRED
NOT SELECTED
CONDITIONALLY EXCLUDED
SUPERSEDED
REPLACED
```

---

# 5. REJECTED

`REJECTED` means the technology is not permitted as part of the JAS v1 production baseline.

---

# 6. DEFERRED

`DEFERRED` means the technology may be reconsidered later, but is intentionally not part of the current baseline.

---

# 7. NOT SELECTED

`NOT SELECTED` means the technology was evaluated but another option was selected for the same architectural role.

---

# 8. CONDITIONALLY EXCLUDED

The technology may be used only if an explicit future architectural decision authorizes it.

---

# 9. SUPERSEDED

A previous technology or architectural direction has been superseded by a newer decision.

---

# 10. REPLACED

A technology has an explicitly selected alternative in the current architecture.

---

# 11. IMPORTANT DISTINCTION

The following are different:

```text
Rejected
```

and:

```text
Conditionally Approved
```

and:

```text
Experimental
```

A rejected technology cannot simply appear in production code.

An experimental technology can exist in a controlled research environment.

---

# 12. REJECTION AUTHORITY

The decision hierarchy is:

```text
JAS
 ↓
Approved Stack
 ↓
Software Matrix
 ↓
Rejected Technology Register
 ↓
Version Lock
```

---

# 13. REJECTION PROCESS

Every significant rejection should follow:

```text
Candidate
    ↓
Research
    ↓
Requirements Mapping
    ↓
Alternative Comparison
    ↓
Security Review
    ↓
License Review
    ↓
Operational Review
    ↓
JAS Compatibility
    ↓
Decision
    ↓
Rejected / Deferred / Selected
```

---

# 14. REJECTION CRITERIA

A technology may be rejected because of:

```text
Architecture mismatch
Excessive complexity
Poor abstraction boundary
Weak long-term fit
Operational overhead
Security concerns
License concerns
Poor Windows compatibility
Poor Linux compatibility
Poor cross-platform behavior
Dependency risk
API instability
Vendor lock-in
Insufficient ecosystem
Excessive ecosystem
Duplicated capability
Performance
Memory requirements
GPU requirements
Deployment complexity
Bootstrap complexity
Testing complexity
Observability limitations
Migration risk
```

---

# 15. NO POPULARITY-BASED REJECTION

Technologies are not rejected simply because:

```text
GitHub stars are low
Community is smaller
They are less trendy
```

---

# 16. NO POPULARITY-BASED APPROVAL

Likewise, technologies are not approved simply because:

```text
They are popular
Everyone uses them
An LLM recommends them
They have many GitHub stars
```

---

# 17. MASTER REJECTION MATRIX

| ID | Domain | Technology | Decision | Primary Reason | Selected Alternative |
|---|---|---|---|---|---|
| RJ-001 | Agent | AutoGen | REJECTED | Duplicate orchestration stack / migration direction | LangGraph |
| RJ-002 | Agent | CrewAI | REJECTED | Abstraction overlap / unnecessary framework duplication | LangGraph |
| RJ-003 | Agent | Semantic Kernel | REJECTED | Ecosystem abstraction mismatch for JAS core | LangGraph |
| RJ-004 | Agent | AutoGPT | REJECTED | Product/framework model mismatch | Custom Core + LangGraph |
| RJ-005 | Agent | LangChain Agents as primary runtime | REJECTED | Too broad as primary orchestration authority | LangGraph |
| RJ-006 | Vector DB | Milvus | NOT SELECTED | Operational overlap with Qdrant | Qdrant |
| RJ-007 | Vector DB | Weaviate | NOT SELECTED | Operational overlap with Qdrant | Qdrant |
| RJ-008 | Vector DB | Chroma | NOT SELECTED | Better suited to simpler/local use cases | Qdrant |
| RJ-009 | Vector DB | Pinecone | REJECTED | External managed dependency / vendor lock-in | Qdrant |
| RJ-010 | Vector DB | pgvector as primary vector DB | NOT SELECTED | Dedicated vector layer preferred | Qdrant |
| RJ-011 | Database | MongoDB | NOT SELECTED | Relational model preferred for authoritative state | PostgreSQL |
| RJ-012 | Database | MySQL | NOT SELECTED | PostgreSQL ecosystem fit | PostgreSQL |
| RJ-013 | Database | MariaDB | NOT SELECTED | PostgreSQL ecosystem fit | PostgreSQL |
| RJ-014 | Cache | Memcached | NOT SELECTED | Redis provides broader capability | Redis |
| RJ-015 | Browser | Selenium | NOT SELECTED | Playwright better fit for modern agent/browser workflows | Playwright |
| RJ-016 | Browser | Puppeteer | NOT SELECTED | Chromium-centric / narrower browser strategy | Playwright |
| RJ-017 | Browser | Browser-use as core browser runtime | REJECTED | Higher-level dependency should not own browser boundary | Playwright |
| RJ-018 | Frontend | Angular | NOT SELECTED | Higher framework complexity | React |
| RJ-019 | Frontend | Vue | NOT SELECTED | React ecosystem selected | React |
| RJ-020 | Frontend | Svelte/SvelteKit | NOT SELECTED | Ecosystem and architecture consistency | React |
| RJ-021 | Frontend | Next.js | NOT SELECTED | Full-stack coupling unnecessary for JAS frontend | React + Vite |
| RJ-022 | Desktop | Electron | NOT SELECTED | Chromium + Node embedding overhead | Web UI / future Tauri evaluation |
| RJ-023 | Desktop | Tauri | DEFERRED | Valuable but not required for v1 | Web UI |
| RJ-024 | Backend | Django | NOT SELECTED | Excess framework scope | FastAPI |
| RJ-025 | Backend | Flask | NOT SELECTED | Less suitable for typed modern API baseline | FastAPI |
| RJ-026 | Backend | Django REST Framework | NOT SELECTED | Django dependency not justified | FastAPI |
| RJ-027 | Backend | Express.js | NOT SELECTED | Python-first backend architecture | FastAPI |
| RJ-028 | Backend | NestJS | NOT SELECTED | Duplicate backend ecosystem | FastAPI |
| RJ-029 | Build | Poetry | NOT SELECTED | uv selected for project/package workflow | uv |
| RJ-030 | Build | Pipenv | NOT SELECTED | Redundant package/environment system | uv |
| RJ-031 | Build | pip-only workflow | REJECTED | Insufficient reproducibility as project standard | uv |
| RJ-032 | Build | Conda as primary environment manager | NOT SELECTED | Excess scope for general runtime | uv |
| RJ-033 | JS Build | Yarn | NOT SELECTED | Avoid multiple package manager choices | Selected JS package manager |
| RJ-034 | Container | Podman as primary runtime | NOT SELECTED | Docker baseline selected | Docker |
| RJ-035 | Orchestration | Kubernetes for initial deployment | DEFERRED | Excess operational complexity for v1 | Docker |
| RJ-036 | DevOps | Nomad | DEFERRED | Not required for initial scale | Docker |
| RJ-037 | Monitoring | Direct vendor SDKs as primary telemetry layer | REJECTED | Vendor lock-in | OpenTelemetry |
| RJ-038 | Monitoring | Prometheus client as sole telemetry abstraction | NOT SELECTED | OTel provides broader abstraction | OpenTelemetry |
| RJ-039 | Monitoring | Grafana as telemetry source | NOT SELECTED | Visualization is downstream | OpenTelemetry |
| RJ-040 | Logging | ELK as mandatory baseline | DEFERRED | Excess operational footprint | OpenTelemetry-based telemetry |
| RJ-041 | Logging | Fluentd as mandatory logging layer | DEFERRED | Not required for baseline | OpenTelemetry |
| RJ-042 | Security | Direct secret storage in `.env` as production mechanism | REJECTED | Credential exposure risk | Secret management layer |
| RJ-043 | Security | Hard-coded API keys | REJECTED | Unacceptable security practice | Secret management |
| RJ-044 | Security | Unrestricted shell tool | REJECTED | Excess privilege | Capability-controlled shell |
| RJ-045 | Security | Unrestricted filesystem tool | REJECTED | Excess privilege | Permission-controlled filesystem |
| RJ-046 | MCP | Arbitrary MCP servers | REJECTED | Supply-chain/security risk | Approved MCP registry |
| RJ-047 | MCP | Unreviewed remote MCP server | REJECTED | External trust boundary | Approved MCP server |
| RJ-048 | Model | Single-model architecture | REJECTED | Excess provider/model coupling | Model abstraction |
| RJ-049 | Model | Single cloud provider as mandatory backend | REJECTED | Vendor lock-in | Provider abstraction |
| RJ-050 | Architecture | LLM with direct OS access | REJECTED | Security boundary violation | Agent → Policy → Tool |
| RJ-051 | Architecture | Agent framework owning all JARVIS state | REJECTED | Core state must remain JAS-owned | JARVIS Core |
| RJ-052 | Architecture | Database as complete memory system | REJECTED | Memory is broader than storage | Memory Service |
| RJ-053 | Architecture | Vector DB as complete memory system | REJECTED | Retrieval ≠ memory governance | Memory Service |
| RJ-054 | Architecture | Microservices from day one | DEFERRED | Premature complexity | Modular monolith/service boundaries |
| RJ-055 | Architecture | Event bus as mandatory core dependency | DEFERRED | Not required initially | Internal event interfaces |
| RJ-056 | Architecture | Multiple agent frameworks simultaneously | REJECTED | Duplicate orchestration semantics | LangGraph |
| RJ-057 | Architecture | Multiple vector DBs simultaneously | REJECTED | Operational duplication | Qdrant |
| RJ-058 | Architecture | Multiple primary SQL databases | REJECTED | Data fragmentation | PostgreSQL |
| RJ-059 | Architecture | Frontend directly accessing databases | REJECTED | Security and boundary violation | Backend API |
| RJ-060 | Architecture | MCP replacing Plugin architecture | REJECTED | Different abstraction purposes | Plugins + MCP |
```

---

# 18. AGENT ORCHESTRATION REJECTIONS

Agent orchestration is one of the most important areas in this register.

JAS v1 selects:

```text
LangGraph
```

as the primary orchestration technology.

Therefore competing agent orchestration frameworks are not permitted to silently coexist as equal first-class runtimes.

---

# 19. RJ-001 — AUTOGEN

**Technology:**

```text
Microsoft AutoGen
```

**Decision:**

```text
REJECTED FOR JAS v1
```

**Replacement:**

```text
LangGraph
```

---

# 20. AUTOGEN — HISTORICAL STRENGTH

AutoGen pioneered important multi-agent patterns, including:

```text
Multi-agent conversation
GroupChat
Event-driven agent runtime
Agent collaboration
```

It is therefore considered a legitimate technology, not a low-quality candidate.

---

# 21. AUTOGEN — CURRENT ECOSYSTEM FACTOR

Microsoft's current documentation describes Microsoft Agent Framework as the evolution of concepts from AutoGen and Semantic Kernel and provides a migration path from AutoGen. citeturn0search11turn0search4

This reduces the strategic attractiveness of introducing AutoGen as a new foundational JAS dependency.

---

# 22. AUTOGEN — JAS REJECTION REASON

The primary reasons are:

```text
Existing LangGraph selection
+
Duplicate orchestration model
+
Additional dependency surface
+
Migration/technology direction uncertainty
+
Unnecessary framework competition inside Core
```

---

# 23. AUTOGEN — IMPORTANT

This decision does not mean:

```text
AutoGen is technically incapable.
```

It means:

```text
JAS already has an orchestration authority.
```

Introducing a second would weaken architectural clarity.

---

# 24. AUTOGEN RECONSIDERATION CONDITIONS

AutoGen could be reconsidered only if:

```text
LangGraph becomes unsuitable
OR
JAS architecture changes
OR
A demonstrated capability gap cannot be solved otherwise
```

---

# 25. RJ-002 — CREWAI

**Technology:**

```text
CrewAI
```

**Decision:**

```text
REJECTED FOR JAS v1
```

**Replacement:**

```text
LangGraph
```

---

# 26. CREWAI — STRENGTH

CrewAI provides a high-level framework for:

```text
Agents
Tasks
Crews
Multi-agent workflows
```

The abstraction is useful for rapid agent development.

---

# 27. CREWAI — REJECTION

The problem is not capability.

The problem is architectural overlap.

JARVIS already defines:

```text
Core
Agent Runtime
State
Planning
Tools
Memory
Policy
Execution
```

Adding another high-level agent framework would introduce:

```text
Framework state
+
JARVIS state
```

and potentially:

```text
Crew state
+
Graph state
+
Core state
```

---

# 28. CREWAI — JAS DECISION

JARVIS requires a more explicit orchestration boundary than introducing multiple opinionated agent frameworks.

Therefore:

```text
CrewAI
→ Rejected
```

---

# 29. RJ-003 — SEMANTIC KERNEL

**Technology:**

```text
Microsoft Semantic Kernel
```

**Decision:**

```text
REJECTED FOR JAS v1
```

**Replacement:**

```text
LangGraph
+
JARVIS Core abstractions
```

---

# 30. SEMANTIC KERNEL — STRENGTH

Semantic Kernel provides:

```text
Plugins
Memory
AI service integration
Agent functionality
Workflow concepts
```

It is therefore a legitimate enterprise-oriented candidate.

---

# 31. SEMANTIC KERNEL — REJECTION

JAS already defines:

```text
Plugin Architecture
Memory Architecture
Model Abstraction
Agent Orchestration
```

Using Semantic Kernel as another abstraction layer would duplicate several of these responsibilities.

---

# 32. MICROSOFT AGENT FRAMEWORK

Microsoft Agent Framework is a future technology worth monitoring.

The current Microsoft documentation describes it as a new foundation for agent applications and explicitly documents migration from AutoGen. citeturn0search4turn0search11

For JAS v1:

```text
Agent Framework
→ NOT SELECTED
```

It remains a candidate for future evaluation.

---

# 33. RJ-004 — AUTOGPT

**Technology:**

```text
AutoGPT
```

**Decision:**

```text
REJECTED
```

---

# 34. AUTOGPT — REASON

AutoGPT is not selected as the architectural foundation because JARVIS requires:

```text
Explicit Core
Explicit State
Explicit Permission Model
Explicit Tool Boundary
Explicit Agent Runtime
Explicit Memory
Explicit Observability
```

rather than delegating the overall system architecture to an autonomous agent product.

---

# 35. AUTOGPT — ARCHITECTURAL PRINCIPLE

JARVIS:

```text
owns the agent
```

rather than:

```text
being implemented as an agent product.
```

---

# 36. RJ-005 — LANGCHAIN AS PRIMARY AGENT RUNTIME

**Technology:**

```text
LangChain Agents
```

**Decision:**

```text
REJECTED AS PRIMARY ORCHESTRATION AUTHORITY
```

---

# 37. LANGCHAIN — IMPORTANT DISTINCTION

LangChain itself is not rejected from the ecosystem.

It may still be useful for:

```text
Model integrations
Utilities
Retrievers
Adapters
Experimental components
```

The rejected part is:

```text
LangChain Agent Runtime
```

as the primary JARVIS orchestration authority.

---

# 38. LANGCHAIN — REASON

JAS v1 already defines:

```text
LangGraph
```

as the stateful orchestration layer.

Introducing a second orchestration abstraction would create unnecessary overlap.

---

# 39. VECTOR DATABASE REJECTIONS

JAS v1 selects:

```text
Qdrant
```

as the dedicated vector retrieval infrastructure.

Qdrant is therefore the primary vector database.

---

# 40. RJ-006 — MILVUS

**Technology:**

```text
Milvus
```

**Decision:**

```text
NOT SELECTED FOR JAS v1
```

**Replacement:**

```text
Qdrant
```

---

# 41. MILVUS — STRENGTH

Milvus is a serious large-scale vector database with support for distributed deployments and current 3.x development. Its documentation describes use cases from local development to large-scale distributed systems. citeturn0search0turn0search21

Milvus 3.0 was officially released in July 2026, further demonstrating that it remains an active project. citeturn0search18

---

# 42. MILVUS — REJECTION

The rejection is architectural rather than capability-based.

JAS v1 does not require:

```text
Multiple vector infrastructure choices
```

The selected Qdrant deployment provides the required:

```text
Vector Search
Payloads
Filtering
Hybrid Retrieval
Memory Retrieval
```

capabilities.

---

# 43. MILVUS — OPERATIONAL COST

Introducing Milvus would create an additional:

```text
Deployment
Monitoring
Backup
Upgrade
Client SDK
Testing
Documentation
Bootstrap
Version Lock
```

surface.

---

# 44. MILVUS — DECISION

```text
Excellent technology
+
Not necessary for JAS v1
=
NOT SELECTED
```

---

# 45. MILVUS RECONSIDERATION

Milvus may be reconsidered if:

```text
JARVIS reaches very large vector scale
OR
Qdrant becomes a bottleneck
OR
Milvus provides a demonstrated capability gap
```

---

# 46. RJ-007 — WEAVIATE

**Technology:**

```text
Weaviate
```

**Decision:**

```text
NOT SELECTED FOR JAS v1
```

**Replacement:**

```text
Qdrant
```

---

# 47. WEAVIATE — STRENGTH

Weaviate is an AI-oriented open-source vector database supporting vector search and RAG workflows. Its current documentation includes local and cloud deployment paths. citeturn0search2

---

# 48. WEAVIATE — REJECTION

The same architectural principle applies:

```text
Qdrant already fills the dedicated vector database role.
```

Using both would create unnecessary infrastructure duplication.

---

# 49. RJ-008 — CHROMA

**Technology:**

```text
Chroma
```

**Decision:**

```text
NOT SELECTED FOR PRODUCTION BASELINE
```

**Replacement:**

```text
Qdrant
```

---

# 50. CHROMA — REASON

Chroma is attractive for:

```text
Rapid prototyping
Local experiments
Simple RAG
Developer workflows
```

but JARVIS requires a dedicated long-lived memory infrastructure baseline.

---

# 51. CHROMA — DECISION

Chroma may be used in isolated experiments.

It must not become the production memory backend without a new evaluation.

---

# 52. RJ-009 — PINECONE

**Technology:**

```text
Pinecone
```

**Decision:**

```text
REJECTED AS PRIMARY MEMORY INFRASTRUCTURE
```

**Replacement:**

```text
Qdrant
```

---

# 53. PINECONE — REASON

The primary concern is architectural dependency on a managed external service.

JARVIS explicitly aims to support:

```text
Local
Offline
Hybrid
Cloud
```

deployment models.

A cloud-only vector infrastructure would reduce this flexibility.

---

# 54. PINECONE — FUTURE

A future cloud deployment profile may evaluate managed vector services separately.

---

# 55. RJ-010 — PGVECTOR AS PRIMARY VECTOR SYSTEM

**Technology:**

```text
pgvector
```

**Decision:**

```text
NOT SELECTED AS PRIMARY VECTOR DATABASE
```

**Replacement:**

```text
Qdrant
```

---

# 56. PGVECTOR — REASON

pgvector is attractive because it integrates vector search into PostgreSQL.

However, JAS intentionally separates:

```text
Relational Data
```

from:

```text
Dedicated Vector Retrieval
```

for the primary architecture.

---

# 57. PGVECTOR — IMPORTANT

This is not a claim that pgvector is technically inadequate.

It is an architectural choice:

```text
PostgreSQL
→ authoritative relational state

Qdrant
→ dedicated vector retrieval
```

---

# 58. DATABASE REJECTIONS

JAS v1 selects:

```text
PostgreSQL
```

as the authoritative relational database.

---

# 59. RJ-011 — MONGODB

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
PostgreSQL
```

---

# 60. MONGODB — REASON

JARVIS contains significant structured state:

```text
Users
Tasks
Permissions
Configuration
Audit
Agent State
Relationships
Metadata
```

The relational model provides a strong foundation for these authoritative records.

---

# 61. MONGODB — NOT A PROHIBITED TOOL

MongoDB may be evaluated for a future specialized workload.

It is simply not the primary JARVIS database.

---

# 62. RJ-012 — MYSQL

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
PostgreSQL
```

---

# 63. MYSQL — REASON

MySQL is mature and production-proven.

The rejection is based on:

```text
PostgreSQL ecosystem fit
+
JAS decisions
+
Extension ecosystem
+
Data architecture
```

rather than basic reliability.

---

# 64. RJ-013 — MARIADB

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
PostgreSQL
```

---

# 65. MARIADB — REASON

Introducing MariaDB would provide another SQL ecosystem without a demonstrated JARVIS requirement.

---

# 66. RJ-014 — MEMCACHED

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
Redis
```

---

# 67. MEMCACHED — REASON

JARVIS requires more than simple key/value caching.

Redis provides a broader platform for:

```text
Cache
Ephemeral State
Coordination
Rate Limiting
Queues where appropriate
```

Therefore maintaining both is unnecessary for v1.

---

# 68. BROWSER REJECTIONS

JAS v1 selects:

```text
Playwright
```

as the browser automation baseline.

---

# 69. RJ-015 — SELENIUM

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
Playwright
```

---

# 70. SELENIUM — STRENGTH

Selenium is a mature and widely adopted browser automation ecosystem.

It remains relevant for:

```text
Legacy browser automation
Enterprise testing
WebDriver-based environments
```

---

# 71. SELENIUM — REASON

JARVIS requires modern browser automation features including:

```text
Browser contexts
Network interception
Modern browser lifecycle
Screenshots
Downloads
Uploads
Multi-browser execution
Async workflows
```

Playwright provides a more integrated fit for the JARVIS browser architecture.

---

# 72. SELENIUM — DECISION

```text
Strong technology
+
Wrong primary fit
=
NOT SELECTED
```

---

# 73. RJ-016 — PUPPETEER

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
Playwright
```

---

# 74. PUPPETEER — REASON

Puppeteer is a strong browser automation technology, particularly in the Chromium ecosystem.

However, JARVIS wants a browser layer that treats:

```text
Chromium
Firefox
WebKit
```

as first-class browser engines.

Playwright better matches that architecture.

---

# 75. RJ-017 — BROWSER-USE AS CORE BROWSER RUNTIME

**Decision:**

```text
REJECTED AS CORE BROWSER AUTOMATION LAYER
```

---

# 76. BROWSER-USE — REASON

Higher-level browser agent libraries may be useful.

However:

```text
JARVIS Browser Layer
```

must own the actual browser lifecycle.

The architecture is:

```text
Agent
 ↓
JARVIS Browser Service
 ↓
Playwright
 ↓
Browser
```

not:

```text
Agent
 ↓
Third-party Browser Agent
 ↓
Unknown browser abstraction
```

---

# 77. FRONTEND REJECTIONS

JAS v1 selects:

```text
React
+
TypeScript
+
Vite
```

---

# 78. RJ-018 — ANGULAR

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
React
```

---

# 79. ANGULAR — REASON

Angular is capable of building large enterprise applications.

However JARVIS requires:

```text
Flexible UI
Rapid iteration
Component ecosystem
Low frontend coupling
```

without adopting a larger full application framework than necessary.

---

# 80. RJ-019 — VUE

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
React
```

---

# 81. VUE — REASON

Vue is technically viable.

The decision is primarily ecosystem and architectural consistency.

The project has selected React/TypeScript for the frontend baseline.

---

# 82. RJ-020 — SVELTE / SVELTEKIT

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
React + Vite
```

---

# 83. SVELTE — REASON

Svelte is attractive for lightweight interfaces.

However JARVIS benefits more from the ecosystem and component availability around React.

---

# 84. RJ-021 — NEXT.JS

**Decision:**

```text
NOT SELECTED AS PRIMARY FRONTEND ARCHITECTURE
```

**Replacement:**

```text
React + Vite + FastAPI
```

---

# 85. NEXT.JS — REASON

Next.js combines:

```text
Frontend
+
Server
+
Routing
+
Rendering
+
Deployment conventions
```

JAS intentionally separates:

```text
Frontend
```

from:

```text
Backend
```

Therefore Next.js introduces full-stack coupling that is unnecessary for the current architecture.

---

# 86. DESKTOP APPLICATION REJECTIONS

---

# 87. RJ-022 — ELECTRON

**Decision:**

```text
NOT SELECTED FOR JAS v1
```

Electron embeds Chromium and Node.js into desktop applications, providing a cross-platform JavaScript desktop model. citeturn0search1

---

# 88. ELECTRON — REASON

Electron is technically viable.

However, a JARVIS desktop shell based on Electron would introduce:

```text
Chromium
+
Node.js
+
Desktop Shell
```

as another runtime surface.

JAS v1 prioritizes:

```text
Core
+
Backend
+
Web UI
```

first.

---

# 89. RJ-023 — TAURI

**Decision:**

```text
DEFERRED
```

Tauri remains an interesting future desktop shell candidate.

It is not rejected because of poor technical quality.

It is deferred because:

```text
Desktop Shell
```

is not required to validate the JARVIS core.

---

# 90. TAURI RECONSIDERATION

Tauri may be reconsidered after:

```text
Core
Backend
Frontend
Voice
Browser
Security
```

are stable.

---

# 91. BACKEND REJECTIONS

JAS v1 selects:

```text
FastAPI
+
Pydantic
```

---

# 92. RJ-024 — DJANGO

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
FastAPI
```

---

# 93. DJANGO — REASON

Django provides:

```text
ORM
Admin
Authentication
Routing
Templates
Forms
```

JARVIS already has separate architectural layers for:

```text
API
Database
Authentication
Frontend
Core
```

Therefore adopting Django would introduce unnecessary framework scope.

---

# 94. RJ-025 — FLASK

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
FastAPI
```

---

# 95. FLASK — REASON

Flask is highly flexible.

However the JARVIS backend requires:

```text
Typed schemas
Async support
Modern API design
Streaming
OpenAPI
Dependency injection patterns
```

FastAPI better aligns with the chosen architecture.

---

# 96. RJ-026 — DJANGO REST FRAMEWORK

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
FastAPI
```

---

# 97. DRF — REASON

Using DRF would first require Django.

The project does not have a sufficient reason to introduce:

```text
Django
+
DRF
```

when FastAPI already satisfies the backend requirements.

---

# 98. RJ-027 — EXPRESS.JS

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
FastAPI
```

---

# 99. EXPRESS — REASON

The project is intentionally Python-first for:

```text
AI
Agents
Models
Memory
Automation
Backend
Bootstrap
```

Adding Node.js as the primary backend runtime would create unnecessary dual-backend complexity.

---

# 100. RJ-028 — NESTJS

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
FastAPI
```

---

# 101. NESTJS — REASON

NestJS is a strong typed backend framework.

However:

```text
TypeScript backend
+
Python AI backend
```

would increase:

```text
Language boundaries
Deployment complexity
Dependency duplication
Testing complexity
```

without a demonstrated requirement.

---

# 102. BUILD TOOL REJECTIONS

JAS v1 selects:

```text
uv
```

for Python project/dependency management.

---

# 103. RJ-029 — POETRY

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
uv
```

---

# 104. POETRY — REASON

Poetry is a mature Python dependency/project-management solution.

The rejection is based on:

```text
JAS build-tool selection
+
Need for fast resolution
+
Environment management
+
Locking strategy
+
Bootstrap integration
```

---

# 105. RJ-030 — PIPENV

**Decision:**

```text
NOT SELECTED
```

**Replacement:**

```text
uv
```

---

# 106. PIPENV — REASON

Pipenv would introduce another dependency/environment management workflow without solving a requirement that uv does not already cover.

---

# 107. RJ-031 — PIP-ONLY WORKFLOW

**Decision:**

```text
REJECTED AS PROJECT STANDARD
```

---

# 108. PIP-ONLY — REASON

A production platform requires:

```text
Reproducibility
Locking
Environment Management
Dependency Resolution
Bootstrap Integration
```

A bare pip workflow is insufficient as the complete engineering standard.

---

# 109. RJ-032 — CONDA AS PRIMARY ENVIRONMENT SYSTEM

**Decision:**

```text
NOT SELECTED
```

---

# 110. CONDA — REASON

Conda is valuable for scientific/GPU environments.

However, JAS v1 requires a general-purpose application packaging baseline rather than making Conda the universal environment authority.

Conda may still be evaluated for specialized ML/GPU workflows.

---

# 111. RJ-033 — YARN

**Decision:**

```text
NOT SELECTED
```

---

# 112. YARN — REASON

The JARVIS project does not require multiple competing JavaScript package manager standards.

One package manager will be selected and locked.

---

# 113. CONTAINER RUNTIME REJECTIONS

---

# 114. RJ-034 — PODMAN AS PRIMARY RUNTIME

**Decision:**

```text
NOT SELECTED AS PRIMARY CONTAINER BASELINE
```

**Replacement:**

```text
Docker
```

---

# 115. PODMAN — REASON

Podman is a legitimate container technology.

The decision is primarily:

```text
Docker ecosystem
+
Documentation
+
Tooling
+
Bootstrap simplicity
+
Developer familiarity
```

---

# 116. PODMAN — FUTURE

Podman can be reconsidered for:

```text
Rootless deployments
Security-focused environments
Docker-compatible deployments
```

---

# 117. ORCHESTRATION REJECTIONS

---

# 118. RJ-035 — KUBERNETES FOR INITIAL DEPLOYMENT

**Decision:**

```text
DEFERRED
```

---

# 119. KUBERNETES — REASON

Kubernetes is designed for large-scale container orchestration.

However JAS v1 does not yet require:

```text
Large cluster
Multi-node orchestration
Complex autoscaling
Service mesh
Multi-region scheduling
```

Introducing Kubernetes immediately would increase:

```text
Operational complexity
Security surface
Bootstrap complexity
Monitoring complexity
Debugging complexity
```

---

# 120. KUBERNETES — NOT REJECTED FOREVER

Kubernetes becomes a candidate when:

```text
JARVIS scale
+
availability requirements
+
multi-node requirements
```

justify it.

---

# 121. RJ-036 — NOMAD

**Decision:**

```text
DEFERRED
```

---

# 122. NOMAD — REASON

Nomad may provide a simpler orchestration model than Kubernetes.

However JAS v1 does not require a cluster orchestrator.

---

# 123. OBSERVABILITY REJECTIONS

JAS v1 selects:

```text
OpenTelemetry
```

as the instrumentation and telemetry abstraction.

---

# 124. RJ-037 — DIRECT VENDOR SDKs AS PRIMARY TELEMETRY

**Decision:**

```text
REJECTED
```

---

# 125. DIRECT VENDOR SDK — REASON

Hard-coding:

```text
Vendor A SDK
```

into every service creates:

```text
Vendor lock-in
Migration cost
Code duplication
Inconsistent telemetry
```

---

# 126. SELECTED MODEL

```text
Application
 ↓
OpenTelemetry
 ↓
Exporter / Collector
 ↓
Chosen Backend
```

---

# 127. RJ-038 — PROMETHEUS CLIENT AS SOLE TELEMETRY ABSTRACTION

**Decision:**

```text
NOT SELECTED AS SOLE TELEMETRY STANDARD
```

---

# 128. PROMETHEUS — REASON

Metrics are only one part of JARVIS observability.

JARVIS also needs:

```text
Traces
Logs
Events
Agent Execution
Tool Execution
```

OpenTelemetry provides the broader instrumentation abstraction.

---

# 129. RJ-039 — GRAFANA AS TELEMETRY SOURCE

**Decision:**

```text
NOT SELECTED AS TELEMETRY AUTHORITY
```

---

# 130. GRAFANA — REASON

Grafana is primarily a visualization/observability interface.

JARVIS needs an instrumentation abstraction beneath the visualization layer.

---

# 131. RJ-040 — ELK AS MANDATORY BASELINE

**Decision:**

```text
DEFERRED
```

---

# 132. ELK — REASON

ELK may be valuable for large-scale logging.

However making it mandatory from day one introduces:

```text
Elasticsearch
Logstash
Kibana
```

and associated operational overhead.

---

# 133. ELK — FUTURE

ELK may be evaluated if:

```text
Log volume
Search requirements
Retention requirements
Enterprise deployment
```

justify it.

---

# 134. RJ-041 — FLUENTD AS MANDATORY LOGGING LAYER

**Decision:**

```text
DEFERRED
```

---

# 135. FLUENTD — REASON

The initial JARVIS telemetry architecture does not require a mandatory independent log collector layer.

---

# 136. SECURITY REJECTIONS

Security rejections are more absolute than normal technology choices.

---

# 137. RJ-042 — `.ENV` AS PRODUCTION SECRET STORE

**Decision:**

```text
REJECTED AS COMPLETE PRODUCTION SECRET MANAGEMENT
```

---

# 138. REASON

`.env` files may be useful for:

```text
Development
Local Configuration
Non-sensitive Parameters
```

but production secrets require stronger protection.

---

# 139. RJ-043 — HARDCODED API KEYS

**Decision:**

```text
ABSOLUTELY REJECTED
```

The following are prohibited:

```text
API keys in source
Passwords in source
Private keys in source
Tokens in Git
Secrets in frontend bundles
```

---

# 140. RJ-044 — UNRESTRICTED SHELL TOOL

**Decision:**

```text
REJECTED
```

---

# 141. SHELL SECURITY PRINCIPLE

JARVIS must not implement:

```text
LLM
 ↓
arbitrary shell
```

Instead:

```text
Agent
 ↓
Tool
 ↓
Policy
 ↓
Permission
 ↓
Sandbox
 ↓
Execution
```

---

# 142. RJ-045 — UNRESTRICTED FILESYSTEM TOOL

**Decision:**

```text
REJECTED
```

---

# 143. FILESYSTEM SECURITY

Filesystem access must be:

```text
Scoped
Audited
Permission-controlled
Path-restricted
Capability-based
```

---

# 144. MCP REJECTIONS

---

# 145. RJ-046 — ARBITRARY MCP SERVERS

**Decision:**

```text
REJECTED
```

---

# 146. MCP SECURITY REASON

MCP creates an external capability boundary.

An MCP server may potentially:

```text
Read
Write
Execute
Network
Access credentials
Modify external systems
```

Therefore:

```text
MCP server exists
```

does not mean:

```text
MCP server approved
```

---

# 147. RJ-047 — UNREVIEWED REMOTE MCP SERVER

**Decision:**

```text
REJECTED
```

---

# 148. MCP TRUST MODEL

```text
Discovery
 ↓
Evaluation
 ↓
Security Review
 ↓
License Review
 ↓
Capability Review
 ↓
Approval
 ↓
Version Lock
```

---

# 149. MCP REGISTRY ≠ APPROVAL

An MCP server being available through a registry does not automatically make it trusted.

---

# 150. MODEL ARCHITECTURE REJECTIONS

---

# 151. RJ-048 — SINGLE-MODEL ARCHITECTURE

**Decision:**

```text
REJECTED
```

---

# 152. SINGLE-MODEL REASON

JARVIS requires different model capabilities:

```text
Reasoning
Fast responses
Vision
Embedding
STT
TTS
Reranking
Specialized inference
```

A single model should not be treated as the entire AI system.

---

# 153. RJ-049 — SINGLE CLOUD PROVIDER AS MANDATORY BACKEND

**Decision:**

```text
REJECTED
```

---

# 154. CLOUD LOCK-IN REASON

The architecture must support:

```text
Local
Cloud
Hybrid
```

models.

Therefore:

```text
Provider Abstraction
```

is mandatory.

---

# 155. RJ-050 — LLM DIRECT OS ACCESS

**Decision:**

```text
ABSOLUTELY REJECTED
```

---

# 156. CORE SECURITY PRINCIPLE

The architecture must be:

```text
LLM
 ↓
Intent
 ↓
Agent
 ↓
Tool Selection
 ↓
Policy
 ↓
Permission
 ↓
Execution
```

not:

```text
LLM
 ↓
Operating System
```

---

# 157. RJ-051 — AGENT FRAMEWORK OWNING ALL JARVIS STATE

**Decision:**

```text
REJECTED
```

---

# 158. REASON

JARVIS Core must own authoritative state boundaries.

An agent framework may manage:

```text
Workflow State
Checkpoint State
```

but should not silently become the owner of:

```text
All Memory
All User State
All Permissions
All System State
```

---

# 159. MEMORY ARCHITECTURE REJECTIONS

---

# 160. RJ-052 — DATABASE AS COMPLETE MEMORY SYSTEM

**Decision:**

```text
REJECTED
```

---

# 161. REASON

Memory includes:

```text
Working Memory
Semantic Memory
Episodic Memory
Procedural Memory
Retention
Deletion
Provenance
Privacy
Retrieval
```

A database is infrastructure, not the entire memory architecture.

---

# 162. RJ-053 — VECTOR DATABASE AS COMPLETE MEMORY SYSTEM

**Decision:**

```text
REJECTED
```

---

# 163. REASON

Vector search solves:

```text
Semantic Retrieval
```

It does not automatically solve:

```text
Memory Governance
Memory Lifecycle
Privacy
Retention
Deletion
Provenance
Conflict Resolution
```

---

# 164. ARCHITECTURAL COMPLEXITY REJECTIONS

---

# 165. RJ-054 — MICROSERVICES FROM DAY ONE

**Decision:**

```text
DEFERRED
```

---

# 166. MICROSERVICES — REASON

JARVIS may eventually require multiple independently deployed services.

However starting with dozens of microservices creates:

```text
Network complexity
Deployment complexity
Debugging complexity
Distributed state
Authentication overhead
Observability overhead
```

before those costs are justified.

---

# 167. INITIAL ARCHITECTURE

The preferred initial approach is:

```text
Modular Core
+
Explicit Boundaries
+
Service-ready Interfaces
```

rather than:

```text
Everything is a microservice
```

---

# 168. RJ-055 — EVENT BUS AS MANDATORY CORE DEPENDENCY

**Decision:**

```text
DEFERRED
```

---

# 169. EVENT BUS — REASON

An event architecture may become important for:

```text
Distributed Agents
Long-running Jobs
High-scale Events
Service Decoupling
```

but it is not required for the first stable JARVIS core.

---

# 170. RJ-056 — MULTIPLE AGENT FRAMEWORKS SIMULTANEOUSLY

**Decision:**

```text
REJECTED
```

---

# 171. REASON

Using:

```text
LangGraph
+
AutoGen
+
CrewAI
+
Semantic Kernel
```

simultaneously would create:

```text
Multiple state models
Multiple tool abstractions
Multiple lifecycle models
Multiple observability models
Multiple failure semantics
```

---

# 172. JARVIS RULE

One primary orchestration authority.

Current:

```text
LangGraph
```

---

# 173. RJ-057 — MULTIPLE VECTOR DATABASES SIMULTANEOUSLY

**Decision:**

```text
REJECTED
```

---

# 174. REASON

Using:

```text
Qdrant
+
Milvus
+
Weaviate
```

without a proven requirement would create unnecessary:

```text
Infrastructure
Backup
Monitoring
Testing
Migration
Dependency
```

cost.

---

# 175. RJ-058 — MULTIPLE PRIMARY SQL DATABASES

**Decision:**

```text
REJECTED
```

---

# 176. REASON

The authoritative relational data layer should have one primary database.

Current:

```text
PostgreSQL
```

---

# 177. RJ-059 — FRONTEND DIRECT DATABASE ACCESS

**Decision:**

```text
REJECTED
```

---

# 178. REASON

The frontend must communicate through controlled APIs.

Correct:

```text
React
 ↓
Backend API
 ↓
Application Service
 ↓
Database
```

Incorrect:

```text
React
 ↓
PostgreSQL
```

---

# 179. RJ-060 — MCP REPLACING PLUGINS

**Decision:**

```text
REJECTED
```

---

# 180. REASON

Plugin and MCP systems solve different problems.

### Plugin

```text
JARVIS-native extension
```

### MCP

```text
External capability protocol
```

Therefore:

```text
Plugin ≠ MCP
```

---

# 181. PLUGIN / MCP ARCHITECTURE

```text
                 JARVIS
                    │
          ┌─────────┴─────────┐
          │                   │
       Plugins               MCP
          │                   │
   JARVIS-native        External protocol
   extensions           integrations
```

---

# 182. TECHNOLOGIES NOT REJECTED

The following should **not** be interpreted as rejected merely because they are not primary:

```text
Rust
C/C++
Microsoft Agent Framework
Milvus
Weaviate
Chroma
pgvector
Tauri
Kubernetes
Nomad
Podman
ELK
Prometheus
Grafana
Conda
```

Their current statuses are:

```text
Conditional
Deferred
Experimental
Not Selected
```

depending on the technology.

---

# 183. NOT SELECTED ≠ BAD

This distinction must be preserved throughout the project.

Example:

```text
Milvus
```

can be technically excellent and still:

```text
Not Selected
```

because:

```text
Qdrant
```

already fills the architectural role.

---

# 184. SUPERSEDED TECHNOLOGY

A technology may become rejected because a newer architectural decision supersedes it.

---

# 185. SUPERSESSION EXAMPLE

Conceptually:

```text
AutoGen
 ↓
Microsoft Agent Framework
```

does not automatically mean:

```text
Microsoft Agent Framework
 ↓
Approved
```

It means the ecosystem changed and must be reevaluated.

---

# 186. FUTURE TECHNOLOGY REEVALUATION

A rejected technology may return to consideration only when there is:

```text
New Evidence
+
New Requirement
+
Architecture Change
```

---

# 187. REEVALUATION TRIGGERS

Valid triggers include:

```text
Major new release
Critical capability added
Security improvement
License change
Performance breakthrough
JAS architecture change
Current technology deprecation
Current technology security failure
Scale requirement
New deployment requirement
```

---

# 188. INVALID REEVALUATION TRIGGERS

The following are not sufficient:

```text
"It is trending."
"Someone on YouTube recommended it."
"An LLM likes it."
"It has more GitHub stars."
"Everyone is using it."
```

---

# 189. REEVALUATION PROCESS

```text
Rejected Technology
        ↓
New Evidence
        ↓
Formal Re-evaluation
        ↓
Comparison With Current Choice
        ↓
Security / License Review
        ↓
Decision
```

---

# 190. REPLACEMENT TECHNOLOGY REQUIREMENT

A rejected technology can only replace an approved technology if the replacement demonstrates:

```text
Equal or better required capability
+
Acceptable security
+
Acceptable license
+
Migration feasibility
+
Operational benefit
```

---

# 191. MIGRATION REQUIREMENT

No production technology may be replaced without a migration plan.

---

# 192. MIGRATION PLAN

At minimum:

```text
Current System
New System
Compatibility Layer
Data Migration
Configuration Migration
Testing
Rollback
Deployment
Verification
```

---

# 193. SECURITY REJECTION PRIORITY

Security-related rejection has higher priority than:

```text
Performance
Cost
Developer Convenience
Popularity
```

---

# 194. LICENSE REJECTION PRIORITY

An incompatible license can independently prevent approval.

---

# 195. SUPPLY CHAIN REJECTION

A technology may be rejected if:

```text
Dependency provenance
```

cannot be sufficiently established.

---

# 196. BOOTSTRAP REJECTION

A technology may be rejected if its installation cannot be made reproducible enough for:

```text
Bootstrap
```

---

# 197. COMPLIANCE REJECTION

A technology may be rejected if the project cannot reliably detect:

```text
Installed Version
Runtime State
Configuration
```

during system verification.

---

# 198. OBSERVABILITY REJECTION

A production technology may be rejected if critical execution cannot be observed adequately.

---

# 199. TESTABILITY REJECTION

A technology may be rejected if its critical behavior cannot be tested reliably.

---

# 200. WINDOWS COMPATIBILITY

Because JARVIS development includes Windows environments, technologies with severe Windows compatibility problems require additional scrutiny.

---

# 201. CROSS-PLATFORM PRINCIPLE

Preferred baseline:

```text
Windows
Linux
macOS
```

where practical.

---

# 202. PLATFORM-SPECIFIC TECHNOLOGY

Platform-specific technologies are allowed when they are isolated behind a stable interface.

---

# 203. NATIVE TECHNOLOGY REJECTION PRINCIPLE

Native code is not rejected.

It is:

```text
Conditionally Approved
```

when it provides meaningful value.

---

# 204. SOFTWARE DUPLICATION PRINCIPLE

JARVIS should not maintain two technologies for the same role unless there is a documented reason.

---

# 205. EXAMPLE

Bad:

```text
PostgreSQL
+
MySQL
+
MongoDB
```

all as primary databases.

Good:

```text
PostgreSQL
```

with specialized storage where justified.

---

# 206. AGENT DUPLICATION

Bad:

```text
LangGraph
+
CrewAI
+
AutoGen
```

as equal core runtimes.

Good:

```text
LangGraph
```

as primary orchestration with future alternatives evaluated separately.

---

# 207. VECTOR DUPLICATION

Bad:

```text
Qdrant
+
Milvus
+
Weaviate
```

for the same memory workload.

Good:

```text
Qdrant
```

with alternative databases retained in this register.

---

# 208. BROWSER DUPLICATION

Bad:

```text
Selenium
+
Playwright
+
Puppeteer
```

as production browser authorities.

Good:

```text
Playwright
```

with alternative frameworks documented here.

---

# 209. BACKEND DUPLICATION

Bad:

```text
FastAPI
+
Django
+
Express
+
NestJS
```

for the same application backend.

Good:

```text
FastAPI
```

with other runtimes isolated to specific tools if future requirements justify them.

---

# 210. BUILD TOOL DUPLICATION

Bad:

```text
pip
+
Poetry
+
Pipenv
+
Conda
+
uv
```

as competing environment authorities.

Good:

```text
uv
```

with specialized tools introduced only when required.

---

# 211. REJECTED SOFTWARE AND EXPERIMENTAL SOFTWARE

Rejected:

```text
Not allowed in production baseline.
```

Experimental:

```text
Allowed only in controlled research.
```

---

# 212. EXPERIMENTAL TECHNOLOGY ESCAPE

Experimental code must not become production code merely because it already exists in the repository.

---

# 213. EXPERIMENTAL PROMOTION

Promotion requires:

```text
Evaluation
Security Review
License Review
Testing
Performance
Documentation
Matrix Update
Version Lock
```

---

# 214. REJECTION REGISTER MAINTENANCE

This document must be updated whenever:

```text
A technology is formally rejected
A technology changes status
A replacement changes
A major reconsideration occurs
```

---

# 215. REJECTION RECORD FORMAT

Future entries should use:

```text
Technology
ID
Domain
Decision
Date
Evaluation Scope
Strengths
Weaknesses
Reason
Replacement
Reconsideration Conditions
Evidence
```

---

# 216. DECISION TRACEABILITY

Every rejected technology should be traceable to:

```text
Approved Stack Domain Document
```

and, where appropriate:

```text
Research / Evaluation Record
```

---

# 217. NO ORPHAN DECISIONS

A rejected technology should not exist without a reason.

---

# 218. NO PERMANENT MEMORY LOSS

Rejected decisions are intentionally retained.

---

# 219. WHY RETAIN REJECTED TECHNOLOGIES?

Because future developers may ask:

```text
Why didn't we use X?
```

The answer should be:

```text
Because X was evaluated and rejected for documented reasons.
```

---

# 220. ANTI-REPETITION FUNCTION

This document prevents the project from repeatedly asking:

```text
Should we use Milvus?
```

when:

```text
Milvus
→ Already evaluated
→ Not selected
→ Qdrant selected
```

---

# 221. ANTI-HYPE FUNCTION

This document also protects against:

```text
New framework appears
↓
Developer sees it
↓
Entire architecture changes
```

---

# 222. ARCHITECTURE STABILITY

The default assumption is:

```text
Existing Decision
```

remains valid unless new evidence demonstrates otherwise.

---

# 223. BURDEN OF PROOF

The burden of proof belongs to the proposed replacement.

---

# 224. REPLACEMENT QUESTION

The question is not:

> "Is the new technology good?"

The question is:

> "Is the new technology sufficiently better for JARVIS to justify changing the existing architecture?"

---

# 225. TECHNOLOGY SWITCHING COST

Every replacement introduces:

```text
Migration
Testing
Documentation
Training
Bootstrap Changes
Version Lock Changes
Manifest Changes
Compliance Changes
Deployment Changes
```

---

# 226. SWITCHING THRESHOLD

A replacement should therefore provide meaningful value.

---

# 227. ARCHITECTURAL INERTIA

JARVIS intentionally prefers:

```text
Stable technology
```

over:

```text
Constantly changing technology
```

when the existing technology continues to meet requirements.

---

# 228. EXCEPTION

Security vulnerabilities or architectural failures may justify immediate replacement.

---

# 229. SECURITY EMERGENCY

Security-critical replacement may bypass normal release cadence but must still be documented.

---

# 230. REJECTION PRIORITY MATRIX

| Reason | Severity |
|---|---:|
| Security violation | Critical |
| License incompatibility | Critical |
| Architecture violation | Critical |
| Uncontrolled privilege | Critical |
| Reproducibility failure | High |
| Severe dependency instability | High |
| Operational complexity | Medium |
| Performance | Medium |
| Cost | Medium |
| Developer preference | Low |
| Popularity | Not a criterion |

---

# 231. CURRENT PRIMARY REPLACEMENT MAP

```text
AutoGen
    → LangGraph

CrewAI
    → LangGraph

Semantic Kernel
    → LangGraph + JARVIS Core

AutoGPT
    → JARVIS Core + LangGraph

Milvus
    → Qdrant

Weaviate
    → Qdrant

Chroma
    → Qdrant

Pinecone
    → Qdrant

pgvector as primary
    → Qdrant

MongoDB
    → PostgreSQL

MySQL
    → PostgreSQL

MariaDB
    → PostgreSQL

Memcached
    → Redis

Selenium
    → Playwright

Puppeteer
    → Playwright

Angular
    → React

Vue
    → React

Svelte
    → React

Next.js
    → React + Vite

Django
    → FastAPI

Flask
    → FastAPI

Express
    → FastAPI

NestJS
    → FastAPI

Poetry
    → uv

Pipenv
    → uv

pip-only
    → uv

Kubernetes
    → Docker for initial deployment

Vendor telemetry SDKs
    → OpenTelemetry
```

---

# 232. CURRENT DEFERRED TECHNOLOGIES

The following remain valid future candidates:

```text
Microsoft Agent Framework
Tauri
Kubernetes
Nomad
Podman
ELK
Prometheus-specific infrastructure
Grafana
Milvus
Weaviate
pgvector
```

They are not part of the JAS v1 baseline.

---

# 233. CURRENT EXPERIMENTAL TECHNOLOGIES

Experimental technologies must be listed separately from rejected technologies.

Current examples may include:

```text
Experimental MCP Servers
Experimental Model Runtimes
Alternative Agent Frameworks
Alternative Vision Models
Alternative Voice Engines
```

---

# 234. TECHNOLOGY WATCHLIST

The future technology watchlist should be maintained in:

```text
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

---

# 235. WATCHLIST ≠ APPROVAL

Being on the watchlist means:

```text
Observe
```

not:

```text
Use
```

---

# 236. REJECTION REGISTER AND VERSION LOCK

Version Lock must not contain rejected technologies.

---

# 237. REJECTION REGISTER AND MANIFEST

Manifest must not define rejected technologies as production dependencies.

---

# 238. REJECTION REGISTER AND BOOTSTRAP

Bootstrap must reject attempts to install a technology classified as:

```text
REJECTED
```

unless explicitly operating in a research environment that permits it.

---

# 239. REJECTION REGISTER AND COMPLIANCE

The Compliance Checker should detect rejected dependencies.

---

# 240. COMPLIANCE FAILURE

Example:

```text
requirements contain:
crewai
```

but the matrix says:

```text
CrewAI
→ REJECTED
```

Result:

```text
COMPLIANCE FAILED
```

---

# 241. DEVELOPMENT EXCEPTION

A developer may temporarily evaluate rejected software in an isolated branch or research environment.

That does not change its approval status.

---

# 242. RESEARCH ENVIRONMENT

Research environments should be:

```text
Isolated
Non-production
Non-authoritative
Non-deployable
```

---

# 243. PRODUCTION BOUNDARY

The production boundary is:

```text
APPROVED
+
CONDITIONALLY APPROVED under conditions
```

---

# 244. REJECTED TECHNOLOGY INSTALLATION

Production Bootstrap must not automatically install rejected technologies.

---

# 245. SOFTWARE SUPPLY CHAIN

Rejected technologies must not enter the production dependency graph through transitive dependencies without review.

---

# 246. TRANSITIVE REJECTION

If a rejected technology becomes a transitive dependency of an approved component, the situation must be evaluated.

---

# 247. TRANSITIVE DEPENDENCY EXCEPTION

A rejected package may exist transitively if:

```text
It is unavoidable
+
Security is acceptable
+
It is not directly used
+
It is documented
```

This does not make it approved as a direct dependency.

---

# 248. DIRECT VS TRANSITIVE

```text
Direct Dependency
→ Must be Approved

Transitive Dependency
→ Must be Audited
```

---

# 249. LICENSE REVIEW

A rejected technology may be rejected independently of technical quality because of licensing constraints.

---

# 250. SECURITY REVIEW

Security decisions may independently override performance or developer convenience.

---

# 251. ARCHITECTURAL REVIEW

Architecture remains the highest-level selection criterion after JAS requirements.

---

# 252. FINAL GOVERNANCE MODEL

```text
                  JAS v1
                    │
                    ▼
            Technology Candidate
                    │
          ┌─────────┴─────────┐
          │                   │
      Approved             Rejected
          │                   │
          ▼                   ▼
 Software Matrix       Rejection Register
          │
          ▼
    Version Lock
```

---

# 253. FINAL PRINCIPLE

> **A rejected technology is not forgotten. It is recorded so that the project can remember why it was rejected.**

---

# 254. FINAL PRINCIPLE — STABILITY

> **JARVIS does not change technologies because a newer technology exists. JARVIS changes technologies when evidence shows that the new technology provides sufficient architectural benefit to justify migration.**

---

# 255. FINAL PRINCIPLE — EVIDENCE

> **The existence of a newer or more popular framework is not evidence that JAS should change.**

---

# 256. FINAL PRINCIPLE — REPLACEMENT

> **A replacement must prove that it is better for JARVIS, not merely good in isolation.**

---

# 257. FINAL PRIMARY TECHNOLOGY DECISIONS

The following remain the current JAS v1 decisions:

```text
Agent Orchestration
→ LangGraph

Vector Database
→ Qdrant

Relational Database
→ PostgreSQL

Cache / Coordination
→ Redis

Browser Automation
→ Playwright

Backend
→ FastAPI

Frontend
→ React + TypeScript + Vite

Python Package Management
→ uv

Container Runtime
→ Docker

Observability Instrumentation
→ OpenTelemetry

Testing
→ pytest + Playwright

Source Control
→ Git
```

---

# 258. FINAL REJECTED PRIMARY ALTERNATIVES

```text
AutoGen
CrewAI
Semantic Kernel
AutoGPT
LangChain Agents as primary runtime

Milvus
Weaviate
Chroma
Pinecone as primary memory
pgvector as primary vector layer

MongoDB
MySQL
MariaDB

Memcached

Selenium
Puppeteer
Browser-use as core browser authority

Angular
Vue
Svelte
Next.js

Django
Flask
Django REST Framework
Express
NestJS

Poetry
Pipenv
pip-only workflow
Conda as universal environment authority

Podman as primary container baseline

Direct vendor telemetry SDKs

Unrestricted shell
Unrestricted filesystem
Hard-coded secrets
Arbitrary MCP servers
LLM direct OS access
```

---

# 259. FINAL DEFERRED ALTERNATIVES

```text
Microsoft Agent Framework
Tauri
Kubernetes
Nomad
ELK
Prometheus-specific infrastructure
Grafana-specific infrastructure
Milvus
Weaviate
pgvector
Podman
```

---

# 260. FUTURE RE-EVALUATION

The following condition automatically justifies reconsideration:

```text
Current approved technology
        ↓
Fails an important JARVIS requirement
        ↓
Alternative provides demonstrable solution
        ↓
Migration cost justified
```

---

# 261. NO AUTOMATIC RE-EVALUATION

The following does not automatically trigger reevaluation:

```text
New GitHub release
New framework
New benchmark
New social media trend
New LLM recommendation
```

---

# 262. RE-EVALUATION DOCUMENTATION

A future reevaluation must record:

```text
Current Technology
Candidate Technology
Problem
Evidence
Benchmark
Security
License
Migration
Operational Impact
Decision
```

---

# 263. FINAL STATUS

```text
============================================================

JAS-AS-22
REJECTED TECHNOLOGIES AND RATIONALE v1

STATUS:
APPROVED

PURPOSE:
NEGATIVE DECISION REGISTER

PRIMARY FUNCTION:
ARCHITECTURAL DECISION TRACEABILITY

REJECTED TECHNOLOGIES:
DOCUMENTED

DEFERRED TECHNOLOGIES:
DOCUMENTED

REPLACEMENTS:
DOCUMENTED

RE-EVALUATION POLICY:
DEFINED

VERSION LOCK IMPACT:
DEFINED

MANIFEST IMPACT:
DEFINED

BOOTSTRAP IMPACT:
DEFINED

COMPLIANCE IMPACT:
DEFINED

============================================================
```

---

# 264. RELATIONSHIP TO APPROVED SOFTWARE MATRIX

The relationship between documents `21` and `22` is:

```text
21_APPROVED_SOFTWARE_MATRIX.md
                │
                │
                ├── What JARVIS IS ALLOWED TO USE
                │
                ▼
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
                │
                │
                └── What JARVIS HAS DECIDED NOT TO USE
```

Together:

```text
APPROVED
+
REJECTED
```

create the initial technology decision boundary.

---

# 265. RELATIONSHIP TO VERSION LOCK

The next major phase will transform:

```text
Approved Technology
```

into:

```text
Exact Version
Exact Artifact
Exact Revision
Exact Digest
```

---

# 266. RELATIONSHIP TO MANIFEST

The Manifest will transform:

```text
Approved Software Inventory
```

into:

```text
Required Runtime Composition
```

---

# 267. RELATIONSHIP TO BOOTSTRAP

Bootstrap will transform:

```text
Manifest
+
Version Lock
```

into:

```text
Installed JARVIS Environment
```

---

# 268. RELATIONSHIP TO COMPLIANCE

The Compliance Checker will continuously compare:

```text
Actual System
```

against:

```text
JAS
+
Approved Matrix
+
Version Lock
+
Manifest
+
Rejected Register
```

---

# 269. FINAL ARCHITECTURAL CHAIN

```text
JAS
 │
 ▼
Approved Stack
 │
 ├───────────────┐
 ▼               ▼
Approved       Rejected
Matrix         Register
 │
 ▼
Version Lock
 │
 ▼
Manifest
 │
 ▼
Bootstrap
 │
 ▼
Compliance
 │
 ▼
Verification
 │
 ▼
JARVIS Core
```

---

# 270. FINAL RULE

> **No technology enters JARVIS merely because it works. It enters because it has been evaluated, approved, mapped to the architecture, version-locked, and made reproducible.**

---

# 271. END OF DOCUMENT

```text
============================================================

JAS-AS-22
REJECTED TECHNOLOGIES AND RATIONALE

VERSION:
1.0

STATUS:
APPROVED

NEXT DOCUMENT:
23_LICENSE_AND_COMPLIANCE.md

============================================================
```

**END OF `22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md`**