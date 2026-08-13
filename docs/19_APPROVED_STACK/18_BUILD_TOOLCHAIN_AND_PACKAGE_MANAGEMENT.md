# 18 — BUILD TOOLCHAIN AND PACKAGE MANAGEMENT STACK

**Document ID:** JAS-AS-18  
**Document:** `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED STACK SPECIFICATION  
**Primary Domain:** Build Systems, Dependency Management, Package Management, Toolchains and Reproducible Builds  
**Depends On:** JAS v1, `02_CORE_RUNTIME_AND_PROGRAMMING_LANGUAGES.md`, `15_DEVOPS_AND_DEPLOYMENT_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`  
**Related Documents:** `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`, `03_AI_AND_LLM_FRAMEWORKS.md`, `04_AGENT_ORCHESTRATION_STACK.md`, `07_BROWSER_AUTOMATION_STACK.md`, `09_COMPUTER_VISION_STACK.md`, `11_BACKEND_STACK.md`, `13_MCP_AND_EXTERNAL_INTEGRATION_STACK.md`, `14_SECURITY_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `19_APPROVED_MODELS.md`, `21_APPROVED_SOFTWARE_MATRIX.md`, `23_LICENSE_AND_COMPLIANCE.md`, `24_VERSION_SUPPORT_POLICY.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, System Verification, CI/CD, Release Engineering

---

# 1. PURPOSE

This document defines the official build, dependency, package-management and toolchain architecture for JARVIS.

The objective is to ensure that:

```text
Developer Machine
        ↓
Dependency Resolution
        ↓
Build
        ↓
Test
        ↓
Artifact
        ↓
Deployment
```

remains:

```text
Reproducible
Deterministic
Auditable
Secure
Portable
Maintainable
Versioned
```

---

# 2. CORE DECISION

JARVIS will not rely on one universal package manager for every technology.

Instead:

```text
Language / Ecosystem
        ↓
Native Ecosystem Tool
        ↓
Canonical Lockfile
        ↓
Version Lock
        ↓
Manifest
        ↓
Bootstrap
```

will be used.

---

# 3. BUILD SYSTEM PHILOSOPHY

The build system must answer five questions:

```text
1. What do we build?
2. With which tools?
3. With which exact dependencies?
4. From which source artifacts?
5. How do we reproduce the same artifact?
```

---

# 4. BUILD SYSTEM INVARIANT

A production artifact must be traceable to:

```text
Source Commit
+
Build Configuration
+
Toolchain Version
+
Dependency Lock
+
Base Image
+
Model / Asset Revision
```

---

# 5. PACKAGE MANAGEMENT PRINCIPLE

Package managers are not merely installation utilities.

They are part of:

```text
Supply Chain
+
Reproducibility
+
Security
+
Build Integrity
```

---

# 6. APPROVED PRIMARY TOOLCHAIN

The initial JARVIS toolchain is:

| Domain | Tool / Technology | Status |
|---|---|---|
| Python Project Management | `uv` | APPROVED |
| Python Dependency Resolution | `uv` | APPROVED |
| Python Lockfile | `uv.lock` | APPROVED |
| Python Environment | `uv` managed environment | APPROVED |
| JavaScript / TypeScript Package Management | Node ecosystem package manager | APPROVED |
| Frontend Lockfile | ecosystem-native lockfile | APPROVED |
| Native Compilation | C/C++ platform toolchain | APPROVED |
| Container Build | Docker BuildKit / Buildx | APPROVED |
| Container Composition | Docker Compose | APPROVED |
| Build Orchestration | Repository-level build scripts | APPROVED |
| CI Build | CI-native execution + repository build commands | APPROVED |
| Artifact Packaging | OCI / wheel / platform-native artifacts | APPROVED |
| Dependency Audit | Approved security tooling | APPROVED |
| SBOM | CycloneDX / container SBOM tooling | APPROVED |
| Build Provenance | Build attestation | APPROVED |

---

# 7. PYTHON TOOLCHAIN

Python is the primary application language according to the approved runtime architecture.

Python project management will use:

```text
uv
```

as the primary project/dependency tool.

uv provides Python project management, dependency resolution, environments, lockfiles and workspaces, and supports Windows, Linux and macOS. 

---

# 8. PYTHON PROJECT DEFINITION

The canonical Python project metadata file is:

```text
pyproject.toml
```

---

# 9. PYTHON LOCKFILE

The canonical Python dependency lockfile is:

```text
uv.lock
```

The lockfile records exact resolved dependency information and is intended to be committed to version control for reproducible installations. 

---

# 10. PYTHON LOCKFILE AUTHORITY

For JARVIS:

```text
pyproject.toml
        ↓
Dependency Intent
```

while:

```text
uv.lock
        ↓
Resolved Dependency State
```

---

# 11. LOCKFILE RULE

`uv.lock` must be committed to version control.

---

# 12. LOCKFILE EDITING

`uv.lock` must not be manually edited.

It should be generated and updated through `uv` commands. 

---

# 13. PYTHON DEPENDENCY ADDITION

Dependencies should be added through:

```text
uv add
```

rather than manually editing dependency resolution state.

---

# 14. PYTHON DEPENDENCY REMOVAL

Dependencies should be removed through:

```text
uv remove
```

---

# 15. PYTHON ENVIRONMENT

The project environment will use an isolated environment.

Conceptually:

```text
project/
└── .venv/
```

The `.venv` directory must not be committed to Git.

uv manages project environments and recommends keeping `.venv` outside version control. 

---

# 16. PYTHON COMMAND EXECUTION

Project commands should preferably execute through:

```text
uv run
```

to ensure the intended project environment is used.

uv verifies project/lockfile synchronization before execution. 

---

# 17. FROZEN PYTHON BUILDS

CI and release environments must use locked dependency state.

Conceptually:

```text
uv sync --locked
```

or the equivalent locked/frozen CI workflow.

---

# 18. LOCKED VS FROZEN

The distinction between checking lock consistency and blindly using an existing lockfile must be understood.

`--locked` verifies that the lockfile is current; `--frozen` uses the existing lockfile without updating it. 

---

# 19. PYTHON WORKSPACES

If the JARVIS repository evolves into multiple Python packages, uv workspaces may be used.

Example:

```text
packages/
├── jas-core/
├── jas-agents/
├── jas-memory/
├── jas-browser/
└── jas-tools/
```

uv workspaces can manage multiple packages with a shared lockfile. 

---

# 20. WORKSPACE PRINCIPLE

A workspace should be introduced only when repository complexity justifies it.

Do not split the system into dozens of packages prematurely.

---

# 21. PYTHON PACKAGE BOUNDARIES

Package boundaries should follow JAS architecture boundaries rather than arbitrary code size.

---

# 22. PYTHON VERSION

The Python version must be defined in:

```text
pyproject.toml
```

and represented in Version Lock.

---

# 23. PYTHON VERSION CONSISTENCY

Developer:

```text
Python
```

CI:

```text
Python
```

Docker:

```text
Python
```

and Bootstrap:

```text
Python
```

must remain within the approved support policy.

---

# 24. PYTHON VERSION FILE

Where useful:

```text
.python-version
```

may define the default development Python version.

uv supports `.python-version` for selecting the project's default Python version. 

---

# 25. PYTHON BUILD BACKEND

Python package builds must use a standards-compliant build backend.

The exact backend is selected through the Approved Stack and Version Lock.

---

# 26. PYTHON ARTIFACTS

Python distributable components may produce:

```text
Wheel
Source Distribution
```

---

# 27. PYTHON BUILD

Python package builds should be performed using the approved project tooling.

uv supports building source distributions and wheels through `uv build`. 

---

# 28. REQUIREMENTS.TXT

`requirements.txt` is not the canonical project dependency source.

---

# 29. REQUIREMENTS.TXT USE

It may be generated for compatibility with external systems when required.

uv can export locked dependencies to `requirements.txt`. 

---

# 30. MULTIPLE PYTHON LOCK SOURCES

The project must avoid maintaining competing authoritative dependency definitions.

Preferred:

```text
pyproject.toml
+
uv.lock
```

rather than:

```text
pyproject.toml
+
requirements.txt
+
another lockfile
```

as independent sources of truth.

---

# 31. PYLOCK

PEP 751 `pylock.toml` may be used for interoperability when required.

It is not the primary JARVIS project lockfile.

uv supports exporting to `pylock.toml`. 

---

# 32. PYTHON DEPENDENCY SOURCES

Approved sources may include:

```text
PyPI
Approved private indexes
Approved Git repositories
Local workspace packages
```

---

# 33. GIT DEPENDENCIES

Git dependencies are allowed conditionally.

They must be pinned to immutable revisions where possible.

---

# 34. BRANCH DEPENDENCIES

Dependencies pointing to:

```text
main
master
develop
```

must not be used in production lock state without resolution to a specific immutable revision.

uv can lock Git dependencies to commit SHAs. 

---

# 35. LOCAL PATH DEPENDENCIES

Local path dependencies may be used for workspace development.

Production artifacts must not accidentally depend on developer-local paths.

---

# 36. PRIVATE PACKAGE REGISTRIES

Private registries may be used where required.

Credentials must never be embedded in:

```text
pyproject.toml
Dockerfile
lockfile
source code
```

---

# 37. PYTHON OPTIONAL DEPENDENCIES

Optional features should use dependency groups/extras rather than installing every possible feature into the base environment.

---

# 38. JARVIS OPTIONAL COMPONENTS

Potential optional groups include:

```text
voice
vision
browser
gpu
development
testing
evaluation
```

---

# 39. DEVELOPMENT DEPENDENCIES

Development-only tools must be separated from production runtime dependencies.

---

# 40. TEST DEPENDENCIES

Testing dependencies should not unnecessarily become production dependencies.

---

# 41. NODE / TYPESCRIPT TOOLCHAIN

Frontend development may use:

```text
Node.js
TypeScript
```

according to the approved frontend architecture.

---

# 42. NODE VERSION

The Node.js version must be explicitly version-locked.

---

# 43. NODE VERSION FILE

Where appropriate, the repository may define:

```text
.nvmrc
```

or an equivalent supported version declaration.

The authoritative version remains the Version Lock.

---

# 44. JAVASCRIPT PACKAGE MANAGER

The exact package manager must be selected and frozen through Approved Stack + Version Lock.

Candidate tooling includes:

```text
npm
pnpm
```

but the repository must have one canonical package manager.

---

# 45. NO MIXED PACKAGE MANAGERS

A single frontend workspace must not casually mix:

```text
npm
pnpm
yarn
bun
```

as independent authorities.

---

# 46. FRONTEND LOCKFILE

The selected package manager's canonical lockfile must be committed.

---

# 47. LOCKFILE AUTHORITY

The frontend lockfile is authoritative for exact dependency resolution.

---

# 48. CI INSTALLATION

CI must use the package manager's immutable/frozen installation mode where supported.

---

# 49. NODE_MODULES

`node_modules` must not be committed to source control.

---

# 50. PACKAGE CACHE

Package caches may be used to accelerate builds.

They must not override lockfile correctness.

---

# 51. NATIVE TOOLCHAIN

JARVIS may require native dependencies because of:

```text
Computer Vision
Audio
CUDA
GPU acceleration
Browser dependencies
Performance-critical code
```

---

# 52. NATIVE LANGUAGES

Potential native languages:

```text
C
C++
Rust
```

may be used where justified.

---

# 53. NATIVE CODE PRINCIPLE

Native code must not be introduced merely for performance claims.

There must be a measurable reason.

---

# 54. NATIVE BUILD SYSTEM

The native build system must be explicitly documented per component.

---

# 55. C/C++ BUILD

Possible build systems include:

```text
CMake
Ninja
MSVC
GCC
Clang
```

but only approved combinations may become production requirements.

---

# 56. RUST BUILD

If Rust is introduced:

```text
Cargo
Cargo.lock
```

become the canonical Rust dependency/build system.

---

# 57. RUST LOCKFILE

Application/binary Rust components should commit `Cargo.lock`.

---

# 58. CUDA TOOLCHAIN

GPU-specific components must define:

```text
CUDA Toolkit
GPU Driver
Compiler
Architecture
Runtime Compatibility
```

---

# 59. CUDA VERSION

CUDA versions must be included in Version Lock when they affect runtime/build behavior.

---

# 60. GPU BUILD MATRIX

GPU artifacts must define supported:

```text
GPU architecture
CUDA version
Driver range
Operating system
Python version
```

---

# 61. NATIVE ABI

Native dependencies must account for ABI compatibility.

---

# 62. WINDOWS NATIVE BUILD

Windows builds may require:

```text
MSVC
Windows SDK
CMake
Ninja
```

depending on component requirements.

---

# 63. LINUX NATIVE BUILD

Linux builds may use:

```text
GCC
Clang
CMake
Ninja
```

depending on component requirements.

---

# 64. CROSS-COMPILATION

Cross-compilation is allowed only when explicitly required.

---

# 65. NATIVE ARTIFACT REPRODUCIBILITY

Native builds must record:

```text
Compiler
Compiler Version
SDK
Build Flags
Target Architecture
Dependency Versions
```

---

# 66. BUILD FLAGS

Production build flags must be explicit and version-controlled.

---

# 67. DEBUG VS RELEASE

Native components must distinguish:

```text
Debug
Release
RelWithDebInfo
```

or equivalent configurations.

---

# 68. BUILD CONFIGURATION

Build configurations must not depend on undocumented developer machine settings.

---

# 69. ENVIRONMENT VARIABLES

Build-affecting environment variables must be documented.

---

# 70. CONTAINER TOOLCHAIN

Docker is the canonical container packaging technology.

---

# 71. BUILDKIT

Docker BuildKit / Buildx is the approved build engine.

Docker documents BuildKit/Buildx as the modern build path and provides support for multi-stage builds, multi-platform builds, caching and attestations. 

---

# 72. DOCKERFILE

Container images must have explicit Dockerfiles unless another approved build mechanism is documented.

---

# 73. MULTI-STAGE BUILDS

Multi-stage builds should be used when they reduce runtime image size and attack surface.

Docker explicitly supports multi-stage builds for producing smaller, cleaner images. 

---

# 74. BUILD STAGES

Typical stages:

```text
base
↓
dependencies
↓
build
↓
test
↓
runtime
```

---

# 75. BUILD CONTEXT

Docker build contexts must remain minimal.

---

# 76. DOCKERIGNORE

A `.dockerignore` file should exclude:

```text
.git
.venv
node_modules
tests where unnecessary
local caches
secrets
artifacts
```

where appropriate.

Docker recommends keeping build contexts small and using `.dockerignore`. 

---

# 77. BASE IMAGE

Base images must be approved and version-controlled.

---

# 78. BASE IMAGE PINNING

Production base images should be pinned to explicit versions.

---

# 79. IMAGE DIGEST

For high-assurance production deployments, base images should be pinned to immutable digests.

---

# 80. `latest`

Production builds must not rely on:

```text
latest
```

as an implicit version.

---

# 81. PACKAGE INSTALLATION IN DOCKER

Package installation must consume lockfiles where supported.

---

# 82. DOCKER PYTHON INSTALL

Python dependencies should be installed from locked dependency state.

---

# 83. DOCKER NODE INSTALL

Node dependencies should use the selected package manager's frozen/immutable installation mode.

---

# 84. NATIVE DEPENDENCIES

OS-level dependencies must be explicitly versioned where the distribution/package manager supports it.

---

# 85. APT / APK / DNF

Distribution package managers may be used inside containers.

Their repositories and versions must be controlled as far as practical.

---

# 86. PACKAGE REPOSITORY DRIFT

Unpinned OS package repositories can introduce non-reproducible builds.

---

# 87. REPRODUCIBLE CONTAINER BUILD

A container build should be reproducible from:

```text
Dockerfile
+
Source
+
Lockfiles
+
Base Image
+
Build Configuration
```

---

# 88. DOCKER CACHE

Build cache is allowed and encouraged for performance.

Docker's cache is layer-based; changing a layer can invalidate downstream layers. 

---

# 89. CACHE ≠ SOURCE OF TRUTH

Cache must never be treated as dependency authority.

---

# 90. CACHE INVALIDATION

CI must provide a clean-build mode.

---

# 91. CLEAN BUILD

A clean build should be periodically executed without cached layers.

Docker supports `--no-cache` and `--no-cache-filter` for controlled cache invalidation. 

---

# 92. CACHE MOUNTS

Build cache mounts may accelerate package installation.

Docker documents cache mounts as a mechanism for reusing package-download caches between builds. 

---

# 93. EXTERNAL BUILD CACHE

CI may use remote/external cache backends.

---

# 94. CACHE SECURITY

Caches must not contain secrets.

---

# 95. BUILD SECRETS

Secrets required during builds must use build-secret mechanisms rather than embedding them in image layers.

---

# 96. BUILD ARGUMENTS

Secrets must not be passed as ordinary build arguments.

---

# 97. BUILD PROVENANCE

Production images should support build provenance/attestation.

Docker Buildx supports provenance metadata and attestations. 

---

# 98. SBOM

Production container artifacts should generate SBOMs where practical.

Docker Buildx/Compose support SBOM attestations. 

---

# 99. SBOM FORMAT

CycloneDX is approved for software inventory interoperability.

---

# 100. PYTHON SBOM

uv can export dependency information to CycloneDX format. 

---

# 101. ARTIFACT PROVENANCE

Artifacts should be traceable to:

```text
Git Commit
Build ID
Toolchain
Dependency Lock
Builder
Timestamp
```

---

# 102. SOURCE DATE EPOCH

Reproducible build workflows should control timestamps where supported.

Docker documents `SOURCE_DATE_EPOCH` as relevant to reproducible build timestamps and cache behavior. 

---

# 103. TIMESTAMP POLICY

Build timestamps should not introduce unnecessary nondeterminism.

---

# 104. BUILD ENVIRONMENT

Build environments should be isolated from arbitrary developer machine state.

---

# 105. CI BUILDER

Release artifacts should be built in controlled CI environments.

---

# 106. LOCAL BUILDS

Local builds remain supported for development.

---

# 107. LOCAL ≠ RELEASE

A developer's local artifact is not automatically a release artifact.

---

# 108. RELEASE BUILDER

Production artifacts must be produced by the approved release pipeline.

---

# 109. BUILD REPRODUCTION

A release artifact should be reproducible or independently verifiable from the locked build inputs.

---

# 110. DEPENDENCY RESOLUTION

Dependency resolution is a controlled engineering operation.

---

# 111. RESOLUTION INPUTS

Resolution depends on:

```text
Package Requirements
Python/Node Version
OS
Architecture
Extras
Dependency Sources
```

---

# 112. RESOLUTION OUTPUT

The resolver produces:

```text
Exact Dependency Graph
```

---

# 113. RESOLUTION LOCK

The resulting graph must be committed into the appropriate lockfile.

---

# 114. UNIVERSAL PYTHON RESOLUTION

uv's universal resolution is designed to represent dependencies across operating systems, architectures and Python versions. 

---

# 115. PLATFORM MARKERS

Platform-specific dependencies must be explicit.

---

# 116. OPTIONAL PLATFORM DEPENDENCIES

Examples:

```text
Windows-only
Linux-only
CUDA-only
CPU-only
```

must be represented explicitly.

---

# 117. DEPENDENCY CONFLICTS

Dependency conflicts must be resolved before approval.

---

# 118. OVERRIDES

Dependency overrides should be rare and documented.

---

# 119. PATCHING DEPENDENCIES

Local patches to third-party dependencies require explicit architecture and security review.

---

# 120. VENDORED DEPENDENCIES

Vendoring is allowed only when justified.

---

# 121. VENDORING CRITERIA

Potential reasons:

```text
Security
Reproducibility
Unavailable Upstream
Required Patch
Offline Deployment
```

---

# 122. VENDORED LICENSES

Vendored code must retain required license notices.

---

# 123. SUBMODULES

Git submodules are discouraged unless required for a specific upstream dependency.

---

# 124. GIT SUBMODULE PINNING

If used, submodules must point to immutable commits.

---

# 125. BINARY DEPENDENCIES

Prebuilt binaries must be:

```text
Versioned
Authenticated
Checksum-verified
Source-documented
```

---

# 126. CHECKSUMS

Important downloaded artifacts should have checksums.

---

# 127. HASH VERIFICATION

Bootstrap should verify artifact integrity where checksum data is available.

---

# 128. PACKAGE SIGNATURES

Package/repository signature verification should be used where supported.

---

# 129. TLS

Package retrieval must use secure transport.

---

# 130. INSECURE REGISTRIES

Untrusted HTTP package sources are prohibited in production builds.

---

# 131. TRUSTED SOURCES

Approved package indexes and registries must be defined.

---

# 132. PACKAGE SOURCE POLICY

A dependency is not approved merely because it is downloadable.

---

# 133. SUPPLY CHAIN

Package management must integrate with:

```text
14_SECURITY_STACK.md
23_LICENSE_AND_COMPLIANCE.md
```

---

# 134. DEPENDENCY VULNERABILITY

Dependencies must be periodically scanned.

---

# 135. MALICIOUS PACKAGE RISK

New dependencies must undergo supply-chain evaluation.

---

# 136. MAINTAINER RISK

Dependency health includes:

```text
Maintainer
Release Activity
Security History
Community
```

---

# 137. TRANSITIVE DEPENDENCIES

Transitive dependencies are part of the security boundary.

---

# 138. TRANSITIVE LOCKING

The lockfile must represent the complete resolved dependency graph.

---

# 139. DIRECT VS TRANSITIVE

Approved Software Matrix should distinguish:

```text
Direct Dependency
Transitive Dependency
System Dependency
Build Dependency
```

---

# 140. BUILD DEPENDENCIES

Build-only dependencies must not be copied into runtime images unnecessarily.

---

# 141. RUNTIME MINIMIZATION

Production images should contain only required runtime components.

---

# 142. DEVELOPMENT TOOLS

Tools such as:

```text
Formatter
Linter
Type Checker
Test Runner
Profiler
```

should remain development/CI dependencies unless runtime execution requires them.

---

# 143. BUILD TOOLCHAIN VERSIONING

Every build-critical tool must have a supported version policy.

---

# 144. TOOLCHAIN COMPONENTS

Potential build-critical components:

```text
Python
uv
Node
Package Manager
CMake
Ninja
Compiler
CUDA
Docker
Buildx
```

---

# 145. TOOLCHAIN LOCK

These versions feed into:

```text
Version Lock
```

---

# 146. TOOLCHAIN BOOTSTRAP

Bootstrap must be able to:

```text
Detect
Validate
Install
Select
```

required toolchain components where supported.

---

# 147. BOOTSTRAP AUTHORITY

Bootstrap must not silently upgrade an approved toolchain version.

---

# 148. BOOTSTRAP VERSION MISMATCH

If an incompatible toolchain is detected:

```text
BOOTSTRAP BLOCKED
```

or a clearly defined remediation path must be presented.

---

# 149. TOOLCHAIN AUTO-UPGRADE

Automatic major-version upgrades are prohibited.

---

# 150. MINOR/PATCH UPGRADES

Minor/patch upgrades require Version Lock updates.

---

# 151. TOOLCHAIN INSTALLER

The installation mechanism itself must be versioned and auditable.

---

# 152. CI TOOLCHAIN

CI must use the same approved toolchain versions as release builds.

---

# 153. DEV/CI PARITY

Development and CI environments should minimize unnecessary differences.

---

# 154. STAGING/PRODUCTION PARITY

Staging should use the same build artifacts as production.

---

# 155. BUILD ONCE

Preferred release pattern:

```text
Build Once
↓
Test Artifact
↓
Promote Artifact
```

rather than rebuilding independently for every environment.

---

# 156. ARTIFACT PROMOTION

```text
Development
     ↓
CI
     ↓
Release Candidate
     ↓
Staging
     ↓
Production
```

---

# 157. ARTIFACT IMMUTABILITY

Released artifacts must be immutable.

---

# 158. IMAGE TAGGING

Images should have:

```text
Semantic Version
Git Revision
Immutable Digest
```

traceability.

---

# 159. IMAGE DIGEST

Production deployments should reference immutable image digests when practical.

---

# 160. PACKAGE VERSIONING

JARVIS components should use semantic versioning where applicable.

---

# 161. INTERNAL PACKAGES

Internal packages may use coordinated release versions.

---

# 162. MONOREPO VERSIONING

If JARVIS remains a monorepo, package versions should not be introduced merely for appearance.

---

# 163. BUILD METADATA

Artifacts should expose build metadata.

Example:

```text
Version
Commit
Build ID
Build Time
Toolchain
```

---

# 164. BUILD LABELS

Container images may include OCI labels for provenance.

---

# 165. SOURCE REVISION

Every production artifact must identify source revision.

---

# 166. REPOSITORY CLEANLINESS

Build outputs must not pollute source directories.

---

# 167. ARTIFACT DIRECTORIES

Conceptually:

```text
dist/
build/
artifacts/
```

must be controlled and ignored where appropriate.

---

# 168. CACHE DIRECTORIES

Caches should not be committed.

Examples:

```text
.venv/
__pycache__/
node_modules/
.pytest_cache/
Docker cache
```

---

# 169. GITIGNORE

Repository ignore rules must cover generated artifacts and local environments.

---

# 170. BUILD CONTEXT CLEANLINESS

Only necessary files should enter container build contexts.

---

# 171. BUILD GRAPH

The repository should eventually model:

```text
Source
 ↓
Package
 ↓
Build
 ↓
Test
 ↓
Artifact
```

dependencies explicitly.

---

# 172. BUILD TARGETS

Build targets should correspond to meaningful deliverables.

Potential targets:

```text
backend
frontend
worker
agent-runtime
browser-runtime
mcp-runtime
cli
```

---

# 173. BUILD TARGET NAMING

Targets must have stable names.

---

# 174. MULTI-SERVICE BUILDS

Docker Compose may coordinate multiple JARVIS services.

Docker Compose supports explicit build definitions, dependencies and cache configuration. 

---

# 175. COMPOSE DEVELOPMENT

Compose may be used for local integration environments.

---

# 176. COMPOSE PRODUCTION

Production Compose use is conditional on deployment architecture.

It is not automatically the final production orchestrator.

---

# 177. BUILD ORCHESTRATION

A repository-level command interface should eventually provide:

```text
build
test
lint
typecheck
package
image
verify
```

commands.

---

# 178. SINGLE ENTRY POINT

Where practical, developers should not need to memorize dozens of package-manager-specific commands.

---

# 179. BUILD WRAPPER

A controlled build wrapper may abstract:

```text
uv
npm/pnpm
Docker
CMake
```

without hiding important errors.

---

# 180. MAKE / TASK RUNNER

A task runner may be introduced if repository complexity justifies it.

---

# 181. TASK RUNNER STATUS

```text
CONDITIONALLY APPROVED
```

until the repository's actual needs are known.

---

# 182. OVER-ENGINEERING RULE

Do not introduce:

```text
Bazel
Buck
Pants
Nx
Turborepo
```

or equivalent monolithic build orchestration merely because JARVIS is large.

---

# 183. BUILD SYSTEM COMPLEXITY

The build system must remain simpler than the application it builds.

---

# 184. BUILD FAILURE

Build failures must fail loudly.

---

# 185. SILENT FALLBACK

Build tools must not silently substitute incompatible versions.

---

# 186. OPTIONAL COMPONENT FAILURE

Optional components may fail independently only if architecture explicitly defines them as optional.

---

# 187. REQUIRED COMPONENT FAILURE

Required component failure blocks the build.

---

# 188. BUILD VALIDATION

Before producing a release artifact:

```text
Dependency Lock Valid
+
Toolchain Valid
+
Source Valid
+
Tests Valid
```

---

# 189. STATIC VALIDATION

Build pipeline should execute:

```text
Formatting
Lint
Type Checking
```

where applicable.

---

# 190. TEST VALIDATION

Build pipeline must execute relevant tests.

---

# 191. SECURITY VALIDATION

Build pipeline must execute dependency and secret scanning.

---

# 192. LICENSE VALIDATION

Build pipeline should validate dependency licensing.

---

# 193. SBOM GENERATION

Release pipeline should generate SBOM data.

---

# 194. PROVENANCE GENERATION

Release pipeline should generate build provenance where supported.

---

# 195. ARTIFACT VALIDATION

Artifacts must be tested before promotion.

---

# 196. CLEAN-ROOM BUILD

Periodic clean builds should validate dependency completeness.

---

# 197. OFFLINE BUILD

Where JARVIS claims offline/local operation, required artifacts should support controlled offline installation after acquisition.

---

# 198. AIR-GAPPED FUTURE

Air-gapped deployment is:

```text
FUTURE / CONDITIONAL
```

and requires additional artifact mirroring infrastructure.

---

# 199. MIRRORING

Approved package sources may eventually be mirrored for:

```text
Reliability
Security
Offline Deployment
Performance
```

---

# 200. PACKAGE MIRROR

Package mirroring must preserve package provenance.

---

# 201. MODEL ARTIFACTS

Models are not ordinary dependencies.

They must be managed through:

```text
19_APPROVED_MODELS.md
```

and corresponding model locks.

---

# 202. MODEL BUILD RELATION

The build system may package model configuration but should not necessarily embed large model weights into application images.

---

# 203. MODEL DOWNLOAD

Model acquisition belongs primarily to Bootstrap / Model Management.

---

# 204. MODEL VERSION

Model version/revision must be immutable in production configuration.

---

# 205. MCP ARTIFACTS

Approved MCP servers may have independent package/build systems.

---

# 206. MCP VERSION

MCP server versions must be represented in the appropriate lock/manifest layer.

---

# 207. BROWSER ARTIFACTS

Browser binaries and dependencies must be controlled separately from application packages where required.

---

# 208. PLAYWRIGHT BROWSERS

Browser binaries must be installed through the approved browser dependency mechanism and versioned consistently with the test/runtime stack.

---

# 209. AUDIO ARTIFACTS

Audio models and native codecs must follow approved artifact/version policies.

---

# 210. VISION ARTIFACTS

Vision model weights and native GPU libraries must be tracked independently.

---

# 211. CUDA CONTAINERS

GPU images must explicitly declare CUDA/runtime compatibility.

---

# 212. GPU IMAGE PINNING

CUDA base images must be pinned.

---

# 213. GPU RUNTIME VALIDATION

System Verification must confirm:

```text
GPU
Driver
CUDA
Runtime
Model
```

compatibility.

---

# 214. WINDOWS + DOCKER

Windows development may use Docker Desktop where appropriate.

---

# 215. LINUX CI

Linux should be the primary standardized CI environment for containerized builds unless a component specifically requires another platform.

---

# 216. WINDOWS CI

Windows CI is required for components claiming native Windows support.

---

# 217. MACOS

macOS support is conditional unless explicitly required by JAS.

---

# 218. CROSS-PLATFORM DEPENDENCIES

Platform-specific dependencies must not be hidden inside generic requirements.

---

# 219. ENVIRONMENT DETECTION

Bootstrap should detect:

```text
OS
Architecture
Python
Node
Docker
GPU
CUDA
Compiler
```

---

# 220. TOOLCHAIN REPORT

Bootstrap should produce a report:

```text
Tool
Detected Version
Required Version
Status
Remediation
```

---

# 221. TOOLCHAIN COMPLIANCE

Example:

```text
Python       ✓
uv           ✓
Node         ✓
PackageMgr   ✓
Docker       ✓
GPU          ✓
CUDA         ✓
Compiler     ✓
```

---

# 222. BUILD MANIFEST

Manifest must eventually identify required build tools.

---

# 223. BUILD VERSION LOCK

Version Lock must eventually contain:

```text
Python
uv
Node
Package Manager
Docker
Buildx
Compiler
CUDA
```

as applicable.

---

# 224. BOOTSTRAP ORDER

Conceptually:

```text
Environment Detection
        ↓
Toolchain Validation
        ↓
Toolchain Installation
        ↓
Dependency Resolution
        ↓
Dependency Installation
        ↓
Native Dependencies
        ↓
Browser Dependencies
        ↓
Models
        ↓
Container Build
        ↓
Verification
```

---

# 225. BOOTSTRAP FAILURE

Bootstrap must stop at the first critical dependency failure rather than continuing into a known-invalid state.

---

# 226. BOOTSTRAP IDEMPOTENCY

Running Bootstrap multiple times should produce a stable result.

---

# 227. REPAIR

Bootstrap may support repair operations:

```text
Missing Dependency
Corrupted Environment
Broken Cache
Invalid Lock
```

---

# 228. LOCKFILE REPAIR

Lockfile repair must not silently change production dependencies.

---

# 229. UPDATE WORKFLOW

Dependency update workflow:

```text
Current Lock
↓
Candidate Update
↓
Security Evaluation
↓
Compatibility Tests
↓
AI Regression
↓
Performance Regression
↓
Approval
↓
New Lock
```

---

# 230. AUTOMATIC DEPENDENCY UPDATES

Fully automatic production dependency updates are:

```text
NOT APPROVED
```

---

# 231. DEPENDABOT / RENOVATE-LIKE SYSTEMS

Automated update proposals may be used.

They must create reviewable changes rather than silently modifying production.

---

# 232. MAJOR UPDATE

Major dependency updates require explicit review.

---

# 233. MINOR UPDATE

Minor updates require regression validation.

---

# 234. PATCH UPDATE

Patch updates may use a lighter approval path if security and compatibility policies permit.

---

# 235. SECURITY UPDATE

Critical security updates may follow an accelerated path.

---

# 236. UPDATE ROLLBACK

Dependency updates must be reversible through version control and lockfile restoration.

---

# 237. DEPENDENCY DIFF

Every dependency update should provide a dependency graph diff.

---

# 238. LOCKFILE REVIEW

Lockfile changes should be reviewable.

---

# 239. TRANSITIVE CHANGE REVIEW

A direct dependency update may change many transitive packages.

Those changes must be visible.

---

# 240. SUPPLY-CHAIN REVIEW

Unexpected transitive dependencies may trigger review.

---

# 241. BUILD PERFORMANCE

Build performance should be measured.

---

# 242. BUILD METRICS

Track:

```text
Dependency Resolution Time
Install Time
Compile Time
Docker Build Time
Cache Hit Rate
Artifact Size
```

---

# 243. BUILD CACHE METRICS

Track cache effectiveness.

---

# 244. CI COST

Build architecture should minimize unnecessary CI resource consumption.

---

# 245. PARALLEL BUILDS

Independent targets may build in parallel.

---

# 246. NATIVE BUILD CACHE

Native compiler caches may be used where safe.

---

# 247. PYTHON CACHE

uv's cache may accelerate dependency operations.

---

# 248. NODE CACHE

Node package caches may accelerate CI.

---

# 249. DOCKER CACHE

Docker BuildKit cache may accelerate container builds. 

---

# 250. CACHE CORRUPTION

CI must have a cache-reset path.

---

# 251. CLEAN BUILD SCHEDULE

Periodic clean builds must run to ensure cached builds do not hide missing dependencies.

---

# 252. REPRODUCIBILITY TEST

A clean environment should be able to reconstruct the artifact using:

```text
Source
+
Locks
+
Toolchain
+
Configuration
```

---

# 253. REPRODUCIBILITY LIMIT

Absolute bit-for-bit reproducibility may not be achievable for every AI/native component.

Where not possible:

```text
Verifiable provenance
+
Pinned inputs
+
Artifact hashes
```

must be used.

---

# 254. NON-DETERMINISTIC COMPONENTS

Examples:

```text
GPU kernels
Model compilation
Timestamped binaries
External provider outputs
```

require documented reproducibility boundaries.

---

# 255. BUILD DETERMINISM

Build scripts must avoid:

```text
Current Time
Randomness
Unpinned Downloads
Host-Specific Paths
```

unless explicitly required.

---

# 256. HOST PATHS

Builds must not embed developer-specific absolute paths.

---

# 257. NETWORK DEPENDENCE

Builds should minimize uncontrolled network access.

---

# 258. NETWORK RESTRICTION

Where possible, build steps should use only approved package sources.

---

# 259. NETWORK AUDIT

Build pipelines should identify external network dependencies.

---

# 260. HERMETIC BUILD

Fully hermetic builds are:

```text
FUTURE / CONDITIONAL
```

for JARVIS.

---

# 261. HERMETIC BUILD PATH

Future architecture may introduce:

```text
Artifact Mirror
+
Pinned Inputs
+
Isolated Builder
```

for high-assurance releases.

---

# 262. BUILD SECURITY

Build infrastructure is part of JARVIS's security boundary.

---

# 263. CI PERMISSIONS

CI jobs should use least privilege.

---

# 264. BUILD TOKENS

Build credentials must be scoped narrowly.

---

# 265. REGISTRY CREDENTIALS

Registry credentials must not be embedded in images.

---

# 266. PACKAGE REGISTRY CREDENTIALS

Registry credentials must be injected at runtime/build securely.

---

# 267. SECRET LEAK TESTING

Build output must be scanned for accidental secrets.

---

# 268. MALICIOUS BUILD SCRIPT

Dependency lifecycle scripts must be considered supply-chain execution.

---

# 269. PACKAGE INSTALL SCRIPTS

Package installation must be performed only from approved sources.

---

# 270. BUILD SANDBOX

High-risk third-party build steps may require isolated execution.

---

# 271. PRIVILEGED BUILDS

Privileged container builds should be avoided unless required.

---

# 272. ROOT BUILDS

Containers should minimize unnecessary root execution.

---

# 273. RUNTIME USER

Production containers should use a non-root runtime user where practical.

---

# 274. BUILD USER

Build stages may require elevated privileges, but those privileges should not leak into runtime images.

---

# 275. IMAGE MINIMIZATION

Runtime images should exclude:

```text
Compilers
Package Managers
Build Tools
Tests
Source Maps where unnecessary
```

when possible.

---

# 276. DEBUG IMAGE

Debug images may exist separately from production images.

---

# 277. DEBUG/PRODUCTION SEPARATION

Debug artifacts must not be accidentally deployed as production.

---

# 278. DEVELOPMENT IMAGE

A developer image may contain:

```text
Compiler
Debugger
Test Tools
```

---

# 279. RELEASE IMAGE

Release image should contain the minimum runtime set.

---

# 280. IMAGE TESTING

Images must undergo:

```text
Build
Scan
Test
Smoke
```

before promotion.

---

# 281. IMAGE STARTUP TEST

Verify that production images start correctly.

---

# 282. IMAGE HEALTH TEST

Verify health endpoints and dependencies.

---

# 283. IMAGE FUNCTIONAL TEST

Run critical workflows against the built image.

---

# 284. IMAGE SECURITY TEST

Scan image packages and configuration.

---

# 285. IMAGE PROVENANCE

Record image digest and build provenance.

---

# 286. COMPOSE VALIDATION

Compose configurations must be validated before deployment.

Docker Compose supports build configuration validation and provenance/SBOM options. 

---

# 287. CI PIPELINE STRUCTURE

Conceptually:

```text
Checkout
   ↓
Toolchain Setup
   ↓
Dependency Lock Validation
   ↓
Dependency Installation
   ↓
Static Checks
   ↓
Tests
   ↓
Security
   ↓
Build
   ↓
Artifact Scan
   ↓
SBOM
   ↓
Provenance
   ↓
Release
```

---

# 288. LOCK VALIDATION

CI must fail if lockfiles are inconsistent with project metadata.

---

# 289. UV LOCK VALIDATION

`uv lock --check` or an equivalent locked workflow should detect outdated Python lock state. 

---

# 290. FRONTEND LOCK VALIDATION

The selected Node package manager's frozen/immutable mode must be used in CI.

---

# 291. DOCKER BUILD VALIDATION

Docker builds should use the exact release inputs.

---

# 292. BUILD CACHE CI

CI may import/export BuildKit cache.

---

# 293. CACHE TRUST

Cache contents must not be trusted as equivalent to source verification.

---

# 294. RELEASE BUILD

Release builds should use clean or validated cache environments.

---

# 295. NIGHTLY CLEAN BUILD

A scheduled clean build should detect hidden dependency assumptions.

---

# 296. TOOLCHAIN DRIFT

CI must detect when installed toolchain versions differ from Version Lock.

---

# 297. ENVIRONMENT DRIFT

System Verification must detect environment drift.

---

# 298. DOCKER DRIFT

Base image updates must trigger controlled review.

---

# 299. COMPILER DRIFT

Compiler updates may change binary behavior and require regression testing.

---

# 300. CUDA DRIFT

CUDA updates require GPU regression testing.

---

# 301. PYTHON DRIFT

Python runtime updates require full Python regression testing.

---

# 302. NODE DRIFT

Node runtime updates require frontend regression testing.

---

# 303. PACKAGE MANAGER DRIFT

Package-manager updates may alter lockfile semantics and must be controlled.

---

# 304. LOCKFILE FORMAT DRIFT

A lockfile schema change is a toolchain compatibility event.

---

# 305. UV LOCK SCHEMA

uv lockfiles have versioned schemas; incompatible schema versions may not be readable by older uv versions. 

---

# 306. LOCKFILE MIGRATION

Lockfile format changes require:

```text
Toolchain Update
+
CI Validation
+
Developer Compatibility
```

---

# 307. BUILD SYSTEM MIGRATION

Changing package managers is an architectural decision.

---

# 308. PACKAGE MANAGER MIGRATION

Migration process:

```text
Evaluate
↓
Prototype
↓
Compatibility
↓
Migration
↓
Lock Regeneration
↓
CI
↓
Bootstrap
↓
Release
```

---

# 309. NO CASUAL MIGRATION

A developer must not replace the package manager locally and commit unrelated lockfile changes.

---

# 310. BUILD TOOL ADDITION

Every new build tool must pass Approved Stack governance.

---

# 311. TOOL JUSTIFICATION

A new build tool must answer:

```text
Why?
What problem?
Why existing tooling insufficient?
Maintenance cost?
Security?
Cross-platform?
Bootstrap impact?
```

---

# 312. BUILD TOOL REMOVAL

Unused build tools should be removed.

---

# 313. TOOLCHAIN MINIMALISM

Prefer the smallest toolchain that can satisfy JAS requirements.

---

# 314. BUILD SYSTEM ANTI-PATTERNS

The following are prohibited or strongly discouraged:

```text
Unpinned Dependencies
Latest Tags
Manual Production Installs
Committed Virtual Environments
Committed node_modules
Random Global Packages
Undocumented Compiler Flags
Developer-Specific Paths
Uncontrolled Git Dependencies
Secrets in Dockerfiles
Multiple Package Managers for One Workspace
Silent Dependency Upgrades
```

---

# 315. GLOBAL PACKAGE RULE

Global developer installations must not be required for reproducible project builds.

---

# 316. DEVELOPER MACHINE

The developer machine is an execution environment, not the source of dependency truth.

---

# 317. GLOBAL PYTHON PACKAGES

Global Python packages must not satisfy project dependencies implicitly.

---

# 318. GLOBAL NODE PACKAGES

Global Node packages must not be required for project builds.

---

# 319. SYSTEM COMPILERS

System compilers may be required for native builds but must be version-validated.

---

# 320. BOOTSTRAP TOOLCHAIN INSTALLATION

Bootstrap may install or configure:

```text
Python
uv
Node
Package Manager
Docker
Compiler
```

where supported by the environment.

---

# 321. BOOTSTRAP PLATFORM ADAPTERS

Bootstrap should use platform-specific adapters rather than scattered shell commands.

Conceptually:

```text
bootstrap/
├── windows/
├── linux/
└── common/
```

---

# 322. WINDOWS PACKAGE INSTALLER

The Windows bootstrap path may use an approved system package manager.

---

# 323. LINUX PACKAGE INSTALLER

The Linux bootstrap path may use the distribution package manager.

---

# 324. PACKAGE MANAGER ABSTRACTION

Bootstrap should abstract installation differences behind a stable interface.

---

# 325. BOOTSTRAP OUTPUT

Bootstrap should report:

```text
Installed
Already Present
Updated
Skipped
Failed
```

---

# 326. BOOTSTRAP LOGGING

All build-toolchain installation actions must be logged.

---

# 327. BOOTSTRAP AUDIT

Bootstrap should record toolchain versions after installation.

---

# 328. TOOLCHAIN SNAPSHOT

Conceptually:

```text
toolchain-report.json
```

may record:

```text
Python
uv
Node
Package Manager
Docker
Buildx
Compiler
CUDA
OS
Architecture
```

---

# 329. MANIFEST INTEGRATION

Manifest will define required toolchain components.

---

# 330. VERSION LOCK INTEGRATION

Version Lock will define exact supported versions.

---

# 331. BOOTSTRAP INTEGRATION

Bootstrap will install/validate those versions.

---

# 332. COMPLIANCE INTEGRATION

Compliance Checker will verify repository/build structure against the defined toolchain.

---

# 333. SYSTEM VERIFICATION

System Verification will verify that the complete toolchain can produce a functioning JARVIS environment.

---

# 334. BUILD VERIFICATION

Verification should include:

```text
Dependency Resolution
Build
Test
Package
Container
Startup
Health
```

---

# 335. CLEAN INSTALL VERIFICATION

A clean environment must be able to execute the documented bootstrap/build workflow.

---

# 336. DEVELOPER ONBOARDING

A new developer should be able to move from:

```text
Fresh Machine
```

to:

```text
Working JARVIS Development Environment
```

using documented bootstrap tooling.

---

# 337. ONBOARDING TARGET

The onboarding workflow should minimize undocumented manual steps.

---

# 338. DOCUMENTATION

Build commands must be documented.

---

# 339. SINGLE SOURCE

Operational build commands should eventually be exposed through a canonical repository command interface.

---

# 340. BUILD COMMAND EXAMPLES

Conceptually:

```text
jas build
jas test
jas lint
jas typecheck
jas verify
jas image
```

The exact CLI is a future implementation decision.

---

# 341. BUILD CLI STATUS

```text
CONDITIONALLY APPROVED
```

---

# 342. BUILD GRAPH DOCUMENTATION

The repository should eventually document major build dependencies.

---

# 343. BUILD ORDER

Example:

```text
Runtime
↓
Dependencies
↓
Native Libraries
↓
Application
↓
Frontend
↓
Tests
↓
Containers
```

---

# 344. FRONTEND BUILD

Frontend builds must consume the locked Node dependency graph.

---

# 345. BACKEND BUILD

Backend builds must consume the locked Python dependency graph.

---

# 346. NATIVE BUILD

Native components must consume approved compiler/toolchain versions.

---

# 347. CONTAINER BUILD

Container builds must package already validated application artifacts where practical.

---

# 348. TEST BUILD

Testing must run against the same artifacts intended for release.

---

# 349. BUILD ARTIFACT TYPES

JARVIS may produce:

```text
Python Wheels
Source Distributions
Frontend Bundles
Container Images
Native Libraries
CLI Packages
Configuration Bundles
Model Metadata
```

---

# 350. ARTIFACT STORAGE

Artifacts must be stored in approved artifact repositories.

---

# 351. ARTIFACT RETENTION

Retention policy must be defined in deployment/release architecture.

---

# 352. ARTIFACT IMMUTABILITY

Published release artifacts must not be overwritten.

---

# 353. ARTIFACT HASH

Every production artifact should have a cryptographic digest.

---

# 354. ARTIFACT SIGNING

Artifact signing is:

```text
CONDITIONALLY APPROVED
```

and recommended for future production distribution.

---

# 355. OCI ARTIFACTS

Container images should use OCI-compatible distribution mechanisms.

---

# 356. REGISTRY

The exact container registry is defined separately from the build toolchain.

---

# 357. PRIVATE REGISTRY

Private registries may be used for proprietary deployments.

---

# 358. PUBLIC REGISTRY

Public registries may be used only for approved public artifacts.

---

# 359. ARTIFACT ACCESS CONTROL

Artifact repositories must enforce appropriate access control.

---

# 360. CI ARTIFACT ACCESS

CI should use scoped credentials.

---

# 361. BUILD LOGS

Build logs should be retained according to release/observability policy.

---

# 362. LOG SECRETS

Build logs must be scanned or configured to prevent secret leakage.

---

# 363. ERROR HANDLING

Build failures should preserve enough context for diagnosis.

---

# 364. BUILD RETRY

Retries are allowed for transient infrastructure failures.

---

# 365. BUILD RETRY LIMIT

Retries must be bounded.

---

# 366. NETWORK FAILURE

Network failures should not silently cause partial dependency installation.

---

# 367. PARTIAL INSTALLATION

A failed dependency installation must leave the environment in a known state.

---

# 368. ENVIRONMENT REPAIR

Broken environments should be safely recreated rather than patched indefinitely.

---

# 369. CLEAN ENVIRONMENT PREFERENCE

When environment integrity is uncertain:

```text
Recreate
```

is preferred over undocumented manual repair.

---

# 370. DEPENDENCY ENVIRONMENT

The final environment should contain only approved dependencies.

---

# 371. EXTRANEOUS DEPENDENCIES

Extraneous packages should be detected.

uv's default project sync behavior is designed to remove packages not represented in the lockfile. 

---

# 372. ENVIRONMENT DRIFT

Environment drift must trigger remediation.

---

# 373. PACKAGE AUDIT

Dependency audit should be part of CI.

---

# 374. VULNERABILITY POLICY

Vulnerabilities must be classified according to security policy.

---

# 375. CRITICAL DEPENDENCY VULNERABILITY

Critical vulnerabilities may block release.

---

# 376. LICENSE BLOCK

License violations block release.

---

# 377. UNKNOWN LICENSE

Unknown/unverifiable licenses require review.

---

# 378. TRANSITIVE LICENSE

Transitive dependency licenses must be included in compliance analysis.

---

# 379. SBOM → LICENSE

SBOM data should support compliance analysis.

---

# 380. SBOM → SECURITY

SBOM data should support vulnerability analysis.

---

# 381. BUILD → OBSERVABILITY

Build events should integrate with deployment/release observability.

---

# 382. BUILD → TESTING

Build pipeline must integrate with `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`.

---

# 383. BUILD → SECURITY

Build pipeline must integrate with `14_SECURITY_STACK.md`.

---

# 384. BUILD → DEPLOYMENT

Build pipeline must integrate with `15_DEVOPS_AND_DEPLOYMENT_STACK.md`.

---

# 385. BUILD → VERSION LOCK

All build-critical versions must be represented in Version Lock.

---

# 386. BUILD → MANIFEST

All required build components must be represented in Manifest.

---

# 387. BUILD → BOOTSTRAP

Bootstrap must know how to provision the build toolchain.

---

# 388. BUILD → COMPLIANCE

Compliance Checker must detect toolchain deviations.

---

# 389. BUILD → VERIFICATION

System Verification must prove that the build toolchain can produce a valid system.

---

# 390. BUILD LIFECYCLE

```text
Research
   ↓
Selection
   ↓
Approval
   ↓
Version Lock
   ↓
Bootstrap
   ↓
Build
   ↓
Test
   ↓
Artifact
   ↓
Scan
   ↓
Sign / Attest
   ↓
Release
   ↓
Deploy
```

---

# 391. DEPENDENCY LIFECYCLE

```text
Candidate
   ↓
Evaluation
   ↓
Approved
   ↓
Locked
   ↓
Installed
   ↓
Tested
   ↓
Released
   ↓
Supported
   ↓
Deprecated
   ↓
Removed
```

---

# 392. TOOLCHAIN LIFECYCLE

```text
Candidate
   ↓
Approved
   ↓
Version Locked
   ↓
Bootstrap Supported
   ↓
CI Supported
   ↓
Production Supported
   ↓
Maintenance
   ↓
Deprecated
   ↓
Removed
```

---

# 393. BUILD SECURITY LIFECYCLE

```text
Source
 ↓
Dependency
 ↓
Resolve
 ↓
Lock
 ↓
Build
 ↓
Scan
 ↓
SBOM
 ↓
Provenance
 ↓
Test
 ↓
Release
```

---

# 394. REPRODUCIBILITY MODEL

```text
                    SOURCE
                       │
                       ▼
                ┌─────────────┐
                │  Lockfiles  │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │ Toolchain   │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │    Build    │
                └──────┬──────┘
                       │
                       ▼
                ┌─────────────┐
                │   Artifact  │
                └──────┬──────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
          Digest             Provenance
```

---

# 395. JARVIS BUILD ARCHITECTURE

```text
                         JARVIS
                            │
                ┌───────────┴───────────┐
                │                       │
             Backend                Frontend
                │                       │
              Python              Node/TS
                │                       │
               uv                  Package Manager
                │                       │
             uv.lock              Node Lockfile
                │                       │
                └───────────┬───────────┘
                            │
                            ▼
                     Native Components
                            │
                  ┌─────────┴─────────┐
                  │                   │
                 C++                CUDA
                  │                   │
                  └─────────┬─────────┘
                            │
                            ▼
                       Docker Buildx
                            │
                     ┌──────┴──────┐
                     │             │
                   Image        Artifacts
                     │             │
                     └──────┬──────┘
                            ▼
                         Testing
                            │
                            ▼
                        Security
                            │
                            ▼
                          SBOM
                            │
                            ▼
                       Provenance
                            │
                            ▼
                         Release
```

---

# 396. BOOTSTRAP TOOLCHAIN ARCHITECTURE

```text
                 BOOTSTRAP
                     │
                     ▼
            Environment Detection
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       Python       Node       Docker
          │          │          │
          ▼          ▼          ▼
         uv       Package     Buildx
                    Manager
          │          │          │
          └──────────┼──────────┘
                     ▼
              Native Toolchain
                     │
              ┌──────┴──────┐
              ▼             ▼
             C++           CUDA
              │             │
              └──────┬──────┘
                     ▼
              Dependency Install
                     │
                     ▼
                   Build
                     │
                     ▼
                 Verification
```

---

# 397. CI BUILD ARCHITECTURE

```text
Git Push
   │
   ▼
Checkout
   │
   ▼
Toolchain Validation
   │
   ▼
Lock Validation
   │
   ▼
Dependency Install
   │
   ▼
Static Checks
   │
   ▼
Tests
   │
   ▼
Security
   │
   ▼
Build
   │
   ▼
Container
   │
   ▼
SBOM / Provenance
   │
   ▼
Artifact
   │
   ▼
Release Gate
```

---

# 398. DEVELOPMENT BUILD

```text
Developer
   ↓
Bootstrap
   ↓
Toolchain
   ↓
uv / Node Package Manager
   ↓
Local Dependencies
   ↓
Fast Tests
   ↓
Application
```

---

# 399. PRODUCTION BUILD

```text
Source Commit
   ↓
Locked Toolchain
   ↓
Locked Dependencies
   ↓
Clean / Validated Builder
   ↓
Build
   ↓
Full Tests
   ↓
Security
   ↓
SBOM
   ↓
Provenance
   ↓
Artifact Digest
   ↓
Release
```

---

# 400. BUILD QUALITY GATES

Every release must satisfy:

```text
Toolchain Valid
+
Lockfiles Valid
+
Dependencies Resolved
+
Tests Passed
+
Security Passed
+
Build Successful
+
Artifact Verified
```

---

# 401. HARD BUILD GATES

The following are release blockers:

```text
Missing Lockfile
Invalid Lockfile
Unapproved Dependency
Toolchain Mismatch
Critical Vulnerability
License Violation
Build Failure
Critical Test Failure
Corrupted Artifact
Missing Required Provenance
```

---

# 402. SOFT BUILD GATES

Potential warning conditions:

```text
Cache Miss
Build Slower Than Baseline
Non-critical Dependency Warning
Optional Component Failure
```

---

# 403. BUILD PRINCIPLE

> **The dependency graph must be known before the production artifact is built.**

---

# 404. REPRODUCIBILITY PRINCIPLE

> **The same locked inputs must produce an equivalent supported artifact.**

---

# 405. SECURITY PRINCIPLE

> **The build system is part of the security boundary.**

---

# 406. SIMPLICITY PRINCIPLE

> **Use the smallest toolchain that can reliably build the architecture.**

---

# 407. BOOTSTRAP PRINCIPLE

> **If Bootstrap cannot reproduce the required toolchain, the toolchain is not operationally complete.**

---

# 408. LOCK PRINCIPLE

> **A package version that is not represented in the appropriate lock mechanism is not a production dependency.**

---

# 409. UPDATE PRINCIPLE

> **Dependency updates are engineering changes, not routine background activity.**

---

# 410. ARTIFACT PRINCIPLE

> **A release artifact must be traceable to its source, toolchain and dependency state.**

---

# 411. CACHE PRINCIPLE

> **Cache accelerates builds; cache never defines what should be built.**

---

# 412. PLATFORM PRINCIPLE

> **Platform-specific behavior must be explicit rather than accidental.**

---

# 413. FINAL APPROVED STACK

```text
============================================================
      JARVIS BUILD TOOLCHAIN & PACKAGE MANAGEMENT v1
============================================================

PYTHON
------------------------------------------------------------
Project Management       uv
Dependency Resolution    uv
Environment              uv
Lockfile                 uv.lock
Project Metadata         pyproject.toml
Status                   APPROVED

============================================================

JAVASCRIPT / TYPESCRIPT
------------------------------------------------------------
Runtime                  Node.js
Package Manager          Approved ecosystem manager
Lockfile                 Native package-manager lockfile
Status                   APPROVED
Exact manager            Version Lock / implementation phase

============================================================

NATIVE
------------------------------------------------------------
C/C++                    Approved compiler toolchain
Build                    CMake / Ninja where justified
Rust                     Cargo if Rust is introduced
CUDA                     Version-locked NVIDIA toolchain
Status                   APPROVED / CONDITIONAL BY COMPONENT

============================================================

CONTAINERS
------------------------------------------------------------
Container Engine         Docker
Build Engine             BuildKit / Buildx
Composition              Docker Compose
Multi-stage              APPROVED
Multi-platform           APPROVED
Build Cache              APPROVED
SBOM                     APPROVED
Provenance               APPROVED
Status                   APPROVED

============================================================

REPRODUCIBILITY
------------------------------------------------------------
Lockfiles                REQUIRED
Version Lock             REQUIRED
Pinned Base Images       REQUIRED FOR RELEASE
Artifact Digest          REQUIRED
Build Provenance         REQUIRED WHERE SUPPORTED
Clean Build              REQUIRED PERIODICALLY

============================================================

SECURITY
------------------------------------------------------------
Dependency Audit         REQUIRED
Secret Scanning          REQUIRED
License Validation       REQUIRED
SBOM                     REQUIRED FOR RELEASE ARTIFACTS
Supply-chain Review      REQUIRED
Build Secrets            SECURE INJECTION ONLY

============================================================

BOOTSTRAP
------------------------------------------------------------
Environment Detection    REQUIRED
Toolchain Validation     REQUIRED
Toolchain Provisioning   REQUIRED
Dependency Installation  REQUIRED
Build Validation         REQUIRED
Verification             REQUIRED

============================================================

CORE RULE
------------------------------------------------------------

NO:

Developer-only dependency
Unpinned production dependency
Uncontrolled package source
Latest-tag production image
Manual release build
Secret embedded in build
Untracked toolchain
Untracked native dependency
Silent dependency upgrade

============================================================

BUILD CHAIN
------------------------------------------------------------

JAS
 ↓
Approved Stack
 ↓
Version Lock
 ↓
Manifest
 ↓
Bootstrap
 ↓
Toolchain Validation
 ↓
Dependency Resolution
 ↓
Build
 ↓
Testing
 ↓
Security
 ↓
SBOM
 ↓
Provenance
 ↓
Artifact
 ↓
Release
 ↓
Deployment

============================================================
```

# 414. SUMMARY

`18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md` ile artık JARVIS'in **"hangi dependency var?"** sorusunun yanında:

```text
hangi Python?
hangi package manager?
hangi lockfile?
hangi Node?
hangi compiler?
hangi CUDA?
hangi Docker builder?
hangi base image?
hangi build cache?
hangi artifact?
hangi provenance?
```

sorularının da mimari yeri belirlenmiş oluyor.

En önemli kararlar:

- **Python tarafında `uv + pyproject.toml + uv.lock`** temel yapı olarak onaylandı. uv'nin lockfile'ı exact dependency state'i tutuyor ve cross-platform resolution destekliyor. 
- **Node/TypeScript tarafında tek bir canonical package manager + native lockfile** kullanılacak; hangi manager'ın kesin seçileceği frontend/Approved Stack kararlarının Version Lock aşamasında kesinleştirilecek.
- **Native/CUDA toolchain**, uygulama dependency'lerinden ayrı fakat Version Lock'a bağlı olacak.
- **Docker BuildKit/Buildx**, container build'in resmi altyapısı olacak; multi-stage, cache, multi-platform ve provenance/SBOM mekanizmaları kullanılabilecek. 
- **Cache hiçbir zaman source of truth olmayacak.**
- **Production artifact = source + lockfiles + toolchain + build configuration** ilişkisiyle izlenebilir olacak.
- Bootstrap artık yalnızca dependency installer değil, aynı zamanda **toolchain provisioning + validation system** olacak.

Böylece Approved Stack'in 18. dosyasıyla birlikte zincirin kritik kısmı tamamlanmış oluyor:

```text
07 Browser
08 Voice
09 Vision
10 Frontend
11 Backend
12 Plugins
13 MCP
14 Security
15 DevOps
16 Observability
17 Testing / QA
18 Build / Package Management
        ↓
19 Approved Models
```

**Sıradaki dosya: `19_APPROVED_MODELS.md`.** Bu dosya diğerlerinden biraz daha kritik olacak; çünkü burada artık framework değil, JARVIS'in gerçekten kullanacağı **LLM, embedding, reranker, STT, TTS, vision, OCR ve diğer model sınıflarının seçim, lisans, VRAM/RAM, local/cloud, latency, quantization, fallback ve version/revision locking politikası** belirlenecek.