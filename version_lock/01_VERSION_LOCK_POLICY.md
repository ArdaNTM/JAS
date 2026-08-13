# VERSION LOCK POLICY

**Document ID:** JAS-VLOCK-001

**Version:** 1.0

**Status:** APPROVED

**Classification:** Version Governance Specification

**Layer:** Version Lock

**Architecture:** JAS v1

---

# 1. Purpose

This document defines the official Version Lock governance system for JAS Version 1.

The purpose of Version Lock is to transform approved architectural technologies, software components, models, MCP servers, runtime environments, and external artifacts into a deterministic and reproducible production dependency state.

Version Lock defines:

- Which exact versions are approved for production use
- Which immutable artifact identities are authoritative
- How versions are selected
- How revisions are identified
- How artifact integrity is verified
- How platform-specific versions are represented
- How model versions are locked
- How MCP servers are locked
- How dependencies are upgraded
- How locked components are rolled back
- How historical lock states are preserved
- How Version Lock integrates with Manifest, Bootstrap, and Architecture Compliance Checker

Version Lock is a governance layer.

It is not a package manager, dependency resolver, installation system, model registry, or runtime.

---

# 2. Scope

This policy applies to every external or internal component that participates in a JAS production environment.

The scope includes:

- Programming language runtimes
- Runtime implementations
- Python packages
- JavaScript/TypeScript packages
- Package managers
- Build tools
- Native toolchains
- Databases
- Infrastructure services
- Container runtimes
- Container images
- Browser binaries
- Browser automation frameworks
- AI runtimes
- AI models
- Embedding models
- Reranking models
- Speech models
- Vision models
- OCR systems
- TTS systems
- MCP SDKs
- MCP servers
- Security tooling
- Observability tooling
- Testing tooling
- Artifact signing systems
- Supply-chain tooling
- Internal JAS components

---

# 3. Authority

Version Lock operates below architectural approval and above installation and deployment.

The authority hierarchy is:

```text
JAS v1 Architecture
        ↓
Approved Stack
        ↓
Approved Software Matrix
        ↓
Approved Models
        ↓
Approved MCP Servers
        ↓
Version Lock
        ↓
Manifest
        ↓
Bootstrap
        ↓
Runtime
```

Version Lock SHALL NOT approve a technology that has not already received the required architectural approval.

Version Lock SHALL only select an exact implementation from an approved technology family.

Version Lock SHALL NOT override architectural decisions.

---

# 4. Relationship With Approved Stack

The Approved Stack answers:

> What technologies are allowed?

Version Lock answers:

> Which exact versions and artifacts of those technologies are used?

Therefore:

```text
Approved Stack
    =
Technology Approval

Version Lock
    =
Exact Production Identity
```

An upstream release SHALL NOT become part of Version Lock merely because it is newer.

A component SHALL first satisfy the relevant approval, compatibility, security, licensing, and validation requirements.

---

# 5. Version Lifecycle

Every externally maintained component SHALL follow the following lifecycle:

```text
CANDIDATE
    ↓
EVALUATED
    ↓
APPROVED
    ↓
VERSION SELECTED
    ↓
VERSION LOCKED
    ↓
VALIDATED
    ↓
PRODUCTION
```

A component may also enter:

```text
CONDITIONAL
REJECTED
DEPRECATED
RETIRED
```

depending on its architectural status.

The following rule is mandatory:

> No component SHALL be considered production-ready solely because an upstream release exists.

---

# 6. Lock States

## 6.1 UNLOCKED

The component is approved or known but does not yet have a final production identity.

Example:

```yaml
name: Qwen3
status: APPROVED
lock_status: UNLOCKED
```

---

## 6.2 CANDIDATE_LOCK

A specific version has been selected for evaluation but has not yet completed production validation.

```yaml
lock_status: CANDIDATE_LOCK
```

Candidate locks SHALL NOT be used as production authority.

---

## 6.3 LOCKED

The component has:

- Exact version
- Required revision
- Required artifact identity
- Integrity information
- License validation
- Compatibility validation
- Required test validation

and has been accepted into Version Lock.

```yaml
lock_status: LOCKED
```

---

## 6.4 DEPRECATED

The component remains historically valid but SHALL NOT be selected for new production installations.

---

## 6.5 RETIRED

The component is no longer valid for production use.

Historical Version Lock records SHALL remain preserved.

---

# 7. Exact Version Requirement

Every production dependency SHALL have an exact identity.

Examples include:

```text
Python 3.x.y
FastAPI x.y.z
PostgreSQL x.y
React x.y.z
Node.js x.y.z
```

A major version range such as:

```text
>=3.12
```

is not sufficient for a production lock.

A compatible range may exist in architectural policy, but the Version Lock SHALL contain the exact production selection.

---

# 8. Version, Revision and Digest

Version Lock SHALL distinguish between:

### Version

The semantic or upstream release identifier.

Example:

```text
1.2.3
```

### Revision

The immutable source, model, browser, or artifact revision associated with the selected release.

Examples include:

- Git commit
- Model repository revision
- Browser revision
- Build revision

### Digest

A cryptographic identity of the exact artifact.

Preferred algorithm:

```text
SHA-256
```

Where an artifact digest is available and technically applicable, it SHALL be recorded.

Therefore:

```text
Component Identity
    =
Version
+
Revision
+
Artifact Digest
```

when all three are applicable.

---

# 9. Immutable Identity

Production components SHALL use immutable identities whenever technically possible.

The following SHALL NOT constitute sufficient production identity by themselves:

```text
latest
stable
main
master
nightly
rolling
unversioned
```

Mutable tags MAY be used during development or evaluation but SHALL NOT represent final production artifacts.

Container production artifacts SHALL use immutable image digests.

Model production artifacts SHALL use immutable revisions and artifact digests where available.

---

# 10. Source Authority

Every locked component SHALL identify its authoritative source.

Examples include:

- Official project repository
- Official package registry
- Official model repository
- Official container registry
- Official vendor distribution
- Official MCP server repository
- Official browser distribution

Unverified mirrors SHALL NOT become production authorities without explicit approval.

For every locked artifact, Version Lock SHOULD record:

```yaml
source:
  provider:
  repository:
  artifact:
```

---

# 11. Artifact Integrity

Every downloadable production artifact SHALL undergo integrity verification.

Where supported, verification SHALL include:

- SHA-256 digest
- Digital signature
- Publisher verification
- Registry identity
- Artifact provenance

Bootstrap SHALL verify the expected artifact identity before installation.

A digest mismatch SHALL result in installation failure.

The following state is forbidden:

```text
Expected artifact
        ≠
Downloaded artifact
```

Bootstrap SHALL NOT silently continue after an integrity failure.

---

# 12. Dependency Resolution

Version Lock SHALL represent the final resolved dependency state.

A top-level dependency version alone is insufficient when transitive dependencies affect runtime behavior.

For dependency ecosystems supporting lockfiles, the canonical lock state SHALL include the resolved dependency graph.

Examples:

```text
Python
    ↓
pyproject.toml
    ↓
uv.lock
```

and:

```text
Node.js
    ↓
package.json
    ↓
package-manager lockfile
```

The Version Lock system SHALL reference the canonical dependency lock state.

---

# 13. Python Version Lock

Python-based JAS components SHALL be locked at the following levels:

```text
Python Version
CPython Version
uv Version
Package Versions
Resolved Dependencies
Integrity Information
Platform
Architecture
```

The Python environment SHALL be reproducible from the combination of:

```text
Approved Stack
+
Manifest
+
Version Lock
+
pyproject.toml
+
uv.lock
+
Bootstrap
```

Global Python package installation SHALL NOT form part of the production environment.

---

# 14. Frontend Version Lock

The frontend stack SHALL lock:

- Node.js version
- TypeScript version
- React version
- Vite version
- Selected JavaScript/TypeScript package manager
- Package manager version
- Resolved dependency state

The frontend dependency graph SHALL be reproducible.

A package manager SHALL NOT be changed after Version Lock without a formal lock revision.

---

# 15. Native Toolchain Lock

Where Rust or C/C++ is used, Version Lock SHALL identify:

- Compiler
- Compiler version
- Build system
- Build tool version
- Target architecture
- Platform
- Required native libraries

Rust components SHALL additionally identify:

- Rust version
- Cargo version
- Target triple

C/C++ components SHALL identify:

- Compiler
- Compiler version
- Target
- Required SDK/toolchain

---

# 16. Container Lock

Production container artifacts SHALL be locked using:

```text
Image Name
Image Tag
Image Digest
Architecture
Base Image
Base Image Digest
```

A mutable container tag SHALL NOT be the final production identity.

Example:

```yaml
image:
  repository: <repository>
  tag: <version>
  digest: sha256:<digest>
  architecture: amd64
```

The digest is authoritative.

---

# 17. Browser Lock

Browser automation requires two independently controlled identities:

```text
Browser Automation Framework
+
Browser Binary
```

For Playwright-based systems, Version Lock SHALL therefore capture:

- Playwright version
- Browser family
- Browser revision
- Browser artifact identity

The following browsers may be independently locked where approved:

```text
Chromium
Firefox
WebKit
```

A browser framework upgrade SHALL NOT automatically imply an unlocked browser binary.

---

# 18. Model Lock

AI models require a stricter identity system than conventional software packages.

Every production model SHALL identify, where applicable:

```text
Provider / Organization
Model Family
Exact Variant
Revision
Artifact Format
Quantization
Runtime
Artifact Digest
License
```

Example:

```yaml
model:
  family: Qwen3
  variant: <exact-variant>
  revision: <immutable-revision>
  artifact:
    format: <format>
    quantization: <quantization>
    digest: sha256:<digest>
  runtime:
    name: <runtime>
    version: <version>
```

A model family name alone SHALL NOT constitute a Version Lock identity.

---

# 19. Model Runtime Lock

A model and its inference runtime SHALL be treated as separate lockable components.

Example:

```text
Model
    ↓
Qwen3
    ↓
Artifact
    ↓
GGUF
    ↓
Runtime
    ↓
Ollama
```

The model artifact SHALL therefore not silently inherit the runtime version.

Both SHALL be independently represented when required.

---

# 20. MCP Lock

MCP servers SHALL be individually locked.

The following information SHALL be recorded where applicable:

```text
Server ID
Publisher
Version
Revision
Digest
Protocol Version
SDK Version
Transport
Runtime
License
Permission Profile
```

An MCP registry entry SHALL NOT itself constitute a production lock.

Each enabled MCP server SHALL receive an individual lock record.

---

# 21. Platform Lock

JAS supports multiple platforms.

Version Lock SHALL therefore distinguish platform-specific artifacts.

Supported platform families include:

```text
Windows
Linux
macOS
```

Where relevant, architecture SHALL also be specified:

```text
x86_64 / amd64
arm64
```

A platform-specific dependency SHALL NOT be assumed to be portable merely because its project claims cross-platform support.

Platform compatibility SHALL be validated independently.

---

# 22. Profile-Aware Locking

Not every JAS installation requires every component.

Version Lock SHALL therefore support installation profiles.

Examples:

```text
desktop
server
development
ci
minimal
full
gpu
cpu
browser-enabled
voice-enabled
vision-enabled
```

A component may therefore have:

```yaml
profiles:
  required:
    - desktop
  optional:
    - server
```

Profile selection SHALL be governed by Manifest.

Version Lock SHALL define the exact available component identity.

Manifest SHALL determine which locked components are required for a specific installation.

---

# 23. Required vs Conditional Components

Version Lock SHALL distinguish:

```text
MANDATORY
PROFILE_REQUIRED
CONDITIONAL
OPTIONAL
EXPERIMENTAL
```

A conditional component SHALL not automatically become part of every installation.

An experimental component SHALL never become production merely because it exists in Version Lock metadata.

---

# 24. Internal Component Locking

JAS-owned components SHALL use the JAS release/version system.

Examples include:

- JARVIS Core
- JARVIS Plugin SDK
- JARVIS MCP Gateway
- Authorization Engine
- Audit System
- Internal APIs

Internal components SHALL be identified through:

```text
JAS Release
+
Component Version
+
Source Revision
```

Internal components SHALL not be represented as third-party packages.

---

# 25. Version Selection Criteria

A candidate version SHALL be evaluated according to:

- Compatibility
- Security
- Stability
- Performance
- Resource consumption
- License
- Platform support
- Ecosystem compatibility
- Dependency compatibility
- Bootstrap compatibility
- Manifest compatibility
- Regression results
- Operational reliability

The newest release SHALL NOT automatically win.

The selected version SHALL be the version that provides the best validated fit for JAS v1.

---

# 26. Upgrade Policy

A locked component SHALL NOT be upgraded automatically.

An upgrade SHALL follow:

```text
New Release
    ↓
Security Review
    ↓
Compatibility Review
    ↓
Regression Testing
    ↓
Performance Testing
    ↓
Approval
    ↓
New Version Lock
```

A new Version Lock revision SHALL be generated when a production component changes.

---

# 27. Security Upgrade Exception

Critical security vulnerabilities MAY justify accelerated upgrade procedures.

The accelerated process SHALL still include:

- Security verification
- Compatibility validation
- Artifact verification
- Regression validation
- Lock revision
- Rollback preparation

Emergency changes SHALL remain fully auditable.

---

# 28. Rollback Policy

Every production Version Lock SHALL be reversible.

A rollback SHALL identify:

```text
Previous Version Lock
Previous Component Versions
Previous Revisions
Previous Digests
Previous Manifest
Previous Runtime Configuration
```

Historical Version Lock states SHALL never be overwritten.

Example:

```text
version-lock-v1.0
       ↓
version-lock-v1.1
       ↓
version-lock-v1.2

Rollback:
v1.2 → v1.1
```

---

# 29. Reproducibility Requirement

A Version Lock is valid only if an independent environment can reproduce the locked state.

Given:

```text
Same Manifest
+
Same Version Lock
+
Same Source Artifacts
+
Same Bootstrap
```

the resulting environment SHALL be functionally equivalent within documented platform-specific differences.

Manual installation steps SHALL NOT be required for production reproduction.

---

# 30. Deterministic Installation

Bootstrap SHALL consume Version Lock as authoritative input.

The installation process SHALL follow:

```text
Read Lock
    ↓
Resolve Source
    ↓
Acquire Artifact
    ↓
Verify Identity
    ↓
Verify Digest
    ↓
Install
    ↓
Validate
    ↓
Register
```

Bootstrap SHALL NOT substitute a newer compatible version automatically.

---

# 31. Compliance Verification

Architecture Compliance Checker SHALL verify that the installed environment corresponds to Version Lock.

Verification SHALL include:

- Version
- Revision
- Digest
- Platform
- Architecture
- Runtime
- Required package state
- Required model state
- Required MCP state

A production environment SHALL be considered non-compliant if a locked component differs from the authoritative Version Lock without an approved exception.

---

# 32. Exception Policy

Exceptions SHALL be explicit.

Every exception SHALL identify:

```text
Component
Expected Lock
Actual State
Reason
Risk
Owner
Approval
Expiration
```

Exceptions SHALL NOT silently modify Version Lock.

Temporary deviations SHALL have an expiration or review date.

---

# 33. Historical Integrity

Historical Version Lock states SHALL be immutable records.

The system SHALL preserve:

- Previous lock files
- Previous revisions
- Previous digests
- Previous manifests
- Previous validation reports
- Upgrade records
- Rollback records

Historical records SHALL support reproducibility and forensic analysis.

---

# 34. Version Lock Revisioning

Version Lock SHALL use explicit revisions.

A revision SHALL be created when:

- A production component changes
- A model artifact changes
- A model revision changes
- A dependency graph changes
- A browser revision changes
- An MCP server changes
- A platform-specific artifact changes
- A security upgrade occurs
- A rollback state is formally restored

Documentation-only changes that do not modify production identity MAY use a non-production revision according to repository governance.

---

# 35. Lock Completeness

A Version Lock SHALL NOT be marked production-ready until all mandatory components have complete lock identities.

Mandatory identity fields SHALL be satisfied according to component type.

Examples:

### Python package

```text
Package
Version
Resolved dependency state
Integrity
```

### Container

```text
Image
Tag
Digest
Architecture
```

### Model

```text
Provider
Family
Variant
Revision
Artifact
Quantization where applicable
Digest where available
License
```

### MCP Server

```text
Server
Publisher
Version
Revision
Digest
Protocol
SDK
Transport
Runtime
License
Permission Profile
```

---

# 36. Lock Completeness States

The Version Lock system SHALL expose:

```text
NOT_READY
PARTIAL
CANDIDATE
VALIDATED
LOCKED
RELEASE_READY
```

Definitions:

### NOT_READY

Required information is missing.

### PARTIAL

Some components have been resolved.

### CANDIDATE

A complete candidate lock has been assembled but validation is incomplete.

### VALIDATED

Technical and security validation has completed.

### LOCKED

The exact production dependency state is authoritative.

### RELEASE_READY

Manifest, Bootstrap and compliance validation have confirmed that the lock can be used for release.

---

# 37. Source and Artifact Separation

Version Lock SHALL distinguish:

```text
Source Identity
```

from:

```text
Artifact Identity
```

For source-built software:

```text
Repository
Commit
Build Toolchain
Build Configuration
Artifact Digest
```

For prebuilt artifacts:

```text
Provider
Release
Artifact
Digest
```

This distinction is mandatory for reproducibility.

---

# 38. License Governance

Every locked external component SHALL have a validated license.

Version Lock SHALL record the license identity relevant to the selected artifact.

License validation SHALL occur against:

- Exact component
- Exact version
- Exact artifact
- Model weights where applicable
- Runtime distribution where applicable
- Bundled dependencies where applicable

A component SHALL NOT be locked merely because its project generally claims an acceptable license.

The selected production artifact SHALL be the object of validation.

---

# 39. Security Governance

Before a component becomes LOCKED:

- Known critical vulnerabilities SHALL be evaluated
- Artifact provenance SHALL be evaluated
- Source authority SHALL be verified
- Integrity SHALL be verified
- Supply-chain risk SHALL be evaluated
- Required security controls SHALL be confirmed

Security status SHALL be recorded in the lock validation metadata.

---

# 40. Performance Governance

A version SHALL not be selected solely based on functional compatibility.

Where performance materially affects JAS, validation SHALL include:

- Latency
- Throughput
- CPU consumption
- Memory consumption
- VRAM consumption
- Startup time
- Resource stability

AI models SHALL additionally use the approved model evaluation framework.

---

# 41. Version Lock and Model Evaluation

Model Version Lock SHALL depend on successful model evaluation.

The flow SHALL be:

```text
Approved Model
      ↓
Evaluation
      ↓
Hardware Validation
      ↓
Security / License Validation
      ↓
Artifact Verification
      ↓
Exact Variant Selection
      ↓
Version Lock
```

A model SHALL NOT be locked merely because it is listed in `19_APPROVED_MODELS.md`.

---

# 42. Version Lock and MCP Evaluation

MCP servers SHALL follow:

```text
Approved MCP Server
      ↓
Security Review
      ↓
Permission Review
      ↓
Protocol Compatibility
      ↓
Runtime Compatibility
      ↓
Artifact Verification
      ↓
Version Lock
```

MCP server capability approval and exact MCP server version locking are separate decisions.

---

# 43. Version Lock and Manifest

Version Lock defines:

> What exact components exist?

Manifest defines:

> Which of those components are required for this installation profile?

Therefore:

```text
Version Lock
    ↓
Exact component identity

Manifest
    ↓
Installation selection
```

Manifest SHALL reference Version Lock entries rather than independently defining conflicting versions.

---

# 44. Version Lock and Bootstrap

Bootstrap SHALL consume Version Lock and SHALL NOT independently select production versions.

Bootstrap MAY:

- Detect platform
- Select profile
- Resolve the corresponding locked artifact
- Download artifact
- Verify integrity
- Install artifact
- Validate installation

Bootstrap SHALL NOT:

- Replace locked versions
- Upgrade components silently
- Select arbitrary mirrors
- Ignore digest mismatches
- Bypass compliance failures

---

# 45. Version Lock and Architecture Compliance Checker

Architecture Compliance Checker SHALL treat Version Lock as the authoritative production dependency state.

The checker SHALL detect:

```text
Version Drift
Revision Drift
Digest Drift
Platform Drift
Dependency Drift
Model Drift
MCP Drift
Runtime Drift
```

Any unauthorized drift SHALL be reported as a compliance violation.

---

# 46. Development vs Production

Development environments MAY temporarily use:

- Newer candidate versions
- Experimental builds
- Local patches
- Unlocked dependencies

provided they are explicitly marked as development state.

Production environments SHALL use only:

```text
APPROVED
+
LOCKED
```

components.

Development usage SHALL NOT silently promote an artifact into production.

---

# 47. Mutable Development Dependencies

Mutable dependencies such as:

```text
main
nightly
latest
local build
unreleased
```

MAY be used for experimentation.

They SHALL NOT be valid production Version Lock identities.

When experimental work becomes a production candidate, it SHALL receive a reproducible immutable identity.

---

# 48. Lock Review

Every Version Lock release SHALL undergo review appropriate to the change.

Review categories include:

- Architecture
- Compatibility
- Security
- License
- Performance
- Reproducibility
- Platform
- Model evaluation
- MCP evaluation

The scope of review SHALL correspond to the affected components.

---

# 49. Minimal Change Principle

A Version Lock update SHALL change only the components that require modification.

Unrelated dependencies SHALL NOT be upgraded merely because a lock revision is being created.

This minimizes:

- Regression surface
- Debugging complexity
- Supply-chain exposure
- Deployment risk

---

# 50. Dependency Drift

Dependency drift occurs when the installed environment differs from the authoritative Version Lock.

Examples:

```text
Locked:
FastAPI  X.Y.Z

Installed:
FastAPI  X.Y.(Z+1)
```

or:

```text
Locked:
sha256:ABC

Installed:
sha256:DEF
```

Both constitute Version Lock drift.

Drift SHALL be detectable by Architecture Compliance Checker.

---

# 51. Lock Validation

Before release, Version Lock SHALL pass:

```text
Schema Validation
Dependency Validation
Artifact Validation
Digest Validation
License Validation
Security Validation
Platform Validation
Integration Validation
Regression Validation
```

AI-enabled installations SHALL additionally pass relevant model evaluation requirements.

---

# 52. Release Gate

The final release gate SHALL be:

```text
All mandatory components locked
        AND
All required artifacts verified
        AND
All required licenses validated
        AND
Security validation passed
        AND
Platform validation passed
        AND
Regression validation passed
        AND
Manifest references valid lock entries
        AND
Bootstrap reproduces the lock
        AND
Compliance Checker passes
```

Only then may the Version Lock be marked:

```text
RELEASE_READY
```

---

# 53. Prohibited Practices

The following practices are prohibited in production:

- Using `latest` as a production identity
- Installing unapproved packages
- Ignoring lockfile differences
- Ignoring digest mismatches
- Silently upgrading dependencies
- Silently replacing model artifacts
- Using unapproved MCP servers
- Installing packages from unknown sources
- Manually modifying production environments without recording the change
- Deleting historical lock records
- Treating model family names as sufficient artifact identities
- Treating package ranges as final production versions

---

# 54. Governance Principle

The central Version Lock principle is:

> Production behavior SHALL be determined by explicitly approved and immutably identified components rather than by whatever versions happen to be available at installation time.

Therefore:

```text
Approved Technology
        ↓
Exact Selection
        ↓
Immutable Identity
        ↓
Validation
        ↓
Version Lock
        ↓
Reproducible Installation
```

---

# 55. Version Lock Authority

For JAS v1:

**Version Lock is the final authority for exact production dependency identity.**

Approved Stack documents determine what is allowed.

Approved Software Matrix determines approved software families and lifecycle status.

Approved Models determines approved model families and model governance.

Approved MCP Servers determines approved MCP capabilities and server governance.

Version Lock determines the exact production artifact.

Manifest determines installation composition.

Bootstrap performs installation.

Architecture Compliance Checker verifies compliance.

---

# 56. Final Decision

The Version Lock Policy for JAS v1 is approved.

The following rules are finalized:

1. Production dependencies SHALL use exact identities.
2. Mutable upstream references SHALL NOT represent production artifacts.
3. Version, revision, and digest SHALL be treated as distinct concepts.
4. Artifact integrity SHALL be verified before installation.
5. Models SHALL be locked at exact artifact identity.
6. MCP servers SHALL be locked individually.
7. Container images SHALL use immutable digests.
8. Platform-specific artifacts SHALL be explicitly represented.
9. Version Lock SHALL be profile-aware.
10. Bootstrap SHALL consume Version Lock rather than independently selecting versions.
11. Architecture Compliance Checker SHALL detect Version Lock drift.
12. Historical Version Lock states SHALL remain preserved.
13. Upgrades SHALL require validation and a new lock revision.
14. Rollback SHALL restore a previously validated lock state.
15. No production component SHALL enter Version Lock without the required approval and validation.

---

# 57. Next Phase

The next Version Lock phase is:

**Component Version Resolution**

The sequence SHALL be:

```text
01_VERSION_LOCK_POLICY.md
        ↓
02_COMPONENT_LOCKS.yaml
        ↓
03_MODEL_LOCKS.yaml
        ↓
04_MCP_LOCKS.yaml
        ↓
05_PLATFORM_LOCKS.yaml
        ↓
06_ARTIFACT_LOCKS.yaml
        ↓
VERSION_LOCK_v1.yaml
```

The next file SHALL resolve the exact software component versions permitted by the Approved Software Matrix.

Model versions, model revisions and model artifacts SHALL be resolved separately through the Model Lock phase.

MCP server versions and revisions SHALL be resolved separately through the MCP Lock phase.

---

# Revision History

| Version | Description |
|---|---|
| 0.1 | Initial Version Lock policy draft |
| 0.5 | Added immutable artifact, digest, model, MCP and platform governance |
| 0.8 | Added profile-aware locking, rollback, compliance and reproducibility requirements |
| 1.0 | Approved Version Lock Policy for JAS v1 |

---

# End of Document