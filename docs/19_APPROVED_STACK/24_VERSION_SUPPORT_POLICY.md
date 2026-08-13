# 24 — VERSION SUPPORT POLICY

**Document ID:** JAS-AS-24  
**Document:** `24_VERSION_SUPPORT_POLICY.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED  
**Primary Domain:** Version Lifecycle, Support Policy, Upgrade Governance, Deprecation, End-of-Life, Compatibility, Maintenance

**Depends On:**

```text
JAS v1
00_APPROVED_STACK_OVERVIEW.md
01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md
18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md
19_APPROVED_MODELS.md
20_APPROVED_MCP_SERVERS.md
21_APPROVED_SOFTWARE_MATRIX.md
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
23_LICENSE_AND_COMPLIANCE.md
```

**Feeds Into:**

```text
Version Lock
Manifest
Bootstrap
Architecture Compliance Checker
System Verification
CI/CD
Dependency Management
Release Engineering
Security Management
Upgrade Planning
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

---

# 1. PURPOSE

This document defines how JARVIS manages the lifecycle of software, models, runtimes, services, APIs, MCP servers, plugins, containers, and other versioned components.

The objective is to prevent uncontrolled version drift.

The project must distinguish between:

```text
Available Version
Supported Version
Approved Version
Locked Version
Deprecated Version
End-of-Life Version
```

---

# 2. CORE PRINCIPLE

JARVIS must never equate:

```text
Latest
=
Best
```

or:

```text
Latest
=
Supported by JARVIS
```

or:

```text
Supported Upstream
=
Automatically Approved by JARVIS
```

---

# 3. VERSION GOVERNANCE

Version management follows:

```text
Research
↓
Evaluation
↓
Candidate
↓
Approved
↓
Supported
↓
Version Locked
↓
Maintained
↓
Deprecated
↓
Migration
↓
Removed
```

---

# 4. VERSION SUPPORT IS NOT VERSION LOCK

These documents have different responsibilities.

### Version Support Policy

Answers:

> Which versions may JARVIS use and for how long?

### Version Lock

Answers:

> Which exact versions does this release use?

Therefore:

```text
Version Support Policy
        ↓
Allowed Version Range
        ↓
Version Lock
        ↓
Exact Version
```

---

# 5. VERSION LOCK HAS HIGHER PRECISION

Example:

```text
Support Policy:

Python 3.13.x
Python 3.14.x
```

while:

```text
Version Lock:

Python 3.13.7
```

The first defines the supported policy.

The second defines the actual release.

---

# 6. WHY VERSION SUPPORT MATTERS

Without a support policy:

```text
Developer A
→ package version 1

Developer B
→ package version 2

CI
→ package version 3

Production
→ package version 1
```

can occur simultaneously.

This creates:

```text
Drift
Compatibility Problems
Security Problems
Reproducibility Problems
```

---

# 7. VERSION DRIFT

Version drift means the actual installed version differs from the intended supported/locked version.

JARVIS must detect version drift.

---

# 8. DRIFT TYPES

```text
Runtime Drift
Dependency Drift
Model Drift
Container Drift
Browser Drift
MCP Drift
Plugin Drift
API Drift
Infrastructure Drift
```

---

# 9. SUPPORT STATES

Every versioned component may have one of:

```text
CURRENT
SUPPORTED
MAINTENANCE
DEPRECATED
EOL
REJECTED
UNKNOWN
```

---

# 10. CURRENT

`CURRENT` means the version is an actively maintained upstream release line and is eligible for evaluation.

It does not automatically mean JARVIS uses it.

---

# 11. SUPPORTED

`SUPPORTED` means:

```text
Upstream Supported
+
JAS Compatible
+
Security Acceptable
+
Architecture Compatible
```

---

# 12. MAINTENANCE

`MAINTENANCE` means the version remains supported but is no longer preferred for new development.

---

# 13. DEPRECATED

`DEPRECATED` means:

> Existing deployments may continue temporarily, but new development must not depend on the version.

---

# 14. EOL

`EOL` means:

> The upstream project no longer provides normal support for the version.

EOL versions are prohibited from the production baseline unless an explicitly approved emergency exception exists.

---

# 15. UNKNOWN

`UNKNOWN` means insufficient information exists to establish support status.

Unknown versions cannot automatically enter production.

---

# 16. REJECTED

`REJECTED` means the version is explicitly prohibited.

---

# 17. JAS SUPPORT WINDOW

JARVIS should normally maintain:

```text
1 Preferred Version
+
1 Compatibility Version
```

for critical infrastructure where practical.

---

# 18. SUPPORT WINDOW OBJECTIVE

The objective is to avoid:

```text
Only One Supported Version
```

because that creates migration emergencies.

---

# 19. EXCESSIVE SUPPORT

JARVIS should also avoid supporting too many major versions simultaneously.

Example:

```text
Python 3.10
3.11
3.12
3.13
3.14
```

may create unnecessary testing and maintenance complexity.

---

# 20. SUPPORT WIDTH

Every component should define:

```text
Minimum Supported Version
Preferred Version
Maximum Tested Version
```

---

# 21. MINIMUM SUPPORTED VERSION

The oldest version JARVIS officially supports.

---

# 22. PREFERRED VERSION

The version recommended for new installations.

---

# 23. MAXIMUM TESTED VERSION

The newest version that has passed JARVIS validation.

---

# 24. FUTURE VERSION

A version newer than the maximum tested version is:

```text
UNVALIDATED
```

until tested.

---

# 25. VERSION RANGE

A component may therefore have:

```text
Supported:
3.13.x – 3.14.x

Preferred:
3.13.x

Maximum Tested:
3.14.x
```

---

# 26. SEMANTIC VERSIONING

Where upstream uses Semantic Versioning:

```text
MAJOR.MINOR.PATCH
```

JARVIS should preserve the distinction between:

```text
Breaking Change
Feature Change
Bug Fix
```

---

# 27. SEMVER IS NOT UNIVERSAL

Not every project follows SemVer reliably.

Therefore JARVIS must follow the upstream project's actual versioning policy.

---

# 28. UPSTREAM POLICY HAS PRIORITY

If a project uses:

```text
Year-based versions
Calendar versions
Major-only versions
Custom model revisions
Git commit hashes
```

JARVIS must adapt its version tracking accordingly.

---

# 29. VERSION IDENTIFIERS

Possible identifiers include:

```text
Semantic Version
Release Tag
Git Commit
Model Revision
Container Digest
Browser Revision
API Version
Schema Version
Protocol Version
```

---

# 30. EXACT ARTIFACT IDENTITY

For high-assurance components:

```text
Name
+
Version
+
Revision
+
Digest
```

should identify the artifact.

---

# 31. PATCH RELEASES

Patch releases are generally the lowest-risk upgrades.

They normally contain:

```text
Bug Fixes
Security Fixes
Small Corrections
```

but must still be tested.

---

# 32. MINOR RELEASES

Minor releases may introduce:

```text
New Features
New APIs
Behavior Changes
```

and require compatibility testing.

---

# 33. MAJOR RELEASES

Major releases may introduce breaking changes.

They require explicit upgrade evaluation.

---

# 34. SECURITY PATCHES

Security patches receive elevated priority.

A security patch should normally be evaluated ahead of feature upgrades.

---

# 35. CRITICAL SECURITY PATCH

If a critical vulnerability affects the locked version:

```text
Security Override
```

may bypass the normal upgrade cadence.

---

# 36. SECURITY-FIRST RULE

JARVIS prefers:

```text
Secure Supported Version
```

over:

```text
Older Stable Version
```

when the older version has an unresolved critical vulnerability.

---

# 37. SECURITY EXCEPTION

If an immediate upgrade is impossible:

```text
Temporary Exception
+
Mitigation
+
Deadline
```

must be created.

---

# 38. DEPENDENCY UPGRADE TYPES

Every upgrade should be classified:

```text
PATCH
MINOR
MAJOR
SECURITY
EMERGENCY
MODEL REVISION
INFRASTRUCTURE
```

---

# 39. PATCH UPGRADE POLICY

Patch upgrades should normally be eligible for routine maintenance.

---

# 40. PATCH TESTING

Patch upgrades should still execute:

```text
Unit Tests
Integration Tests
Smoke Tests
Critical E2E Tests
```

---

# 41. MINOR UPGRADE POLICY

Minor upgrades require:

```text
Compatibility Review
Regression Tests
Performance Review
```

for critical components.

---

# 42. MAJOR UPGRADE POLICY

Major upgrades require:

```text
Migration Plan
Architecture Review
Compatibility Review
Full Regression Testing
Rollback Plan
```

---

# 43. MODEL VERSION UPGRADES

AI models are not always governed by SemVer.

Therefore model upgrades should consider:

```text
Model ID
Revision
Weights
Tokenizer
Architecture
Context Length
Tool Calling
Structured Output
Behavior
License
Performance
```

---

# 44. MODEL BEHAVIOR VERSIONING

A model upgrade can change behavior without changing the API.

Therefore:

```text
API Compatible
≠
Behavior Compatible
```

---

# 45. MODEL REGRESSION

Model upgrades must evaluate:

```text
Reasoning
Tool Calling
Structured Output
Latency
Token Usage
Memory Usage
Safety
Instruction Following
Agent Reliability
```

---

# 46. MODEL VERSION LOCK

Production models must be version/revision locked.

---

# 47. MODEL `LATEST`

Production should not depend on an uncontrolled:

```text
latest
```

model alias.

---

# 48. MODEL ALIAS

If a provider offers:

```text
model-latest
```

JARVIS may use it only in:

```text
Experimental
Development
Canary
```

profiles unless explicitly validated.

---

# 49. PRODUCTION MODEL RULE

Production should use:

```text
Explicit Model ID
+
Explicit Revision
```

where the provider supports it.

---

# 50. MODEL LICENSE REVALIDATION

Every model upgrade triggers:

```text
License Review
Terms Review
```

because model terms may differ between releases.

---

# 51. MODEL PERFORMANCE REVALIDATION

Every major model upgrade requires benchmark comparison.

---

# 52. MODEL COST REVALIDATION

Cloud model changes must evaluate:

```text
Input Cost
Output Cost
Latency
Rate Limits
```

where applicable.

---

# 53. MODEL PROVIDER CHANGES

Changing providers is treated as:

```text
Architecture Change
+
Compliance Change
```

when data flow or terms change materially.

---

# 54. API VERSIONING

External APIs must be version-aware.

---

# 55. API DEPRECATION

If a provider announces:

```text
API v1
→ Deprecated
→ EOL
```

JARVIS must begin migration before the deadline.

---

# 56. API DEADLINE

The migration target should normally be:

```text
Before Upstream EOL
```

with an internal safety margin.

---

# 57. API SAFETY MARGIN

Recommended minimum:

```text
90 days
```

for major API migrations where practical.

---

# 58. CRITICAL API

For critical services:

```text
180+ days
```

of migration buffer is preferred where practical.

---

# 59. DATABASE VERSIONING

Databases are long-lived infrastructure.

They require explicit version policies.

---

# 60. POSTGRESQL POLICY

PostgreSQL releases a new major version approximately annually and supports each major version for five years. Its official policy recommends using the current minor release for the chosen major version. citeturn0search3

JARVIS therefore follows:

```text
Preferred:
Current supported PostgreSQL major

Required:
Latest supported minor within that major
```

---

# 61. POSTGRESQL MAJOR UPGRADE

A PostgreSQL major upgrade requires:

```text
Schema Test
Migration Test
Backup Verification
Restore Test
Performance Test
Application Compatibility Test
```

---

# 62. POSTGRESQL MINOR UPGRADE

Minor upgrades should be treated as routine maintenance, while still passing backup and regression checks.

---

# 63. DATABASE EOL

An EOL database version must not be used in production.

---

# 64. VECTOR DATABASE VERSIONING

Vector databases follow:

```text
Server Version
Client Version
Protocol/API Version
Index Format
```

---

# 65. VECTOR DATABASE COMPATIBILITY

The client and server combination must be tested together.

---

# 66. QDRANT

Qdrant version upgrades must evaluate:

```text
API Compatibility
Collection Compatibility
Index Compatibility
Persistence
Performance
Client Compatibility
```

---

# 67. CACHE VERSIONING

Cache systems must distinguish:

```text
Server Version
Client Library
Protocol
Persistence Format
```

---

# 68. REDIS

Redis upgrades require special review because:

```text
License
Server Version
Persistence
Protocol
Client
```

may change independently.

---

# 69. REDIS LICENSE RECHECK

Every Redis major upgrade must trigger the license review defined in:

```text
23_LICENSE_AND_COMPLIANCE.md
```

---

# 70. FRONTEND RUNTIME

Frontend runtime components include:

```text
Node.js
npm / pnpm
React
React DOM
Bundler
TypeScript
Browser Targets
```

---

# 71. NODE.JS POLICY

JARVIS prefers Node.js LTS lines for production.

As of August 2026, Node.js 24.x and 22.x are listed as LTS while 26.x is Current. Node.js 26 is scheduled to enter LTS in October 2026 under the current published schedule. citeturn0search12turn0search2

Therefore:

```text
Production:
LTS preferred

Development:
Current may be tested

Experimental:
Non-LTS may be evaluated
```

---

# 72. NODE.JS EOL

EOL Node.js releases are prohibited from production.

---

# 73. NODE.JS MAJOR UPGRADE

Node.js major upgrades require:

```text
Build
Test
Dependency Resolution
Native Module Test
Frontend Build
Backend Integration
```

---

# 74. REACT POLICY

React stable releases follow SemVer-style major/minor/patch versioning. React also maintains Canary and Experimental channels; Canary versions can include breaking changes and should be pinned when used. citeturn0search0

JARVIS production uses:

```text
Stable React
```

and not:

```text
Experimental React
```

---

# 75. REACT CANARY

Canary may be used only for:

```text
Research
Prototype
Compatibility Evaluation
```

unless explicitly approved.

---

# 76. REACT EXPERIMENTAL

Experimental React is not part of the production baseline.

---

# 77. TYPESCRIPT

TypeScript versions must be compatible with:

```text
Node.js
React
Build Toolchain
Type Definitions
```

---

# 78. FRONTEND TOOLCHAIN

Frontend upgrades must test:

```text
Build
Development Server
Production Bundle
SSR/CSR behavior where applicable
Browser Compatibility
```

---

# 79. BROWSER VERSIONING

Browser automation is especially sensitive to version changes.

---

# 80. PLAYWRIGHT VERSION POLICY

Playwright updates its supported browser versions with releases. Each Playwright release expects specific browser binaries. citeturn0search5

Therefore:

```text
Playwright Version
↔
Browser Revision
```

must be treated as a coupled dependency.

---

# 81. PLAYWRIGHT UPGRADE

A Playwright upgrade requires:

```text
Library Upgrade
+
Browser Installation
+
Browser Regression Tests
```

---

# 82. PLAYWRIGHT BROWSER DRIFT

A browser binary that differs from the Playwright-tested browser revision is considered drift.

---

# 83. BROWSER PINNING

Production browser automation should use the browser versions associated with the locked Playwright release.

---

# 84. BROWSER SECURITY

Browser security updates may require accelerated upgrades.

---

# 85. CHROMIUM

Chromium upgrades should be evaluated for:

```text
Automation Compatibility
Security
Extensions
Headless Behavior
CDP Compatibility
```

---

# 86. FIREFOX

Firefox upgrades should be evaluated for:

```text
Web Compatibility
Automation
Protocol Changes
```

---

# 87. WEBKIT

WebKit upgrades should be evaluated independently.

---

# 88. DOCKER VERSIONING

Docker Engine has stable and test channels. Docker documents patch releases as backward compatible within their major/minor version. citeturn0search4

JARVIS production uses:

```text
Stable
```

rather than:

```text
Test
```

unless explicitly approved.

---

# 89. DOCKER TEST CHANNEL

Docker test releases may be used for:

```text
Experimental
CI Compatibility
Future Migration Testing
```

---

# 90. DOCKER DESKTOP

Docker Desktop and Docker Engine must be treated as separate versioned components.

---

# 91. CONTAINER BASE IMAGE

Base images must be version pinned.

Avoid:

```text
ubuntu:latest
python:latest
node:latest
```

in production.

---

# 92. CONTAINER DIGEST

Production images should preferably be pinned by digest.

---

# 93. BASE IMAGE UPDATES

Base image updates require:

```text
Security Scan
Dependency Scan
Application Tests
```

---

# 94. KUBERNETES

Kubernetes maintains release branches for the three most recent minor versions. citeturn0search13

Therefore JARVIS Kubernetes deployments should remain within the upstream supported window.

---

# 95. KUBERNETES VERSION POLICY

Production Kubernetes:

```text
Supported Upstream
+
JAS Tested
```

only.

---

# 96. KUBERNETES VERSION SKEW

Kubernetes component version skew must follow the official compatibility policy rather than arbitrary version combinations. citeturn0search13

---

# 97. KUBERNETES UPGRADE

Requires:

```text
Control Plane Test
Node Test
Ingress Test
Storage Test
Networking Test
JARVIS Service Test
```

---

# 98. PYTHON POLICY

Python is the primary JARVIS application runtime unless JAS is later revised.

---

# 99. PYTHON SUPPORT

JARVIS should prefer actively supported Python release lines.

---

# 100. PYTHON MAJOR/MINOR

Python compatibility must be tested at the minor-release level:

```text
3.x
```

because Python's standard-library and packaging behavior can differ between minor versions.

---

# 101. PYTHON PATCH

Patch updates should generally be routine maintenance after regression testing.

---

# 102. PYTHON EOL

EOL Python versions are prohibited from production.

---

# 103. PYTHON NATIVE EXTENSIONS

Python upgrades must test:

```text
PyTorch
CUDA bindings
OpenCV
NumPy
Compiled Extensions
```

where applicable.

---

# 104. GPU RUNTIME VERSIONING

GPU software has multiple coupled layers:

```text
GPU Driver
CUDA
CUDA Toolkit
PyTorch
Tensor Libraries
Model Runtime
```

---

# 105. CUDA POLICY

CUDA compatibility must be evaluated as a stack rather than a single version.

---

# 106. DRIVER COMPATIBILITY

GPU driver versions must satisfy the selected CUDA/runtime requirements.

---

# 107. PYTORCH

PyTorch upgrades require:

```text
Python Compatibility
CUDA Compatibility
GPU Architecture Compatibility
Model Compatibility
Performance Validation
```

---

# 108. TORCHVISION

TorchVision versions should be kept compatible with the selected PyTorch release.

---

# 109. NUMPY

NumPy upgrades can affect:

```text
SciPy
PyTorch
OpenCV
Pandas
Native Extensions
```

and therefore require integration testing.

---

# 110. OPENCV

OpenCV upgrades require:

```text
Vision Regression
Camera Test
Video Test
Codec Test
```

---

# 111. LLM FRAMEWORKS

LLM frameworks are high-change components.

Examples include:

```text
Inference Frameworks
Agent Frameworks
Tool Calling Libraries
Structured Output Libraries
```

---

# 112. LLM FRAMEWORK SUPPORT

For rapidly changing AI frameworks:

```text
Preferred
+
Previous Compatible
```

should be maintained where feasible.

---

# 113. AI FRAMEWORK MAJOR UPGRADES

Major upgrades require:

```text
Agent Regression
Tool Regression
Memory Regression
Streaming Regression
Structured Output Regression
```

---

# 114. AGENT FRAMEWORKS

Agent frameworks require behavioral rather than only API testing.

---

# 115. AGENT BEHAVIOR VERSIONING

An agent framework upgrade can change:

```text
Planning
Retries
Tool Calling
State
Checkpointing
Concurrency
```

without breaking imports.

Therefore API compatibility alone is insufficient.

---

# 116. MEMORY FRAMEWORKS

Memory libraries must be evaluated for:

```text
Serialization
Retrieval
Persistence
Metadata
Migration
```

---

# 117. VECTOR INDEX FORMAT

If a vector database changes its index format:

```text
Migration
Backup
Rollback
```

must be validated.

---

# 118. DATABASE MIGRATIONS

Every schema-changing upgrade must have:

```text
Forward Migration
Rollback / Recovery Strategy
Backup
Verification
```

---

# 119. API SCHEMA VERSIONING

Internal APIs should use explicit schemas.

---

# 120. BACKEND API

JARVIS backend APIs should distinguish:

```text
v1
v2
```

where breaking changes are required.

---

# 121. API DEPRECATION

Deprecated API endpoints must have:

```text
Deprecation Date
Replacement
Removal Target
```

---

# 122. INTERNAL API POLICY

Internal APIs can evolve faster than public APIs but must still maintain compatibility across deployed services.

---

# 123. EVENT SCHEMA VERSIONING

Event schemas must be versioned when compatibility requires it.

---

# 124. MESSAGE VERSIONING

Messages between services should contain enough information to determine schema compatibility.

---

# 125. DATABASE SCHEMA VERSION

Database schemas should have migration versions.

---

# 126. CONFIGURATION VERSION

Configuration formats should be versioned.

---

# 127. MANIFEST VERSION

Manifest schema itself must be versioned.

---

# 128. BOOTSTRAP VERSION

Bootstrap must know which Manifest schema it supports.

---

# 129. BOOTSTRAP COMPATIBILITY

Conceptually:

```text
Bootstrap v2
supports
Manifest v1
Manifest v2
```

only when explicitly tested.

---

# 130. BOOTSTRAP MIGRATION

If the Manifest schema changes incompatibly:

```text
Migration
```

must be provided.

---

# 131. COMPLIANCE CHECKER VERSION

The Architecture Compliance Checker must understand the JAS version against which it validates.

---

# 132. JAS VERSION

JAS itself uses:

```text
Major
Minor
Patch
```

versioning for specification revisions.

---

# 133. JAS MAJOR REVISION

A major JAS revision may introduce breaking architectural changes.

---

# 134. JAS MINOR REVISION

A minor JAS revision may add compatible architectural capabilities.

---

# 135. JAS PATCH REVISION

A patch revision corrects errors without changing architectural intent.

---

# 136. JAS REVISION IMPACT

Any JAS revision must evaluate impact on:

```text
Approved Stack
Version Lock
Manifest
Bootstrap
Compliance Checker
Core
```

---

# 137. DEPRECATION POLICY

Deprecation should be deliberate.

---

# 138. DEPRECATION REASONS

A component may be deprecated because of:

```text
Upstream EOL
Security
Performance
Architecture
License
Maintenance
Better Replacement
Compatibility
Vendor Risk
```

---

# 139. DEPRECATION NOTICE

Every deprecated component should record:

```text
Component
Version
Reason
Date
Replacement
Migration Path
Removal Target
```

---

# 140. DEPRECATION PERIOD

Critical components should normally receive a migration window.

---

# 141. MINIMUM MIGRATION WINDOW

Recommended default:

```text
90 days
```

for non-emergency deprecations.

---

# 142. CRITICAL INFRASTRUCTURE

For critical infrastructure:

```text
180 days
```

or more is preferred where practical.

---

# 143. SECURITY DEPRECATION

Security-driven deprecations may have shorter timelines.

---

# 144. EOL POLICY

EOL versions must not be introduced into new production deployments.

---

# 145. EXISTING EOL DEPLOYMENTS

An existing deployment reaching EOL enters:

```text
MIGRATION REQUIRED
```

state.

---

# 146. EOL EXCEPTION

An EOL exception must include:

```text
Reason
Risk
Mitigation
Migration Plan
Deadline
Owner
```

---

# 147. EOL MAXIMUM

EOL exceptions should be temporary.

---

# 148. NO INDEFINITE EOL

There must be no permanent:

```text
"temporary"
```

EOL exception.

---

# 149. SUPPORT MATRIX

The Approved Software Matrix should contain:

```text
Component
Current Version
Supported Range
Preferred Version
EOL Date
JAS Status
```

where applicable.

---

# 150. VERSION SUPPORT RECORD

Conceptually:

```text
Component:
Python

Preferred:
3.x

Supported:
3.x / selected minors

Minimum:
X

Maximum Tested:
Y

Status:
SUPPORTED

Review:
YYYY-MM-DD
```

---

# 151. SUPPORT MATRIX STATES

```text
CURRENT
SUPPORTED
MAINTENANCE
DEPRECATED
EOL
UNKNOWN
```

---

# 152. SUPPORT DATE TYPES

Track:

```text
Upstream Release Date
Upstream Support Start
Upstream Maintenance Start
Upstream EOL
JAS Review Date
JAS Deprecation Date
JAS Removal Date
```

---

# 153. UPSTREAM EOL

The upstream EOL date is the most important external lifecycle boundary.

---

# 154. JAS EOL

JARVIS may choose an earlier internal EOL.

It should not normally choose a later production-support date without an explicit exception.

---

# 155. JAS SUPPORT END

```text
JAS Support End
≤
Upstream Support End
```

is the default policy.

---

# 156. EXCEPTION

A later date requires explicit risk acceptance.

---

# 157. SECURITY SUPPORT

Security support has higher priority than feature support.

---

# 158. SECURITY FIX AVAILABILITY

If upstream no longer provides security fixes, JARVIS should migrate.

---

# 159. BACKPORTS

JARVIS may maintain internal patches where necessary, but this increases maintenance responsibility.

---

# 160. INTERNAL FORK

An internal fork requires:

```text
Owner
Patch Process
Security Monitoring
Build Process
License Compliance
Release Process
```

---

# 161. FORK POLICY

Forking is a last-resort strategy, not a normal support mechanism.

---

# 162. VENDOR SUPPORT

Commercial support can extend operational support but does not automatically change upstream open-source EOL.

---

# 163. COMMERCIAL SUPPORT

If a vendor provides extended support:

```text
Vendor Support
```

may be recorded separately from:

```text
Upstream Support
```

---

# 164. EXTENDED SUPPORT

Extended support is acceptable only when:

```text
Security
License
Cost
Availability
```

are acceptable.

---

# 165. VERSION REVIEW CADENCE

Every production dependency should be reviewed periodically.

---

# 166. CRITICAL COMPONENT REVIEW

Critical infrastructure:

```text
Monthly
```

review preferred.

---

# 167. NORMAL COMPONENT REVIEW

Normal dependencies:

```text
Quarterly
```

review preferred.

---

# 168. LOW-RISK COMPONENTS

Low-risk components may be reviewed:

```text
Semi-annually
```

where appropriate.

---

# 169. MODEL REVIEW

Models should be reviewed more frequently because model ecosystems change rapidly.

---

# 170. SECURITY REVIEW

Security advisories may trigger immediate review regardless of scheduled cadence.

---

# 171. VERSION WATCH

The project should monitor:

```text
New Releases
Security Advisories
Deprecations
EOL Notices
License Changes
Breaking Changes
```

---

# 172. UPGRADE CANDIDATE

A new version should first become:

```text
UPGRADE CANDIDATE
```

rather than immediately replacing production.

---

# 173. CANDIDATE TESTING

Candidate testing should include:

```text
Build
Unit
Integration
System
Performance
Security
Compatibility
```

where appropriate.

---

# 174. CANARY

A candidate may be deployed to:

```text
Canary
```

before full production adoption.

---

# 175. CANARY REQUIREMENTS

Canary versions must have:

```text
Rollback
Observability
Comparison
Failure Detection
```

---

# 176. ROLLBACK

Every major upgrade must have a rollback or recovery strategy.

---

# 177. DATABASE ROLLBACK

Database migrations may not always support direct rollback.

Therefore:

```text
Backup
Restore
Forward Recovery
```

must be considered.

---

# 178. MODEL ROLLBACK

Model versions should remain available during migration.

---

# 179. CONTAINER ROLLBACK

Previous production image digests must remain retrievable.

---

# 180. FRONTEND ROLLBACK

Previous frontend artifacts should remain deployable.

---

# 181. BACKEND ROLLBACK

Backend releases must remain reproducible.

---

# 182. VERSION PINNING

Critical components must be pinned.

---

# 183. RANGES

Broad version ranges should be avoided for production-critical dependencies.

---

# 184. EXAMPLE

Avoid:

```text
package >= 1.0
```

when exact reproducibility is required.

Prefer:

```text
Version Lock
→ exact version
```

---

# 185. LOCKFILES

Package manager lockfiles are required where supported.

---

# 186. LOCKFILE POLICY

Lockfiles must be committed for production applications unless the architecture explicitly requires another mechanism.

---

# 187. TRANSITIVE DEPENDENCY DRIFT

Lockfiles should prevent uncontrolled transitive dependency updates.

---

# 188. DEPENDENCY UPDATE

Updating a lockfile is treated as a version change.

---

# 189. AUTOMATED UPDATES

Automated dependency update systems may create pull requests.

They must not automatically merge critical production upgrades without required validation.

---

# 190. SECURITY AUTOMATION

Security patch automation may receive accelerated treatment.

---

# 191. MAJOR VERSION AUTOMATION

Major upgrades should never be silently merged.

---

# 192. MINOR VERSION AUTOMATION

Minor upgrades may be automated only for low-risk components with strong test coverage.

---

# 193. PATCH VERSION AUTOMATION

Patch upgrades may be automated for approved components when CI coverage is sufficient.

---

# 194. MODEL AUTOMATION

Automatic model upgrades are prohibited for production unless explicitly approved.

---

# 195. API AUTOMATION

Automatic external API version changes are prohibited for production-critical integrations.

---

# 196. CONTAINER AUTOMATION

Automatic base-image updates require security and application testing.

---

# 197. VERSION COMPATIBILITY MATRIX

For tightly coupled systems:

```text
Python
PyTorch
CUDA
Driver
OpenCV
NumPy
```

must have a compatibility matrix.

---

# 198. MATRIX EXAMPLE

```text
Runtime
   ↓
Framework
   ↓
Native Runtime
   ↓
GPU
   ↓
Model
```

---

# 199. COMPATIBILITY FIRST

A newer version should not be approved if it breaks the compatibility matrix.

---

# 200. SUPPORT POLICY FOR COUPLED STACKS

A coupled stack is upgraded as a unit where necessary.

---

# 201. BROWSER COUPLING

```text
Playwright
+
Browser Revision
```

is one such coupled stack.

---

# 202. GPU COUPLING

```text
Driver
+
CUDA
+
PyTorch
```

is another.

---

# 203. DATABASE COUPLING

```text
Database Server
+
Client
+
ORM
+
Migration Tool
```

may form another coupled stack.

---

# 204. FRONTEND COUPLING

```text
Node
+
React
+
TypeScript
+
Bundler
```

may form a coupled stack.

---

# 205. AGENT COUPLING

```text
Agent Framework
+
LLM Provider
+
Tool Schema
+
Memory
```

may form a behavioral compatibility stack.

---

# 206. VERSION COMPATIBILITY TEST

Compatibility should be verified before adoption.

---

# 207. PERFORMANCE REGRESSION

Version upgrades must check for:

```text
Latency Increase
Memory Increase
CPU Increase
GPU Increase
Token Increase
Storage Increase
```

---

# 208. COST REGRESSION

Cloud service upgrades may change:

```text
Price
Token Economics
Bandwidth
Storage
```

---

# 209. LICENSE REGRESSION

Version upgrades may change license terms.

Every upgrade must therefore connect to:

```text
23_LICENSE_AND_COMPLIANCE.md
```

---

# 210. SECURITY REGRESSION

An upgrade can introduce vulnerabilities.

Security scanning remains mandatory.

---

# 211. BEHAVIORAL REGRESSION

AI and agent upgrades require behavioral tests.

---

# 212. DOCUMENTATION REGRESSION

An upgrade should be rejected if critical migration documentation is unavailable for a breaking change.

---

# 213. SUPPORT SCORE

A component may be evaluated using:

```text
Upstream Support
Security
Stability
Compatibility
Maintenance
Documentation
Community
```

---

# 214. VERSION SCORE

Conceptually:

```text
Version Health =
Support
+
Security
+
Compatibility
+
Stability
+
Maintenance
```

---

# 215. SCORE IS NOT DECISION

A high score cannot override:

```text
License Failure
Security Failure
Architecture Failure
```

---

# 216. VERSION APPROVAL STATES

```text
APPROVED
CANDIDATE
EXPERIMENTAL
DEPRECATED
BLOCKED
```

---

# 217. APPROVED VERSION

May be used in production.

---

# 218. CANDIDATE VERSION

Under validation.

---

# 219. EXPERIMENTAL VERSION

May be used only in controlled environments.

---

# 220. DEPRECATED VERSION

Existing use allowed temporarily.

---

# 221. BLOCKED VERSION

Must not be used.

---

# 222. VERSION BLOCK REASONS

```text
Security
License
Compatibility
EOL
Instability
Architecture
Performance
```

---

# 223. UPGRADE DECISION

A version becomes approved only after:

```text
Evaluation
Testing
Compliance
Documentation
```

---

# 224. VERSION LOCK UPDATE

Once approved:

```text
Version Support Policy
        ↓
Approved Version
        ↓
Version Lock Update
```

---

# 225. LOCK UPDATE REVIEW

Every Version Lock update must identify:

```text
Old Version
New Version
Reason
Impact
Tests
Rollback
License
```

---

# 226. VERSION LOCK DIFF

The change should be reviewable as a diff.

---

# 227. RELEASE NOTES

Every upgrade should have a concise release note.

---

# 228. MIGRATION NOTES

Breaking upgrades require migration documentation.

---

# 229. MIGRATION CHECKLIST

```text
[ ] Current version identified
[ ] Target version identified
[ ] EOL reviewed
[ ] Security reviewed
[ ] License reviewed
[ ] Compatibility reviewed
[ ] Migration guide reviewed
[ ] Tests updated
[ ] Performance tested
[ ] Rollback prepared
[ ] Version Lock updated
[ ] Manifest validated
```

---

# 230. EOL MIGRATION CHECKLIST

```text
[ ] EOL date identified
[ ] Replacement selected
[ ] Migration owner assigned
[ ] Migration tested
[ ] Production rollout planned
[ ] Old version removal planned
```

---

# 231. VERSION REMOVAL

A deprecated version becomes removed after:

```text
Migration Complete
+
No Supported Consumers
```

---

# 232. REMOVAL VERIFICATION

Search must confirm that no active production component depends on the removed version.

---

# 233. ORPHANED DEPENDENCY

Unused dependencies should be removed.

---

# 234. DEAD VERSION

A version no longer used anywhere should be removed from the baseline.

---

# 235. DOCUMENTATION CLEANUP

After removal:

```text
Approved Matrix
Version Lock
Manifest
Bootstrap
CI
Docs
```

must be updated.

---

# 236. BOOTSTRAP VERSION POLICY

Bootstrap must install versions consistent with Version Lock.

---

# 237. BOOTSTRAP EOL CHECK

Bootstrap should detect when a locked component becomes EOL.

---

# 238. BOOTSTRAP WARNING

If an existing environment contains an EOL version:

```text
EOL WARNING
```

should be generated.

---

# 239. BOOTSTRAP BLOCK

For critical production profiles:

```text
EOL
→ Installation Block
```

unless explicitly overridden.

---

# 240. DEVELOPMENT EXCEPTION

Development environments may temporarily use:

```text
Experimental
Candidate
```

versions.

---

# 241. PRODUCTION STRICTNESS

Production must have the strictest version policy.

---

# 242. DEVELOPMENT FLEXIBILITY

Development can evaluate future versions without changing production.

---

# 243. STAGING

Staging should approximate production but may test the next supported release.

---

# 244. ENVIRONMENT POLICY

```text
Development:
Current + Candidate

Testing:
Supported + Candidate

Staging:
Production + Candidate

Production:
Approved + Locked
```

---

# 245. VERSION PROMOTION

```text
Development
↓
CI
↓
Testing
↓
Staging
↓
Canary
↓
Production
```

---

# 246. NO DIRECT PRODUCTION UPGRADE

Critical dependencies should not jump directly from:

```text
Old Production
```

to:

```text
New Production
```

without validation.

---

# 247. EMERGENCY PATCH

Security emergencies may bypass some normal stages.

---

# 248. EMERGENCY UPGRADE

An emergency upgrade must still record:

```text
Reason
Version
Risk
Tests
Decision
```

---

# 249. POST-EMERGENCY REVIEW

After emergency deployment:

```text
Full Regression
Documentation
Version Lock
Compliance
```

must be completed.

---

# 250. LONG-TERM SUPPORT

JARVIS should prefer dependencies with predictable support lifecycles.

---

# 251. SUPPORTABILITY SCORE

Long-lived infrastructure should be evaluated for:

```text
Release Cadence
EOL Policy
Security Support
Migration Path
Community
Commercial Support
```

---

# 252. ABANDONED PROJECT

If upstream becomes abandoned:

```text
Migration Candidate
```

status should be considered.

---

# 253. PROJECT HEALTH

Version support is connected to project health.

---

# 254. MAINTAINER RISK

A dependency with one inactive maintainer may have elevated lifecycle risk.

---

# 255. RELEASE FREQUENCY

Irregular releases are not automatically bad, but must be evaluated.

---

# 256. STABLE PROJECT

A low release frequency can be acceptable when:

```text
Stable
Secure
Supported
```

---

# 257. FAST-MOVING PROJECT

Rapid release frequency increases:

```text
Upgrade Cost
Regression Risk
```

---

# 258. AI ECOSYSTEM

AI components generally require shorter review cycles than traditional infrastructure.

---

# 259. AI REVIEW CADENCE

Recommended:

```text
Monthly
```

for critical AI frameworks/models.

---

# 260. INFRASTRUCTURE REVIEW

Recommended:

```text
Quarterly
```

for standard infrastructure.

---

# 261. EOL WATCH

JARVIS should maintain an upcoming EOL list:

```text
Next 180 Days
Next 365 Days
```

---

# 262. EOL ALERT

A component entering the final:

```text
180 days
```

before EOL should trigger migration planning.

---

# 263. CRITICAL EOL ALERT

At:

```text
90 days
```

the migration should be active.

---

# 264. FINAL EOL ALERT

At:

```text
30 days
```

the migration should be release-blocking unless exception-approved.

---

# 265. SECURITY OVERRIDE

A security issue can accelerate the timeline regardless of EOL.

---

# 266. VERSION POLICY FOR PYTHON PACKAGES

Python dependencies should use:

```text
Lockfile
+
Exact Version
```

in production.

---

# 267. VERSION POLICY FOR NODE PACKAGES

Node dependencies should use:

```text
package-lock
```

or the officially selected package manager's equivalent lockfile.

---

# 268. NATIVE DEPENDENCIES

Native dependencies require additional compatibility testing.

---

# 269. OS DEPENDENCIES

Operating system packages must also be version-managed for production containers.

---

# 270. SYSTEM LIBRARIES

Critical libraries such as:

```text
glibc
OpenSSL
libstdc++
```

must be tracked through the base image/runtime policy.

---

# 271. OPENSSL

OpenSSL updates should be prioritized when security issues arise.

---

# 272. CERTIFICATE STORES

CA certificate bundles should not be allowed to become indefinitely stale.

---

# 273. BROWSER CERTIFICATES

Browser updates may affect TLS behavior.

---

# 274. PROTOCOL VERSIONS

JARVIS should track important protocol versions:

```text
HTTP
WebSocket
MCP
TLS
Database Protocols
```

---

# 275. MCP VERSIONING

MCP clients and servers must be compatible with the supported protocol version.

---

# 276. MCP SERVER VERSION

Each approved MCP server should have:

```text
Server Version
Protocol Version
Compatibility
```

recorded.

---

# 277. MCP BREAKING CHANGE

A breaking MCP server upgrade requires:

```text
Integration Test
Tool Schema Test
Permission Test
```

---

# 278. PLUGIN API VERSION

The JARVIS plugin API must be versioned.

---

# 279. PLUGIN COMPATIBILITY

Plugins should declare:

```text
Minimum JARVIS Version
Maximum Tested JARVIS Version
Plugin API Version
```

---

# 280. PLUGIN DEPRECATION

Old plugin APIs should have migration paths.

---

# 281. PLUGIN ABI

Native plugins may require ABI compatibility management.

---

# 282. VOICE MODEL VERSIONING

Voice components should track:

```text
STT Model
TTS Model
Voice
Tokenizer
Runtime
```

---

# 283. VOICE REGRESSION

Voice upgrades should evaluate:

```text
WER
Latency
Streaming
Interruption
Audio Quality
```

---

# 284. VISION MODEL VERSIONING

Vision upgrades should evaluate:

```text
Accuracy
Latency
VRAM
Resolution
OCR
Object Detection
```

---

# 285. BROWSER AGENT REGRESSION

Browser upgrades should evaluate:

```text
Navigation
Clicking
Typing
Downloads
Uploads
Authentication
Screenshots
```

---

# 286. AGENT REGRESSION

Agent upgrades should evaluate:

```text
Planning
Tool Selection
Tool Arguments
Retries
Memory
Final Answer
```

---

# 287. MEMORY REGRESSION

Memory upgrades should evaluate:

```text
Retrieval
Recall
Precision
Latency
Persistence
Deletion
```

---

# 288. SECURITY REGRESSION

Every major upgrade should rerun security tests.

---

# 289. PERFORMANCE BASELINE

JARVIS should maintain performance baselines.

---

# 290. VERSION PERFORMANCE COMPARISON

Before adoption:

```text
Old Version
vs
New Version
```

should be compared where the component is performance-critical.

---

# 291. ACCEPTABLE REGRESSION

Each component may define acceptable regression thresholds.

---

# 292. RELEASE BLOCK

If regression exceeds the threshold:

```text
Upgrade Blocked
```

---

# 293. COST REGRESSION

Cloud services should also have cost thresholds.

---

# 294. TOKEN COST REGRESSION

For model upgrades:

```text
Cost / Request
```

should be compared where applicable.

---

# 295. LATENCY REGRESSION

Critical interactive components should have latency thresholds.

---

# 296. MEMORY REGRESSION

RAM/VRAM increases must be considered for local deployments.

---

# 297. HARDWARE COMPATIBILITY

A version requiring newer hardware may not automatically be approved.

---

# 298. GPU GENERATION

Model/runtime upgrades must consider supported GPU architectures.

---

# 299. CPU ARCHITECTURE

JARVIS should explicitly track:

```text
x86_64
ARM64
```

where supported.

---

# 300. PLATFORM SUPPORT

Production support matrix should distinguish:

```text
Windows
Linux
macOS
Docker
Cloud
```

as applicable.

---

# 301. WINDOWS

Windows support must include:

```text
Runtime
GPU
Filesystem
Process
Browser
Shell
```

compatibility.

---

# 302. LINUX

Linux support must consider:

```text
Distribution
Kernel
glibc
GPU
Container Runtime
```

---

# 303. MACOS

macOS support must consider:

```text
Apple Silicon
Intel
Metal
Browser
Native Dependencies
```

---

# 304. CONTAINER SUPPORT

Container environments should have their own tested version matrix.

---

# 305. CLOUD SUPPORT

Cloud infrastructure versions should be tracked independently from local development versions.

---

# 306. VERSION SUPPORT MATRIX

Conceptually:

| Component | Preferred | Supported | Candidate | EOL Policy |
|---|---|---|---|---|
| Python | Defined by Version Lock | Active supported lines | Next minor | Upstream EOL |
| Node.js | LTS | Active LTS | Current | Upstream EOL |
| PostgreSQL | Current supported major | Supported majors | Next major | 5-year upstream window |
| React | Stable | Stable supported | Canary | Upstream policy |
| Playwright | Locked release | Current validated line | Next release | Continuous browser alignment |
| Docker | Stable | Supported stable | Test | Upstream lifecycle |
| Kubernetes | Supported minor | Latest 3 minor lines | Next minor | Upstream policy |

---

# 307. CURRENT UPSTREAM FACTS

As of the policy date:

```text
Date:
2026-08-10
```

examples include:

```text
Node.js 24.x → LTS
Node.js 22.x → LTS
Node.js 26.x → Current

PostgreSQL:
18.x → Supported
17.x → Supported
16.x → Supported
15.x → Supported
14.x → Supported until November 2026

Kubernetes:
Latest three minor release branches supported

React:
Stable channel supported
Canary available separately
Experimental available separately
```

These are upstream facts and must not be copied blindly into Version Lock. citeturn0search12turn0search3turn0search13turn0search0

---

# 308. CURRENT ≠ JARVIS APPROVED

Even if:

```text
Upstream = Current
```

the JARVIS status can still be:

```text
CANDIDATE
```

until tested.

---

# 309. SUPPORT POLICY UPDATE

This document itself should not be edited every time a patch version is released.

Patch-level exact versions belong in:

```text
Version Lock
```

---

# 310. POLICY UPDATE TRIGGER

This document changes when:

```text
Support Strategy
Lifecycle Policy
Upgrade Policy
Deprecation Policy
```

changes.

---

# 311. VERSION LOCK UPDATE TRIGGER

Version Lock changes when:

```text
Exact Version
```

changes.

---

# 312. SEPARATION OF CONCERNS

```text
24_VERSION_SUPPORT_POLICY
→ Lifecycle

VERSION LOCK
→ Exact Artifact

MANIFEST
→ System Definition

BOOTSTRAP
→ Installation

COMPLIANCE CHECKER
→ Validation
```

---

# 313. VERSION POLICY AUTHORITY

The hierarchy is:

```text
JAS
↓
Version Support Policy
↓
Approved Stack
↓
Version Lock
↓
Manifest
↓
Bootstrap
```

---

# 314. CONFLICT RULE

If Version Lock specifies an EOL version:

```text
COMPLIANCE FAILURE
```

unless an approved exception exists.

---

# 315. CONFLICT EXAMPLE

```text
Support Policy:
Python 3.13+

Version Lock:
Python 3.10
```

Result:

```text
INVALID
```

unless an explicitly documented legacy exception exists.

---

# 316. LEGACY COMPONENT

A legacy component may remain temporarily when:

```text
Migration Cost
+
Compatibility Constraints
```

justify it.

---

# 317. LEGACY STATUS

Legacy components should be marked:

```text
LEGACY
```

and not silently remain as normal supported dependencies.

---

# 318. LEGACY MIGRATION

Every legacy component should have:

```text
Target Replacement
Migration Plan
Target Date
```

where practical.

---

# 319. NO LEGACY GROWTH

New architecture must not depend on deprecated or legacy components unless explicitly approved.

---

# 320. NEW COMPONENT RULE

A new dependency must be:

```text
Supported Upstream
+
Approved by JAS
```

---

# 321. EOL COMPONENT RULE

New EOL dependencies:

```text
REJECTED
```

by default.

---

# 322. PRE-RELEASE COMPONENT RULE

Pre-release versions:

```text
Experimental
```

by default.

---

# 323. RELEASE CANDIDATE RULE

Release candidates may be evaluated but are not production-approved by default.

---

# 324. NIGHTLY BUILDS

Nightly builds are:

```text
Experimental
```

unless explicitly approved.

---

# 325. GIT HEAD

Unpinned Git HEAD is prohibited in production dependencies.

---

# 326. GIT COMMIT PINNING

Commit pinning may be used when:

```text
No stable release exists
```

and the component is explicitly approved.

---

# 327. COMMIT PINNING REQUIREMENTS

Record:

```text
Repository
Commit SHA
Date
Reason
Expected Release
```

---

# 328. SNAPSHOT BUILDS

Snapshot builds are not production-approved.

---

# 329. FORKED VERSION

Forked versions require:

```text
Fork Source
Commit
Patch Set
Owner
Version Identifier
```

---

# 330. INTERNAL PATCH

Internal patches must be tracked.

---

# 331. SECURITY BACKPORT

Security backports should document:

```text
CVE
Patch
Upstream Reference
Testing
```

---

# 332. VERSION PROVENANCE

Every locked artifact should have a traceable source.

---

# 333. ARTIFACT INTEGRITY

Where practical:

```text
Checksum
Signature
Digest
```

should be verified.

---

# 334. CONTAINER DIGEST

Container images should prefer immutable digests.

---

# 335. MODEL HASH

Model weights should preferably have integrity verification.

---

# 336. PACKAGE HASH

Lockfiles should retain hashes where supported.

---

# 337. SUPPLY CHAIN

Version support policy is part of software supply-chain security.

---

# 338. DEPENDENCY CONFUSION

The project must avoid ambiguous package names and untrusted package sources.

---

# 339. PACKAGE SOURCE POLICY

Production packages should originate from approved registries or verified sources.

---

# 340. MIRRORS

Internal mirrors must preserve artifact identity.

---

# 341. CACHE

Dependency caches must not silently replace artifacts with different versions.

---

# 342. REPRODUCIBILITY

A production environment must be reproducible from:

```text
Version Lock
+
Manifest
+
Approved Artifacts
```

---

# 343. VERSION VERIFICATION

System Verification must verify actual installed versions against Version Lock.

---

# 344. VERSION DRIFT FAILURE

If:

```text
Installed Version
≠
Locked Version
```

the verifier should report:

```text
VERSION DRIFT
```

---

# 345. CRITICAL VERSION DRIFT

For critical components:

```text
VERSION DRIFT
→ VERIFICATION FAILED
```

---

# 346. NON-CRITICAL DRIFT

For non-critical development components:

```text
WARNING
```

may be acceptable.

---

# 347. PRODUCTION RULE

Production must have:

```text
Zero Unapproved Critical Version Drift
```

---

# 348. VERSION REPORT

System Verification should produce:

```text
VERSION_REPORT
```

containing:

```text
Component
Expected Version
Actual Version
Status
```

---

# 349. EXAMPLE

```text
Python
Expected: 3.13.x
Actual:   3.13.x
Status:   PASS
```

---

# 350. FAILURE EXAMPLE

```text
Qdrant
Expected: locked version
Actual:   different version
Status:   FAIL
```

---

# 351. MODEL VERSION REPORT

The report should include model revisions.

---

# 352. MCP VERSION REPORT

The report should include MCP server versions.

---

# 353. PLUGIN VERSION REPORT

The report should include installed plugin versions.

---

# 354. BROWSER VERSION REPORT

The report should include browser revision information.

---

# 355. CONTAINER VERSION REPORT

The report should include image tags and/or digests.

---

# 356. VERSION AUDIT

A complete audit should answer:

```text
What is installed?
What is supported?
What is locked?
What is EOL?
What changed?
Why did it change?
```

---

# 357. UPGRADE AUDIT

An upgrade record should answer:

```text
Why upgrade?
Why now?
What changed?
What could break?
How was it tested?
How can it be rolled back?
```

---

# 358. DOWNGRADE POLICY

Downgrades are allowed only when:

```text
Security
Compatibility
Operational Incident
```

justify them.

---

# 359. DOWNGRADE RECORD

A downgrade must be documented.

---

# 360. SECURITY DOWNGRADE

Security-related downgrades require exceptional review.

---

# 361. INCIDENT ROLLBACK

Production incidents may trigger immediate rollback.

---

# 362. POST-ROLLBACK

After rollback:

```text
Root Cause
Version Difference
Security Status
Migration Plan
```

must be reviewed.

---

# 363. VERSION FREEZE

During critical releases, JARVIS may temporarily freeze dependency upgrades.

---

# 364. RELEASE FREEZE

A release freeze prevents unrelated dependency updates from entering the release branch.

---

# 365. SECURITY EXCEPTION TO FREEZE

Critical security fixes may bypass the freeze.

---

# 366. LONG-TERM FREEZE

Long-term freezes are discouraged because they increase EOL and security risk.

---

# 367. UPGRADE DEBT

Failure to upgrade creates:

```text
Upgrade Debt
```

---

# 368. UPGRADE DEBT TRACKING

Upgrade debt should be tracked like technical debt.

---

# 369. DEBT PRIORITY

Priority increases when:

```text
EOL Approaches
Security Risk Increases
Migration Complexity Increases
```

---

# 370. VERSION SUPPORT DASHBOARD

Long term, the project should expose:

```text
Current Versions
Upcoming Versions
EOL Dates
Deprecated Versions
Security Alerts
Upgrade Candidates
```

---

# 371. AUTOMATION

The dashboard may be generated automatically from:

```text
Version Lock
Software Matrix
Support Metadata
Security Data
```

---

# 372. ROADMAP INTEGRATION

Future version candidates should feed:

```text
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

---

# 373. VERSION ROADMAP

Conceptually:

```text
Current
↓
Next
↓
Future
↓
Experimental
```

---

# 374. FUTURE VERSION

A future version must not automatically enter production merely because it is newer.

---

# 375. EXPERIMENTAL TRACK

Experimental versions should be isolated from the stable production baseline.

---

# 376. EXPERIMENTAL ENVIRONMENT

Experimental versions should ideally run in:

```text
Separate Environment
Container
Virtual Environment
Branch
```

---

# 377. EXPERIMENTAL DATA

Experimental components should not automatically receive production data.

---

# 378. EXPERIMENTAL MODEL

Experimental models should not automatically become user-facing production models.

---

# 379. EXPERIMENTAL MCP

Experimental MCP servers should be sandboxed.

---

# 380. EXPERIMENTAL PLUGIN

Experimental plugins should have restricted permissions.

---

# 381. VERSION SUPPORT AND SECURITY

The security policy has priority when an upstream version becomes vulnerable.

---

# 382. CVE RESPONSE

When a vulnerability affects a locked component:

```text
Detect
↓
Assess
↓
Patch / Upgrade
↓
Test
↓
Deploy
```

---

# 383. CRITICAL CVE

Critical vulnerabilities may trigger emergency upgrades.

---

# 384. HIGH CVE

High vulnerabilities should normally trigger accelerated remediation.

---

# 385. MEDIUM CVE

Medium vulnerabilities follow normal remediation timelines unless context increases risk.

---

# 386. LOW CVE

Low vulnerabilities may be handled through scheduled maintenance.

---

# 387. VERSION SUPPORT AND LICENSE

A version can become unsupported because its license changes.

---

# 388. LICENSE CHANGE

If a new version introduces incompatible licensing:

```text
Do Not Upgrade
```

until compliance approves it.

---

# 389. VERSION SUPPORT AND ARCHITECTURE

A new version can become incompatible with JAS.

---

# 390. ARCHITECTURE BLOCK

If the new version violates JAS:

```text
Upgrade Rejected
```

---

# 391. VERSION SUPPORT AND PERFORMANCE

A newer version can be rejected due to unacceptable performance regression.

---

# 392. VERSION SUPPORT AND RELIABILITY

A newer version can be rejected due to stability problems.

---

# 393. VERSION SUPPORT AND DOCUMENTATION

A major upgrade without sufficient migration documentation may be deferred.

---

# 394. VERSION SUPPORT AND ECOSYSTEM

A dependency may be held back because surrounding dependencies have not yet caught up.

---

# 395. COMPATIBILITY HOLD

A version may enter:

```text
SUPPORTED UPSTREAM
```

but remain:

```text
JAS CANDIDATE
```

until ecosystem compatibility exists.

---

# 396. FINAL APPROVAL CONDITIONS

A version becomes production-approved only if:

```text
Upstream Supported
+
License Compatible
+
Security Acceptable
+
JAS Compatible
+
Tested
+
Operationally Viable
```

---

# 397. VERSION LOCK CONDITION

Only approved versions may enter Version Lock.

---

# 398. MANIFEST CONDITION

Only locked versions may be referenced as production baseline versions.

---

# 399. BOOTSTRAP CONDITION

Bootstrap installs locked versions.

---

# 400. VERIFICATION CONDITION

Verification confirms installed versions match locked versions.

---

# 401. COMPLETE VERSION CHAIN

```text
Upstream Version
       ↓
Support Evaluation
       ↓
JAS Approval
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
```

---

# 402. VERSION LIFECYCLE

The complete lifecycle is:

```text
UNKNOWN
   ↓
DISCOVERED
   ↓
CANDIDATE
   ↓
TESTING
   ↓
APPROVED
   ↓
CURRENT
   ↓
MAINTENANCE
   ↓
DEPRECATED
   ↓
EOL
   ↓
REMOVED
```

---

# 403. VERSION LIFECYCLE RULE

A version must never silently jump from:

```text
CURRENT
```

to:

```text
REMOVED
```

without lifecycle records.

---

# 404. DEPRECATION RECORD

Every deprecation must be documented.

---

# 405. REMOVAL RECORD

Every removal must be documented.

---

# 406. VERSION HISTORY

The project should preserve historical version decisions.

---

# 407. HISTORICAL REPRODUCTION

JARVIS should be able to reproduce older releases where practical.

---

# 408. RELEASE ARCHIVE

Previous production artifacts should be retained according to the release/retention policy.

---

# 409. VERSION LOCK ARCHIVE

Each production release must retain its Version Lock.

---

# 410. MANIFEST ARCHIVE

Each production release must retain its Manifest.

---

# 411. SBOM ARCHIVE

Each production release should retain its SBOM.

---

# 412. COMPLIANCE ARCHIVE

Each production release should retain its compliance baseline.

---

# 413. VERSION SUPPORT ARCHIVE

Changes to this policy should be version-controlled.

---

# 414. POLICY REVISION

A policy revision should include:

```text
Version
Date
Changes
Reason
Impact
```

---

# 415. POLICY GOVERNANCE

This document is governed by:

```text
JAS v1
```

until a future JAS revision changes its authority.

---

# 416. POLICY CHANGE

Changes require:

```text
Evidence
Impact Analysis
Review
Approval
```

---

# 417. NO AD-HOC VERSION POLICY

Developers must not establish independent support rules for individual components.

---

# 418. COMPONENT-SPECIFIC POLICY

A component may have stricter rules than this document.

It may not silently have weaker production rules.

---

# 419. STRICTER RULE

Example:

```text
Global:
Patch updates allowed

Component:
Patch updates require manual approval
```

The stricter rule wins.

---

# 420. CONFLICT RESOLUTION

When policies conflict:

```text
Security
↓
License/Compliance
↓
JAS Architecture
↓
Version Support
↓
Technical Preference
```

---

# 421. VERSION SUPPORT VS SECURITY

Security takes precedence.

---

# 422. VERSION SUPPORT VS LICENSE

License compliance takes precedence.

---

# 423. VERSION SUPPORT VS CONVENIENCE

Convenience never overrides policy.

---

# 424. VERSION SUPPORT VS PERFORMANCE

Performance may justify rejecting an otherwise supported version.

---

# 425. VERSION SUPPORT VS NEW FEATURES

New features alone do not justify a production upgrade.

---

# 426. UPGRADE MOTIVATION

Valid reasons include:

```text
Security
EOL
Critical Bug
Required Feature
Performance
Compatibility
License
Operational Stability
```

---

# 427. INVALID UPGRADE REASON

```text
"Latest"
```

alone is not a sufficient reason.

---

# 428. INVALID UPGRADE REASON

```text
"Everyone uses it"
```

is not a sufficient reason.

---

# 429. INVALID UPGRADE REASON

```text
"Newer is better"
```

is not a sufficient reason.

---

# 430. VERSION SUPPORT POLICY FOR DEVELOPERS

Developers should always know:

```text
What version is supported?
What version is locked?
What version is next?
```

---

# 431. VERSION SUPPORT POLICY FOR BOOTSTRAP

Bootstrap should know:

```text
Allowed
Locked
Deprecated
Blocked
```

versions.

---

# 432. VERSION SUPPORT POLICY FOR CI

CI should test:

```text
Locked
+
Supported Range
+
Candidate
```

where appropriate.

---

# 433. CI MATRIX

Critical components may use:

```text
Minimum Supported
Preferred
Maximum Tested
```

test matrix.

---

# 434. CI MINIMUM VERSION

Testing the minimum supported version prevents accidental loss of compatibility.

---

# 435. CI MAXIMUM VERSION

Testing the maximum supported version provides early warning for future upgrades.

---

# 436. CI CANDIDATE VERSION

Testing the next version reduces migration shock.

---

# 437. PRODUCTION VERSION

Production uses:

```text
Exact Version Lock
```

---

# 438. DEVELOPMENT VERSION

Development may use:

```text
Locked
+
Candidate
```

under controlled conditions.

---

# 439. TESTING VERSION

Testing may include:

```text
Supported Matrix
```

---

# 440. STAGING VERSION

Staging should use the production version unless explicitly testing an upgrade candidate.

---

# 441. VERSION POLICY FOR THIRD-PARTY SERVICES

Third-party services should track:

```text
API Version
Service Version
Contract Version
Terms Version
```

where applicable.

---

# 442. TERMS VERSION

Provider Terms of Service changes can be lifecycle events.

---

# 443. TERMS CHANGE

A material terms change should trigger compliance review.

---

# 444. API EOL

An API EOL should trigger migration planning.

---

# 445. CLOUD PROVIDER DEPRECATION

Cloud-provider deprecations must be treated as external dependencies.

---

# 446. MCP SERVICE DEPRECATION

MCP server deprecation should trigger:

```text
Alternative
Migration
Testing
```

---

# 447. PLUGIN API DEPRECATION

Plugin API changes require compatibility policy.

---

# 448. MODEL API DEPRECATION

Model endpoint retirement requires migration before provider EOL.

---

# 449. MODEL RETIREMENT

A retired model must not remain silently in production.

---

# 450. MODEL FALLBACK

Production should have a tested fallback strategy for critical model services where practical.

---

# 451. FALLBACK VERSION

Fallback models must also be version locked.

---

# 452. VERSION FAILOVER

Failover should not select arbitrary latest versions.

---

# 453. VERSION-AWARE FAILOVER

Failover should select from an approved model/version set.

---

# 454. VERSION POLICY AND OBSERVABILITY

Observability must expose:

```text
Component
Version
Revision
Environment
```

---

# 455. VERSION POLICY AND LOGGING

Version information should be included in diagnostic reports.

---

# 456. VERSION POLICY AND INCIDENTS

Incidents should record the active component versions.

---

# 457. INCIDENT REPRODUCTION

Version records are required for reliable reproduction.

---

# 458. DEBUG REPORT

A JARVIS diagnostic report should include:

```text
JAS Version
Manifest Version
Bootstrap Version
Core Version
Runtime Versions
Database Versions
Model Versions
MCP Versions
Plugin Versions
Browser Versions
Container Versions
```

---

# 459. SUPPORT MATRIX AUTOMATION

The support matrix should eventually be generated from structured metadata.

---

# 460. MACHINE-READABLE SUPPORT DATA

Long-term implementation may use:

```text
version-support.yaml
```

or equivalent.

---

# 461. SUPPORT DATA EXAMPLE

```yaml
component: python
preferred: "3.x"
minimum_supported: "3.x"
maximum_tested: "3.x"
status: supported
```

---

# 462. VERSION LOCK EXAMPLE

```yaml
python:
  version: "X.Y.Z"
```

The exact value belongs in Version Lock.

---

# 463. SUPPORT POLICY EXAMPLE

```yaml
python:
  supported:
    - "X.Y"
    - "X.Z"
  preferred: "X.Y"
```

---

# 464. MACHINE READABILITY

The eventual support metadata should be consumable by:

```text
Bootstrap
CI
Compliance Checker
Upgrade Manager
```

---

# 465. VERSION POLICY ENGINE

Long-term JARVIS may implement:

```text
Version Policy Engine
```

that automatically evaluates:

```text
Installed
Supported
Locked
EOL
```

---

# 466. VERSION POLICY ENGINE OUTPUT

Example:

```text
Python
Installed:  X.Y.Z
Locked:     X.Y.Z
Supported:  YES
EOL:        NO
Status:     PASS
```

---

# 467. VERSION POLICY FAILURE

Example:

```text
Node
Installed:  X
Locked:     Y
Supported:  NO
Status:     FAIL
```

---

# 468. VERSION POLICY WARNING

Example:

```text
PostgreSQL
Installed: supported
EOL: approaching
Status: MIGRATION WARNING
```

---

# 469. EOL COUNTDOWN

The system should be capable of calculating:

```text
Days Until EOL
```

for critical dependencies.

---

# 470. EOL DASHBOARD

Conceptually:

```text
Component       EOL       Days Left
PostgreSQL      Date      N
Node.js         Date      N
Kubernetes      Date      N
```

---

# 471. VERSION RISK SCORE

Long term, version risk may be calculated from:

```text
EOL Distance
Security
Maintenance
Compatibility
Upgrade Difficulty
```

---

# 472. HIGH VERSION RISK

High risk should trigger migration planning.

---

# 473. CRITICAL VERSION RISK

Critical risk should block new production deployments.

---

# 474. VERSION SUPPORT AND ROADMAP

Upgrade candidates should enter the project roadmap.

---

# 475. QUARTERLY REVIEW

At least quarterly, the project should review:

```text
Upcoming EOL
Major Releases
Security
Architecture
License
```

---

# 476. ANNUAL REVIEW

At least annually, the project should perform a broader stack lifecycle review.

---

# 477. ANNUAL STACK REVIEW

Review:

```text
Core Runtime
AI Stack
Agent Stack
Memory
Database
Browser
Voice
Vision
Frontend
Backend
Security
DevOps
Testing
```

---

# 478. VERSION POLICY METRIC

Useful metrics include:

```text
EOL Dependencies
Deprecated Dependencies
Outdated Dependencies
Security-Pending Dependencies
Upgrade Debt
Version Drift
```

---

# 479. TARGET

Production should aim for:

```text
0 EOL Critical Dependencies
0 Unapproved Version Drift
0 Unknown Critical Versions
```

---

# 480. FINAL SUPPORT POLICY

The fundamental rule is:

```text
Production
=
Supported
+
Approved
+
Locked
+
Verified
```

---

# 481. FINAL UPGRADE POLICY

```text
New Version
↓
Evaluate
↓
Test
↓
Approve
↓
Lock
↓
Deploy
```

---

# 482. FINAL DEPRECATION POLICY

```text
Upstream Deprecation
↓
JAS Deprecation
↓
Migration
↓
Removal
```

---

# 483. FINAL EOL POLICY

```text
Upstream EOL
↓
Migration Required
↓
Exception if necessary
↓
Removal
```

---

# 484. FINAL SECURITY POLICY

```text
Critical Security Issue
↓
Emergency Evaluation
↓
Patch / Upgrade
↓
Validation
↓
Deployment
```

---

# 485. FINAL MODEL POLICY

```text
Model Update
↓
Behavior Test
↓
License Test
↓
Performance Test
↓
Approval
↓
Version Lock
```

---

# 486. FINAL BROWSER POLICY

```text
Playwright Update
↓
Browser Revision Update
↓
Browser Tests
↓
Approval
↓
Version Lock
```

Playwright explicitly couples releases to supported browser binaries, so the browser and Playwright should not be treated as independently floating production dependencies. citeturn0search5

---

# 487. FINAL DATABASE POLICY

```text
Database Update
↓
Backup
↓
Migration Test
↓
Performance Test
↓
Recovery Test
↓
Approval
```

---

# 488. FINAL CONTAINER POLICY

```text
Base Image Update
↓
Security Scan
↓
SBOM
↓
Application Tests
↓
Approval
↓
Digest Lock
```

---

# 489. FINAL API POLICY

```text
API Update
↓
Compatibility
↓
Terms
↓
Data Flow
↓
Testing
↓
Approval
```

---

# 490. FINAL PLUGIN POLICY

```text
Plugin Update
↓
API Compatibility
↓
Permission Review
↓
Security
↓
License
↓
Approval
```

---

# 491. FINAL MCP POLICY

```text
MCP Update
↓
Protocol Compatibility
↓
Tool Schema
↓
Security
↓
License
↓
Approval
```

---

# 492. FINAL VERSION GOVERNANCE CHAIN

```text
                    JAS v1
                       │
                       ▼
             Version Support Policy
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
     Upstream Lifecycle      JAS Lifecycle
            │                     │
            └──────────┬──────────┘
                       ▼
                Approved Version
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
             System Verification
                       │
                       ▼
                  Production
```

---

# 493. FINAL VERSION LIFECYCLE

```text
DISCOVERED
    ↓
CANDIDATE
    ↓
TESTING
    ↓
APPROVED
    ↓
LOCKED
    ↓
SUPPORTED
    ↓
MAINTENANCE
    ↓
DEPRECATED
    ↓
MIGRATION
    ↓
REMOVED
```

---

# 494. FINAL PRINCIPLE

> **JARVIS does not run "whatever version happens to be installed."**

---

# 495. FINAL PRINCIPLE

> **Every production component has a defined lifecycle.**

---

# 496. FINAL PRINCIPLE

> **Every production version is explicitly approved and locked.**

---

# 497. FINAL PRINCIPLE

> **Upstream support is necessary but not sufficient for JARVIS approval.**

---

# 498. FINAL PRINCIPLE

> **EOL versions are not part of the normal production baseline.**

---

# 499. FINAL PRINCIPLE

> **Security fixes have priority over normal upgrade cadence.**

---

# 500. FINAL PRINCIPLE

> **AI model versions require behavioral validation, not merely API compatibility testing.**

---

# 501. FINAL PRINCIPLE

> **Coupled components must be upgraded and validated as a compatible stack.**

---

# 502. FINAL PRINCIPLE

> **Version changes must be reproducible, auditable, and reversible whenever practical.**

---

# 503. FINAL PRINCIPLE

> **"Latest" is never a sufficient versioning strategy for production.**

---

# 504. FINAL PRODUCTION RULE

```text
NO LOCK
    → NOT REPRODUCIBLE

NO SUPPORT
    → NOT APPROVED

EOL
    → MIGRATION REQUIRED

UNKNOWN
    → NOT APPROVED

UNTESTED
    → NOT PRODUCTION

UNAPPROVED
    → NOT PRODUCTION
```

---

# 505. FINAL RELEASE RULE

```text
SUPPORTED
+
APPROVED
+
VERSION LOCKED
+
COMPLIANCE PASSED
+
SECURITY PASSED
+
TESTS PASSED
+
SYSTEM VERIFIED
=
PRODUCTION READY
```

---

# 506. RELATIONSHIP TO PREVIOUS DOCUMENT

```text
23_LICENSE_AND_COMPLIANCE.md
```

answers:

> Is this version legally/compliance acceptable?

This document answers:

> Is this version lifecycle/support acceptable?

---

# 507. RELATIONSHIP TO NEXT DOCUMENT

```text
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

will answer:

> What technologies and versions should JARVIS investigate next?

---

# 508. THREE-DOCUMENT CHAIN

```text
23_LICENSE_AND_COMPLIANCE
          │
          ▼
24_VERSION_SUPPORT_POLICY
          │
          ▼
25_ROADMAP_AND_FUTURE_TECHNOLOGIES
```

---

# 509. COMPLETE APPROVED STACK CHAIN

```text
Approved Stack
      │
      ├── License
      │
      ├── Version Support
      │
      └── Future Technology
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
      System Verification
```

---

# 510. CURRENT POLICY DATE

```text
Policy Date:
2026-08-10
```

Upstream lifecycle information is inherently time-sensitive and must be revalidated before creating the final Version Lock.

---

# 511. CURRENT POLICY STATUS

```text
============================================================

JAS-AS-24
VERSION SUPPORT POLICY

VERSION:
1.0

STATUS:
APPROVED

PRIMARY PURPOSE:
VERSION LIFECYCLE AND SUPPORT GOVERNANCE

CORE FUNCTION:
CONTROL WHICH SOFTWARE, MODELS, SERVICES,
RUNTIMES, MCP SERVERS, PLUGINS AND OTHER
VERSIONED COMPONENTS MAY ENTER AND REMAIN
IN THE JARVIS PRODUCTION BASELINE.

KEY RULE:
SUPPORTED + APPROVED + LOCKED + VERIFIED

NEXT DOCUMENT:
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md

============================================================
```

---

# 513. LOCAL LLM RUNTIME POLICY

Local LLM runtimes are versioned production components.

For JARVIS, a local LLM deployment is not identified by the model tag alone.

The runtime identity must distinguish:

```text
Runtime
+
Runtime Version
+
Model Name
+
Model Tag
+
Model Format
+
Quantization
+
Model Digest
+
Context Configuration
+
Hardware Profile
```

A change to any of these may affect reproducibility or model behavior.

---

# 514. OLLAMA

When Ollama is selected as an approved local inference runtime, JARVIS must treat:

```text
Ollama Runtime
+
Ollama Model
+
GPU Runtime
```

as a coupled compatibility stack.

Ollama upgrades must therefore be evaluated separately from model upgrades.

A newer Ollama runtime must not silently change the production model baseline.

---

# 515. OLLAMA VERSION LOCK

Production Ollama deployments must lock the exact runtime version.

The Version Lock should record:

```text
Runtime:
Ollama

Version:
<exact version>

Platform:
<platform>

Architecture:
<architecture>
```

The runtime version must not be inferred from the model tag.

---

# 516. OLLAMA MODEL IDENTITY

A production Ollama model must be identified using an explicit model reference and immutable artifact identity where available.

At minimum:

```text
Model Name
+
Model Tag
+
Model Digest
```

should be recorded.

Where available, JARVIS should additionally record:

```text
Model Layer Digest
Config Digest
Template Digest
System Layer Digest
License Layer Digest
```

This prevents a mutable tag from becoming the sole production identity.

---

# 517. OLLAMA LATEST POLICY

Production must not depend on an uncontrolled:

```text
latest
```

Ollama model alias.

Experimental or development environments may evaluate moving aliases, but production requires an explicitly approved and locked model identity.

This extends the existing production rule:

```text
Explicit Model ID
+
Explicit Revision
```

to local Ollama deployments.

---

# 518. OLLAMA MODEL TAG VERSUS DIGEST

A model tag is a human-facing reference.

A digest is an artifact identity.

Therefore:

```text
qwen2.5-coder:7b
```

and:

```text
sha256:<digest>
```

must not be treated as equivalent identifiers.

A production Version Lock should retain both when the runtime exposes both.

---

# 519. OLLAMA MANIFEST INTEGRITY

When an Ollama model manifest is available locally, JARVIS should validate that referenced blobs exist and that their SHA-256 hashes match the manifest.

The integrity chain should conceptually be:

```text
Model Tag
    ↓
Manifest
    ↓
Layer Digests
    ↓
Local Blobs
    ↓
SHA-256 Verification
```

A missing or mismatched required blob is a verification failure.

---

# 520. OLLAMA MODEL LAYERS

Ollama model artifacts may contain multiple logical layers.

JARVIS should distinguish, where exposed:

```text
Model Layer
System Layer
Template Layer
License Layer
Configuration
```

A model update must therefore not be evaluated solely by total file size.

Changes to a template, system layer, tokenizer/configuration, or license metadata may change behavior or compliance even when the underlying model weights are unchanged.

---

# 521. MODEL RUNTIME COUPLING

For local LLM inference, the effective production artifact is:

```text
Model
+
Runtime
+
GPU Driver
+
CUDA / GPU Backend
+
Hardware
```

A model may remain unchanged while an inference-runtime or GPU-stack upgrade changes:

```text
Latency
Memory Usage
VRAM Usage
Token Throughput
Numerical Behavior
Tool Calling
Structured Output
Context Handling
```

Therefore model validation must be repeated when a critical runtime layer changes.

---

# 522. LOCAL GPU CAPACITY

Local model approval must account for actual GPU capacity.

JARVIS should record at least:

```text
GPU Model
VRAM Total
VRAM Available
Driver Version
GPU Backend
```

where applicable.

A model that fits only under a particular memory condition must not be considered universally compatible with the platform.

---

# 523. VRAM HEADROOM

Production local-model deployments should preserve explicit VRAM headroom.

The Version Lock or hardware profile should distinguish:

```text
Model Memory Requirement
Runtime Overhead
Context Memory
KV Cache / Working Memory
Safety Headroom
```

A model must not be approved solely because its nominal artifact size is below total VRAM.

---

# 524. CPU/GPU OFFLOAD POLICY

When a local inference runtime reports partial CPU/GPU execution, JARVIS must record the execution mode used during validation.

Conceptually:

```text
CPU %
GPU %
```

or an equivalent runtime-specific execution profile.

A change from predominantly GPU execution to substantial CPU offload is a performance-affecting configuration change and requires performance validation.

---

# 525. GPU UTILIZATION IS NOT MODEL VALIDATION

Low instantaneous GPU utilization does not prove that GPU acceleration is functioning correctly.

Validation must distinguish:

```text
GPU Memory Residency
GPU Execution
CPU Offload
Throughput
Latency
```

A single instantaneous utilization reading must not be used as the sole acceptance criterion.

---

# 526. LOCAL MODEL PERFORMANCE BASELINE

Every production local model should have a reproducible performance baseline.

Where applicable, record:

```text
Prompt Set
Context Length
Input Tokens
Output Tokens
Time To First Token
Generation Time
Tokens / Second
CPU Usage
GPU Usage
VRAM Usage
Peak VRAM
```

The same benchmark configuration should be used when comparing model or runtime versions.

---

# 527. CONTEXT LENGTH POLICY

Context length is part of the effective model configuration.

A production lock must record the validated context configuration separately from the model's maximum advertised context length.

For example:

```text
Model Maximum Context:
<upstream/runtime value>

JARVIS Validated Context:
<tested value>
```

Changing the validated context length may change memory consumption and latency and therefore requires revalidation.

---

# 528. QUANTIZATION POLICY

Quantization is part of model identity.

JARVIS must track:

```text
Quantization Level
```

as part of the model lock.

A change such as:

```text
Q4
→
Q5
→
Q8
```

is a model artifact change even when the model family and parameter count remain identical.

Quantization changes require:

```text
Accuracy / Behavior Test
+
Performance Test
+
Memory Test
```

where applicable.

---

# 529. MODEL FORMAT POLICY

The model format must be tracked when relevant.

For local GGUF-based deployments:

```text
Format:
GGUF
```

should be recorded in the Version Lock.

Changing model format or conversion pipeline is treated as a model/runtime compatibility change.

---

# 530. LOCAL MODEL BEHAVIOR REGRESSION

Local LLM upgrades must test at minimum:

```text
Instruction Following
Reasoning
Tool Calling
Structured Output
Context Handling
Streaming
Latency
Token Throughput
Memory Usage
VRAM Usage
```

For JARVIS agent models, the regression suite must additionally include:

```text
Tool Selection
Tool Arguments
Retry Behavior
Failure Recovery
Final Answer Reliability
```

API compatibility alone is insufficient.

---

# 531. LOCAL MODEL FALLBACK POLICY

Production local inference may define an explicitly approved fallback model.

Fallbacks must be version-locked independently.

Conceptually:

```text
Primary Model
     ↓
Health / Capacity Check
     ↓
Approved Fallback
```

The fallback must not be selected dynamically from an uncontrolled `latest` alias.

A fallback change is a Version Lock change.

---

# 532. FALLBACK COMPATIBILITY

A fallback model must be validated for the same contract expected by the calling agent or service.

At minimum:

```text
Prompt Contract
Tool Schema
Structured Output
Context Requirements
Token Limits
Latency Expectations
Memory Requirements
Safety Requirements
```

A model is not an acceptable fallback merely because it can technically load.

---

# 533. LOCAL MODEL FAILOVER

If failover is implemented, JARVIS should record the reason for failover where observability permits.

Examples include:

```text
Out Of Memory
Runtime Failure
Model Load Failure
GPU Failure
Timeout
Health Check Failure
Capacity Limit
```

Failover must not silently replace the locked primary model in a way that makes production behavior unauditable.

---

# 534. OLLAMA ENVIRONMENT REPRODUCIBILITY

A production local-model environment should record the relevant runtime state, including:

```text
Ollama Version
OLLAMA_MODELS Location / Storage Policy
Installed Model References
Model Digests
GPU
Driver
Execution Mode
Context Configuration
```

Filesystem paths themselves are environment-specific and should not be treated as portable artifact identities.

The portable identity is the versioned artifact and its digest.

---

# 535. OLLAMA UPGRADE TEST MATRIX

An Ollama runtime upgrade requires, where applicable:

```text
[ ] Runtime Version Check
[ ] Model Load Test
[ ] Manifest Integrity Check
[ ] GPU Detection
[ ] VRAM Check
[ ] CPU/GPU Execution Check
[ ] Context Test
[ ] Streaming Test
[ ] Tool Calling Test
[ ] Structured Output Test
[ ] Performance Benchmark
[ ] Regression Test
[ ] Rollback Test
```

A runtime upgrade that changes model behavior or performance beyond the component's defined thresholds is blocked pending review.

---

# 536. LOCAL LLM VERSION RECORD

A Version Support / Version Lock record for a local LLM should conceptually contain:

```text
Runtime:
Ollama

Runtime Version:
<exact version>

Model:
<name>:<tag>

Model Digest:
sha256:<digest>

Format:
<format>

Quantization:
<quantization>

Context:
<validated context>

GPU:
<hardware>

VRAM:
<validated capacity>

Execution:
<CPU/GPU profile>

Status:
APPROVED | CANDIDATE | EXPERIMENTAL | DEPRECATED | BLOCKED

Reviewed:
YYYY-MM-DD
```

---

# 537. LOCAL LLM DRIFT DETECTION

JARVIS must detect drift between the expected local LLM baseline and the running environment.

Drift includes:

```text
Runtime Version Drift
Model Digest Drift
Model Tag Drift
Quantization Drift
Context Configuration Drift
GPU / Driver Drift
Execution Mode Drift
```

A critical production drift must be reported and, where appropriate, block startup or deployment.

---

# 538. LOCAL LLM APPROVAL RULE

A local LLM production baseline is approved only when:

```text
Supported Runtime
+
Approved Model
+
Verified Artifact Integrity
+
Compatible GPU Stack
+
Behavioral Validation
+
Performance Validation
+
License / Compliance Validation
+
Version Lock
=
APPROVED LOCAL LLM BASELINE
```

---

# 539. RELATIONSHIP TO VERSION LOCK

This policy defines the lifecycle and support rules for Ollama and local LLM components.

The Version Lock must contain the exact selected values.

Therefore:

```text
24_VERSION_SUPPORT_POLICY
        ↓
Allowed / Approved Runtime + Model
        ↓
VERSION LOCK
        ↓
Exact Ollama Version
+
Exact Model Identity
+
Digest
+
Validated Hardware Profile
```

---

# 540. RELATIONSHIP TO SYSTEM VERIFICATION

System Verification must verify that the running local LLM environment matches the Version Lock.

At minimum, the verification chain should establish:

```text
Runtime
   ↓
Model
   ↓
Digest
   ↓
GPU Stack
   ↓
Configuration
   ↓
Behavior
```

Only a verified chain may be considered reproducible production state.

---

# 541. POLICY REVISION NOTE

This v1.1 revision adds explicit governance for:

```text
Local LLM Runtimes
Ollama
Model Digests
Manifest Integrity
Quantization
Context Configuration
VRAM Headroom
CPU/GPU Offload
Local Model Performance
Fallback Models
Failover
Local LLM Drift Detection
```

These controls extend, rather than replace, the existing model, GPU, hardware, version-lock, security, compliance, and regression policies in this document.

---

# 542. UPDATED FINAL PRINCIPLE

> **A local LLM production deployment is a versioned runtime-and-model stack, not merely a model name.**

---

# 543. UPDATED FINAL PRODUCTION RULE

```text
OLLAMA RUNTIME LOCKED
+
MODEL ID LOCKED
+
MODEL DIGEST VERIFIED
+
QUANTIZATION VERIFIED
+
CONTEXT VERIFIED
+
GPU STACK COMPATIBLE
+
BEHAVIOR VALIDATED
+
PERFORMANCE VALIDATED
+
COMPLIANCE PASSED
+
VERSION LOCK PASSED
=
PRODUCTION-READY LOCAL LLM
```

---

# 544. UPDATED DOCUMENT STATUS

```text
============================================================

JAS-AS-24
VERSION SUPPORT POLICY

VERSION:
1.1

STATUS:
APPROVED

ADDED GOVERNANCE:
LOCAL LLM / OLLAMA VERSION SUPPORT

PRIMARY PURPOSE:
VERSION LIFECYCLE AND SUPPORT GOVERNANCE

CORE FUNCTION:
CONTROL WHICH SOFTWARE, MODELS, SERVICES,
RUNTIMES, MCP SERVERS, PLUGINS AND OTHER
VERSIONED COMPONENTS MAY ENTER AND REMAIN
IN THE JARVIS PRODUCTION BASELINE.

KEY RULE:
SUPPORTED + APPROVED + LOCKED + VERIFIED

NEXT DOCUMENT:
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md

============================================================
```

---

# 545. END OF DOCUMENT

```text
============================================================

JAS-AS-24
VERSION SUPPORT POLICY v1.1

APPROVED

============================================================
```

**END OF `24_VERSION_SUPPORT_POLICY.md`**