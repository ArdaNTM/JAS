# 26 — VERSION LOCK

**Document ID:** JAS-AS-26  
**Document:** `26_VERSION_LOCK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Release Governance / Version Lock  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** DRAFT — HARDWARE / LOCAL INFERENCE BASELINE CAPTURED  
**Primary Domain:** Exact Version Locking, Reproducibility, Runtime Identity, Model Identity, Hardware Profiles and Release Baseline

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
24_VERSION_SUPPORT_POLICY.md
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

**Feeds Into:**

```text
Manifest
Bootstrap
Architecture Compliance Checker
System Verification
Build System
Runtime Configuration
Model Registry
Model Router
Release Engineering
Deployment
```

---

# 1. PURPOSE

This document defines the exact version and artifact identity baseline for a JARVIS release.

The purpose of Version Lock is to answer:

> **Exactly what versions, revisions, artifacts, runtimes and hardware assumptions constitute this release?**

Version Support Policy defines which versions may be supported.

Version Lock defines which exact versions are used.

```text
Version Support Policy
        ↓
Allowed Version Range
        ↓
Evaluation
        ↓
Approved Version
        ↓
VERSION LOCK
        ↓
Exact Release State
```

Version Lock therefore represents a significantly higher level of precision than a general compatibility policy.

---

# 2. CORE PRINCIPLE

JARVIS must never rely on:

```text
Latest
```

as a production versioning strategy.

The production state must instead be represented by:

```text
Exact Version
+
Exact Artifact
+
Exact Revision
+
Exact Runtime
+
Exact Configuration
+
Exact Compatibility Profile
```

where applicable.

---

# 3. VERSION LOCK INVARIANT

A release is reproducible only when its critical dependencies can be identified precisely.

The conceptual production identity is:

```text
Source
+
Dependencies
+
Toolchain
+
Runtime
+
Models
+
Model Artifacts
+
Configuration
+
Hardware Profile
```

Therefore:

```text
UNKNOWN
    ↓
NOT LOCKED

UNPINNED
    ↓
NOT REPRODUCIBLE

UNVERIFIED
    ↓
NOT PRODUCTION READY
```

---

# 4. VERSION LOCK ≠ VERSION SUPPORT

The two documents have different responsibilities.

## Version Support Policy

Answers:

```text
Which versions may JARVIS use?
```

and:

```text
How long may they remain supported?
```

## Version Lock

Answers:

```text
Which exact versions does this release use?
```

Therefore:

```text
24_VERSION_SUPPORT_POLICY
            ↓
Supported Range
            ↓
Evaluation
            ↓
26_VERSION_LOCK
            ↓
Exact Version
```

---

# 5. LOCKED COMPONENT IDENTITY

Each locked component should contain, where applicable:

```text
Component ID
Component Name
Category
Version
Revision
Digest
Artifact
Platform
Architecture
Runtime
Configuration
Status
Evidence
```

For model artifacts, additional identity may include:

```text
Model Family
Model Variant
Model Tag
Model Revision
Model Digest
Layer Digest
Quantization
Format
Context Configuration
Runtime
Hardware Profile
```

---

# 6. LOCK STATES

Each component shall have one of the following states:

```text
LOCKED
VALIDATED
PENDING VALIDATION
CONDITIONAL
EXPERIMENTAL
REJECTED
NOT APPLICABLE
```

Only:

```text
LOCKED
+
VALIDATED
```

may normally constitute the production baseline.

---

# 7. HARDWARE PROFILE

The first validated local development hardware profile captured for JARVIS is:

```text
PROFILE ID:
JAS-HW-LOCAL-001

CPU:
Intel(R) Core(TM) i7-9750H CPU @ 2.60GHz

CPU CORES:
6

LOGICAL PROCESSORS:
12

SYSTEM RAM:
17,029,664,768 bytes
≈ 16 GiB physical RAM

GPU:
NVIDIA GeForce GTX 1660 Ti

GPU VRAM:
6144 MiB
6 GiB

GPU PCI DEVICE ID:
0x219110DE

NVIDIA DRIVER:
610.62

CUDA UMD:
13.3

OS:
Windows 10 Pro

OS ARCHITECTURE:
64-bit
```

This profile represents an observed development environment.

It must **not** automatically be interpreted as:

```text
Universal JARVIS Hardware Requirement
```

The hardware profile is an execution profile.

---

# 8. HARDWARE PROFILE RULE

The JARVIS architecture must distinguish:

```text
Architecture Requirement
```

from:

```text
Current Development Hardware
```

Therefore:

```text
GTX 1660 Ti
```

is not itself an architectural dependency.

The architecture must remain capable of supporting:

```text
CPU
GPU
Alternative GPU
Cloud Runtime
Future Accelerator
```

through the inference abstraction defined by the previous architecture documents.

---

# 9. GPU VALIDATION

The captured NVIDIA environment reports:

```text
GPU:
NVIDIA GeForce GTX 1660 Ti

VRAM:
6144 MiB

Driver:
610.62

CUDA UMD:
13.3
```

Ollama independently detected the GPU as:

```text
CUDA0

Compute Capability:
7.5

Total:
6.0 GiB

Available during runtime initialization:
approximately 5.0 GiB
```

This confirms that the local Ollama runtime can detect the discrete NVIDIA GPU through its CUDA backend.

---

# 10. GPU BACKEND

The observed Ollama runtime selected:

```text
Library:
CUDA

GPU:
NVIDIA GeForce GTX 1660 Ti

Compute Capability:
7.5
```

The integrated:

```text
Intel(R) UHD Graphics 630
```

was detected through Vulkan but was dropped for inference.

Therefore the observed local inference path is:

```text
JARVIS
   ↓
Ollama
   ↓
CUDA
   ↓
NVIDIA GTX 1660 Ti
```

The Intel integrated GPU is not part of the current inference baseline.

---

# 11. OLLAMA RUNTIME

The validated local Ollama installation is:

```text
Runtime:
Ollama

Version:
0.32.7

Platform:
Windows

Architecture:
64-bit

Executable:
C:\Users\ardab\AppData\Local\Programs\Ollama\ollama.exe
```

Current runtime version:

```text
OLLAMA 0.32.7
```

is the observed development runtime.

Production approval remains subject to the full Version Lock and System Verification process.

---

# 12. OLLAMA MODEL STORAGE

The configured Ollama model storage location is:

```text
D:\AI\Models\Ollama\models
```

Environment configuration:

```text
OLLAMA_MODELS=D:\AI\Models\Ollama\models
```

The storage root contains:

```text
D:\AI\Models\Ollama\models
├── blobs
└── manifests
```

This configuration is valid for the observed local environment.

---

# 13. OLLAMA MODEL STORAGE POLICY

Model weights and associated model artifacts should remain outside the operating-system user profile when practical.

The current architecture therefore uses:

```text
OS / Application
    ↓
Ollama Runtime
    ↓
Configured Model Storage
    ↓
Dedicated AI Model Disk Location
```

The model storage location itself is configuration and must not be confused with model identity.

Changing:

```text
OLLAMA_MODELS
```

does not change:

```text
Model Identity
```

provided that the underlying artifacts remain identical and verified.

---

# 14. INSTALLED LOCAL MODELS

The currently installed local models are:

```text
qwen2.5:7b
qwen2.5-coder:7b
```

Observed model table:

| Model | Parameters | Quantization | Context | Size |
|---|---:|---|---:|---:|
| `qwen2.5:7b` | 7.6B | Q4_K_M | 32768 | ~4.7 GB |
| `qwen2.5-coder:7b` | 7.6B | Q4_K_M | 32768 | ~4.7 GB |

These models are currently installed and runnable in the local environment.

Installation does not automatically imply production approval.

---

# 15. QWEN2.5 MODEL IDENTITY

Current local model:

```text
Model:
qwen2.5:7b

Architecture:
qwen2

Parameters:
7.6B

Context Length:
32768

Embedding Length:
3584

Quantization:
Q4_K_M

Format:
GGUF
```

Ollama model digest:

```text
845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e
```

Canonical artifact identity:

```text
sha256:
845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e
```

---

# 16. QWEN2.5 MODEL ARTIFACT

The local Ollama manifest identifies the primary model layer as:

```text
sha256:
2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730
```

Model layer size:

```text
4,683,073,952 bytes
```

Additional observed layers:

```text
System Layer:
sha256:
66b9ea09bd5b7099cbb4fc820f31b575c0366fa439b08245566692c6784e281e

Template Layer:
sha256:
eb4402837c7829a690fa845de4d7f3fd842c2adee476d5341da8a46ea9255175

License Layer:
sha256:
832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e
```

The local blob SHA-256 verification matched the corresponding artifact hashes.

---

# 17. QWEN2.5-CODER MODEL IDENTITY

Current local model:

```text
Model:
qwen2.5-coder:7b

Architecture:
qwen2

Parameters:
7.6B

Context Length:
32768

Embedding Length:
3584

Quantization:
Q4_K_M

Format:
GGUF
```

Ollama model digest:

```text
dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364
```

Canonical artifact identity:

```text
sha256:
dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364
```

---

# 18. QWEN2.5-CODER MODEL ARTIFACT

The local Ollama manifest identifies the primary model layer as:

```text
sha256:
60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463
```

Model layer size:

```text
4,683,074,048 bytes
```

Additional observed layers:

```text
System Layer:
sha256:
66b9ea09bd5b7099cbb4fc820f31b575c0366fa439b08245566692c6784e281e

Template Layer:
sha256:
1e65450c30670713aa47fe23e8b9662bdf4065e81cc8e3cbfaa98924fcc0d320

License Layer:
sha256:
832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e
```

The local blob SHA-256 verification matched the corresponding artifact hashes.

---

# 19. MODEL DIGEST RULE

A model tag:

```text
qwen2.5-coder:7b
```

is not equivalent to its immutable artifact identity:

```text
sha256:<digest>
```

The production Version Lock should preserve both.

Therefore:

```text
Human Reference:
qwen2.5-coder:7b

Artifact Identity:
sha256:dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364
```

must be treated as two related but distinct identifiers.

---

# 20. OLLAMA MANIFEST INTEGRITY

The observed local model repository uses:

```text
Model Tag
    ↓
Manifest
    ↓
Layer Digests
    ↓
Local Blobs
    ↓
SHA-256
```

This is consistent with the Version Support Policy's Ollama integrity requirements. fileciteturn44file4L802-L820

The following integrity checks were successfully observed:

```text
Manifest exists
        +
Referenced blobs exist
        +
Blob SHA-256 matches digest
```

Status:

```text
VALIDATED
```

---

# 21. MODEL FORMAT

The currently validated local models use:

```text
GGUF
```

with:

```text
Q4_K_M
```

quantization.

The architecture must nevertheless preserve the distinction between:

```text
Model Family
Model Revision
Artifact Format
Quantization
Runtime
```

because changing any of these may change:

```text
Memory Usage
Latency
Throughput
Quality
Tool Calling
Structured Output
Context Handling
```

---

# 22. CONTEXT CONFIGURATION

The model metadata reports:

```text
Model Context:
32768
```

However, the observed Ollama runtime initialized with:

```text
default_num_ctx=4096
```

based on the available 6 GiB VRAM profile.

Therefore:

```text
Model Maximum Context
        ≠
Runtime Effective Context
```

The current observed runtime execution profile is:

```text
Context:
4096
```

This distinction is mandatory for reproducibility.

---

# 23. QWEN2.5 RUNTIME PROFILE

Observed execution:

```text
Model:
qwen2.5:7b

Runtime:
Ollama 0.32.7

Context:
4096

Processor:
18% CPU
82% GPU
```

Observed GPU memory:

```text
approximately 5.0 GiB
```

This demonstrates that the model can execute using substantial GPU acceleration on the current GTX 1660 Ti profile.

---

# 24. QWEN2.5-CODER RUNTIME PROFILE

Observed execution:

```text
Model:
qwen2.5-coder:7b

Runtime:
Ollama 0.32.7

Context:
4096

Processor:
18% CPU
82% GPU
```

Observed GPU memory:

```text
approximately 5.0 GiB
```

The current runtime therefore uses:

```text
GPU Acceleration:
VALIDATED

Full GPU Residency:
NOT ASSUMED

CPU Offload:
PRESENT
```

---

# 25. CPU/GPU OFFLOAD POLICY

The current local profile demonstrates:

```text
18% CPU
82% GPU
```

execution.

This must be treated as an explicit runtime profile.

A future configuration that changes execution from:

```text
18% CPU / 82% GPU
```

to a substantially different split shall require performance revalidation.

The model must not be considered equivalent merely because:

```text
Model = same
```

The effective execution environment is:

```text
Model
+
Runtime
+
Backend
+
Hardware
+
Context
+
Offload Configuration
```

---

# 26. GPU UTILIZATION INTERPRETATION

Instantaneous GPU utilization is not sufficient to validate model acceleration.

For example, the observed model execution produced:

```text
GPU Memory:
~5.0 GiB

GPU Utilization:
low instantaneous values during sampling
```

This does not indicate that GPU inference is disabled.

Validation must distinguish:

```text
GPU Memory Residency
GPU Execution
CPU Offload
Throughput
Latency
```

This follows the same policy already established for local LLM validation. fileciteturn44file3L621-L635

---

# 27. LOCAL INFERENCE STACK IDENTITY

The current validated local inference stack is:

```text
Operating System
    ↓
Windows 10 Pro 64-bit
    ↓
NVIDIA Driver 610.62
    ↓
CUDA UMD 13.3
    ↓
NVIDIA GTX 1660 Ti
    ↓
Ollama 0.32.7
    ↓
GGUF / Q4_K_M
    ↓
Qwen Model
```

This entire chain constitutes the current development validation profile.

---

# 28. LOCAL INFERENCE ARTIFACT IDENTITY

For local inference, JARVIS shall treat the effective artifact as:

```text
Model
+
Model Digest
+
Model Layers
+
Runtime
+
Runtime Version
+
Backend
+
GPU Driver
+
Hardware
+
Context
+
Execution Profile
```

This is consistent with the Version Support Policy's local runtime coupling rule. fileciteturn44file3L533-L562

---

# 29. CURRENT LOCAL SOFTWARE BASELINE

The following versions have been directly observed:

| Component | Version / Identity | Status |
|---|---|---|
| Windows | Windows 10 Pro | VALIDATED |
| Architecture | x64 | VALIDATED |
| Ollama | 0.32.7 | VALIDATED |
| NVIDIA Driver | 610.62 | VALIDATED |
| CUDA UMD | 13.3 | VALIDATED |
| GPU | GTX 1660 Ti | VALIDATED |
| GPU VRAM | 6144 MiB | VALIDATED |
| Qwen 2.5 | 7B / Q4_K_M | VALIDATED |
| Qwen 2.5 Coder | 7B / Q4_K_M | VALIDATED |

---

# 30. UNLOCKED / PENDING COMPONENTS

The following exact versions have not yet been established by the current validation evidence:

```text
Python
Node.js
TypeScript
React
Vite
FastAPI
Pydantic
SQLAlchemy
PostgreSQL
Redis
Qdrant
LangGraph
Playwright
OpenTelemetry
Docker
uv
MCP client implementation
Frontend package manager
Browser revision
STT runtime
TTS runtime
Vision model revisions
Embedding model
Reranker
```

These values must not be invented.

Status:

```text
PENDING VALIDATION
```

---

# 31. VERSION LOCK COMPLETENESS RULE

A Version Lock may not be declared complete while critical production dependencies remain:

```text
UNKNOWN
```

or:

```text
UNVERIFIED
```

The final process is:

```text
Discover
    ↓
Record
    ↓
Verify
    ↓
Evaluate
    ↓
Lock
```

not:

```text
Guess
    ↓
Lock
```

---

# 32. MODEL APPROVAL RULE

A locally runnable model is not automatically an approved JARVIS model.

The required chain is:

```text
Model Available
        ↓
Identity Verified
        ↓
License Verified
        ↓
Hardware Compatibility
        ↓
Behavior Evaluation
        ↓
Tool-Calling Evaluation
        ↓
Performance Evaluation
        ↓
Security Evaluation
        ↓
Approval
        ↓
Version Lock
```

This is consistent with the existing Approved Models architecture, where model identity, revision, artifact format and quantization are explicitly separated. fileciteturn44file0L109-L151

---

# 33. LOCAL MODEL APPROVAL STATUS

Current local models:

```text
qwen2.5:7b
qwen2.5-coder:7b
```

are currently classified as:

```text
LOCAL DEVELOPMENT / VALIDATED RUNTIME ARTIFACTS
```

They are **not yet automatically classified as production-approved JARVIS models**.

The remaining approval requirement is behavioral and workload-specific evaluation.

---

# 34. MODEL PERFORMANCE BASELINE

The JARVIS model evaluation system shall capture at minimum:

```text
Task Accuracy
Reasoning Quality
Tool-Calling Reliability
Structured Output Reliability
Context Handling
Latency
Tokens / Second
VRAM Usage
RAM Usage
Failure Rate
Recovery Behavior
```

These criteria directly correspond to the roadmap's local model evaluation requirements. fileciteturn42file3L802-L820

---

# 35. TOOL-CALLING VALIDATION

Because JARVIS is an agentic system, ordinary conversational quality is insufficient.

The model must be evaluated for:

```text
Correct Tool Selection
Correct Tool Arguments
Schema Compliance
No Unauthorized Tool Calls
Recovery After Tool Failure
Multi-Step Tool Execution
```

A model producing good natural-language responses is not automatically suitable for agent execution.

---

# 36. STRUCTURED OUTPUT VALIDATION

Models used by JARVIS must be evaluated for:

```text
Schema Compliance
Determinism
Malformed Output Rate
Recovery
Validation Failure Rate
```

Structured output must be validated by the application layer.

The model must never become the final authority over:

```text
Security
Permissions
Tool Authorization
Policy
```

---

# 37. MODEL ROUTING

The Version Lock must not force the entire JARVIS architecture to use one model.

The intended architecture remains:

```text
JARVIS
   ↓
Model Interface
   ↓
Model Router
   ↓
Capability
   ↓
Approved Model
   ↓
Runtime
```

This preserves the model-agnostic architecture defined by the Approved Models specification. fileciteturn44file0L56-L82

---

# 38. LOCAL / CLOUD ROUTING

The long-term architecture shall support:

```text
LOCAL
+
CLOUD
+
SPECIALIZED MODELS
```

rather than requiring exclusive dependence on a single provider.

Routing may consider:

```text
Privacy
Capability
Latency
Cost
Availability
Offline State
Security Policy
```

as already established in the roadmap. fileciteturn42file3L856-L880

---

# 39. HARDWARE-AWARE ROUTING

The model router may use hardware information as an input.

Conceptually:

```text
Request
   ↓
Task Classification
   ↓
Policy Check
   ↓
Privacy Classification
   ↓
Capability Check
   ↓
Hardware Check
   ↓
Model + Runtime Selection
   ↓
Inference
   ↓
Evaluation
```

Hardware availability must not override security or policy decisions.

---

# 40. 6 GB VRAM PROFILE POLICY

The current:

```text
GTX 1660 Ti
6 GiB VRAM
```

profile is considered a constrained local inference environment.

Therefore the runtime must account for:

```text
Model Memory
+
Runtime Overhead
+
Context Memory
+
KV Cache
+
GPU Memory Used by Other Applications
+
Safety Headroom
```

A model is not considered compatible merely because:

```text
Model File Size < 6 GiB
```

---

# 41. CURRENT VRAM OBSERVATION

During local model execution:

```text
Total VRAM:
6144 MiB

Observed Ollama inference memory:
approximately 5.0 GiB
```

This leaves limited operational headroom.

Therefore the current profile should not assume that:

```text
6 GiB
=
6 GiB available to model
```

The operating system, display stack and other applications consume GPU resources.

---

# 42. CONTEXT / VRAM TRADE-OFF

Increasing:

```text
Context Length
```

may increase:

```text
KV Cache
GPU Memory Usage
RAM Usage
Latency
```

Therefore context size must be explicitly locked as part of the runtime profile.

Current observed baseline:

```text
Model Capability:
32768

Effective Ollama Runtime Context:
4096
```

---

# 43. MODEL STORAGE INTEGRITY

The model storage directory shall be treated as an artifact repository.

The following must be verified:

```text
Manifest Exists
Blob Exists
Digest Matches
Model Metadata Matches
License Layer Exists
Template Layer Exists
System Layer Exists
```

Any mismatch must produce:

```text
VERSION LOCK VERIFICATION FAILURE
```

---

# 44. OLLAMA UPDATE POLICY

Ollama upgrades must not silently alter the production baseline.

The following constitutes a distinct version change:

```text
Ollama Version
```

even when:

```text
Model
```

remains unchanged.

Therefore:

```text
Ollama 0.32.7
```

and:

```text
Ollama <future version>
```

are separate runtime baselines.

The model must be revalidated after a critical runtime upgrade.

---

# 45. MODEL UPDATE POLICY

A model update requires:

```text
New Model Identity
        ↓
New Digest
        ↓
Artifact Verification
        ↓
Behavior Evaluation
        ↓
Performance Evaluation
        ↓
Tool Evaluation
        ↓
Approval
        ↓
Version Lock Update
```

Changing only the visible tag is insufficient.

---

# 46. HARDWARE UPDATE POLICY

A hardware change does not automatically invalidate the architecture.

However, it may invalidate:

```text
Performance Baseline
VRAM Assumptions
Runtime Configuration
Model Selection
Quantization Selection
Context Configuration
```

Therefore a hardware profile change requires targeted revalidation.

---

# 47. DRIVER UPDATE POLICY

The GPU driver is part of the local inference compatibility stack.

A driver update may change:

```text
CUDA Compatibility
Inference Performance
VRAM Behavior
Runtime Stability
Numerical Behavior
```

Therefore:

```text
Driver Version
```

must be included in local inference validation records.

Current observed driver:

```text
610.62
```

---

# 48. CUDA BACKEND POLICY

The current validated local inference path uses:

```text
CUDA
```

with:

```text
CUDA UMD:
13.3
```

The CUDA/backend version is part of the runtime environment and must be captured when reproducing the local inference baseline.

---

# 49. WINDOWS DEVELOPMENT PROFILE

Current development profile:

```text
OS:
Windows 10 Pro

Architecture:
x64
```

This profile is valid for local development validation.

It does not imply that the production architecture is Windows-only.

The architecture should remain portable to:

```text
Windows
Linux
Containerized Linux
Cloud Runtime
```

where supported by the relevant component.

---

# 50. ENVIRONMENT REPRODUCIBILITY

The local model environment should be reconstructable from:

```text
OS Profile
+
GPU Profile
+
Driver
+
CUDA Backend
+
Ollama Version
+
OLLAMA_MODELS
+
Model Tags
+
Model Digests
+
Model Layer Digests
+
Runtime Context
```

This information is sufficient to describe the currently captured local inference baseline.

---

# 51. VERSION LOCK RECORD FORMAT

Future locked components should follow:

```text
COMPONENT:
<name>

VERSION:
<exact version>

REVISION:
<revision>

DIGEST:
<digest>

PLATFORM:
<platform>

ARCHITECTURE:
<architecture>

RUNTIME:
<runtime>

CONFIGURATION:
<configuration>

STATUS:
LOCKED / VALIDATED

EVIDENCE:
<verification source>
```

---

# 52. MODEL LOCK RECORD FORMAT

For models:

```text
MODEL:
<model name>

TAG:
<model tag>

MODEL FAMILY:
<family>

REVISION:
<revision>

FORMAT:
<format>

QUANTIZATION:
<quantization>

MODEL DIGEST:
sha256:<digest>

MODEL LAYER:
sha256:<digest>

TEMPLATE:
sha256:<digest>

SYSTEM:
sha256:<digest>

LICENSE:
sha256:<digest>

RUNTIME:
<runtime>

RUNTIME VERSION:
<version>

CONTEXT:
<context>

HARDWARE PROFILE:
<profile>

STATUS:
<status>
```

---

# 53. CURRENT QWEN2.5 LOCK RECORD

```text
MODEL:
Qwen 2.5

TAG:
qwen2.5:7b

PARAMETERS:
7.6B

FORMAT:
GGUF

QUANTIZATION:
Q4_K_M

MODEL DIGEST:
sha256:845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e

MODEL LAYER:
sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730

RUNTIME:
Ollama

RUNTIME VERSION:
0.32.7

CONTEXT:
4096 effective runtime baseline

HARDWARE:
JAS-HW-LOCAL-001

STATUS:
VALIDATED LOCAL BASELINE
```

---

# 54. CURRENT QWEN2.5-CODER LOCK RECORD

```text
MODEL:
Qwen 2.5 Coder

TAG:
qwen2.5-coder:7b

PARAMETERS:
7.6B

FORMAT:
GGUF

QUANTIZATION:
Q4_K_M

MODEL DIGEST:
sha256:dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364

MODEL LAYER:
sha256:60e05f2100071479f596b964f89f510f057ce397ea22f2833a0cfe029bfc2463

RUNTIME:
Ollama

RUNTIME VERSION:
0.32.7

CONTEXT:
4096 effective runtime baseline

HARDWARE:
JAS-HW-LOCAL-001

STATUS:
VALIDATED LOCAL BASELINE
```

---

# 55. CURRENT OLLAMA LOCK RECORD

```text
RUNTIME:
Ollama

VERSION:
0.32.7

PLATFORM:
Windows

ARCHITECTURE:
x64

MODEL STORAGE:
D:\AI\Models\Ollama\models

BACKEND:
CUDA

GPU:
NVIDIA GeForce GTX 1660 Ti

GPU VRAM:
6144 MiB

GPU DRIVER:
610.62

CUDA UMD:
13.3

STATUS:
VALIDATED LOCAL BASELINE
```

---

# 56. CURRENT HARDWARE LOCK RECORD

```text
PROFILE:
JAS-HW-LOCAL-001

CPU:
Intel Core i7-9750H

CORES:
6

THREADS:
12

RAM:
~16 GiB

GPU:
NVIDIA GeForce GTX 1660 Ti

VRAM:
6 GiB

DRIVER:
610.62

CUDA UMD:
13.3

OS:
Windows 10 Pro x64

STATUS:
VALIDATED DEVELOPMENT PROFILE
```

---

# 57. PRODUCTION STATUS DISTINCTION

The current records must be interpreted as:

```text
LOCAL ENVIRONMENT:
VALIDATED
```

rather than automatically:

```text
JARVIS PRODUCTION:
APPROVED
```

Production approval requires:

```text
Version Lock
+
Manifest
+
Bootstrap
+
Compliance
+
Security
+
Testing
+
System Verification
```

---

# 58. NO SILENT UPDATES

The following must never silently change a locked environment:

```text
Ollama Update
Model Update
Model Tag Resolution
Driver Update
CUDA Backend Update
Context Configuration
Quantization
Model Artifact
Runtime Configuration
```

Any such change must create a detectable configuration drift.

---

# 59. DRIFT DETECTION

JARVIS should detect:

```text
Expected Version
        ≠
Installed Version
```

and:

```text
Expected Digest
        ≠
Installed Digest
```

and:

```text
Expected Hardware Profile
        ≠
Current Hardware Profile
```

and report:

```text
VERSION DRIFT
```

---

# 60. MODEL DRIFT

Model drift includes:

```text
Different Tag Resolution
Different Digest
Different Layer
Different Quantization
Different Template
Different System Prompt
Different Runtime
Different Context
```

A model must therefore be identified beyond its human-readable name.

---

# 61. RUNTIME DRIFT

Runtime drift includes:

```text
Ollama Version Change
CUDA Backend Change
Driver Change
Execution Backend Change
Context Change
Offload Change
Environment Change
```

A runtime change requires targeted verification.

---

# 62. HARDWARE DRIFT

Hardware drift includes:

```text
GPU Replacement
VRAM Change
CPU Replacement
RAM Change
Driver Change
Accelerator Addition
```

Hardware drift does not necessarily invalidate the software architecture.

It may, however, invalidate performance and compatibility assumptions.

---

# 63. RELEASE REPRODUCIBILITY

A release should be reproducible when another environment can reconstruct:

```text
Same Source
+
Same Dependency Lock
+
Same Runtime
+
Same Model Artifact
+
Same Configuration
```

within the documented hardware compatibility boundary.

---

# 64. VERSION LOCK AUTHORITY

When conflicts exist between:

```text
Latest Available
```

and:

```text
Version Lock
```

the Version Lock wins for the current release.

An upgrade requires an explicit Version Lock revision.

---

# 65. VERSION LOCK CHANGE

A Version Lock change must record:

```text
Old Version
New Version
Reason
Evidence
Compatibility Impact
Security Impact
Performance Impact
Migration Impact
Rollback Strategy
Approval
```

---

# 66. MODEL VERSION CHANGE

For model changes, additionally record:

```text
Old Model Digest
New Model Digest
Old Quantization
New Quantization
Old Context
New Context
Old Runtime
New Runtime
Behavior Evaluation
Tool Evaluation
Performance Evaluation
```

---

# 67. HARDWARE PROFILE CHANGE

For hardware changes, record:

```text
Old Hardware Profile
New Hardware Profile
VRAM Difference
Driver Difference
Backend Difference
Performance Difference
Model Compatibility
```

---

# 68. LOCKED CONFIGURATION PRINCIPLE

A version is not sufficiently locked when only the package version is known.

For example:

```text
Ollama 0.32.7
```

is insufficient by itself.

The complete local inference identity is:

```text
Ollama 0.32.7
+
Qwen Model
+
Model Digest
+
GGUF
+
Q4_K_M
+
4096 Context
+
CUDA
+
Driver 610.62
+
GTX 1660 Ti
```

---

# 69. LOCAL INFERENCE ARCHITECTURAL BOUNDARY

The JARVIS Core must not directly depend on Ollama-specific APIs.

The intended boundary is:

```text
JARVIS AI Interface
        ↓
Inference Abstraction
        ↓
Ollama Adapter
        ↓
Ollama Runtime
        ↓
CUDA
        ↓
GPU
```

This preserves the future ability to replace Ollama with:

```text
llama.cpp
vLLM
Transformers
ONNX Runtime
TensorRT-LLM
Cloud Provider
```

without redesigning the JARVIS Core.

The Approved Models specification explicitly distinguishes model from inference runtime for this reason. fileciteturn44file0L109-L125

---

# 70. LOCAL RUNTIME REPLACEMENT

Replacing:

```text
Ollama
```

with another runtime does not necessarily constitute a model change.

However, it does constitute a runtime compatibility change.

Therefore:

```text
Same Model
+
New Runtime
```

requires:

```text
Runtime Validation
+
Performance Validation
+
Behavior Validation
```

before production adoption.

---

# 71. CURRENT BASELINE DECISION

The current local inference baseline is:

```text
============================================================

JARVIS LOCAL INFERENCE BASELINE

OS:
Windows 10 Pro x64

CPU:
Intel Core i7-9750H
6C / 12T

RAM:
~16 GiB

GPU:
NVIDIA GeForce GTX 1660 Ti

VRAM:
6 GiB

NVIDIA DRIVER:
610.62

CUDA UMD:
13.3

RUNTIME:
Ollama 0.32.7

MODEL STORAGE:
D:\AI\Models\Ollama\models

MODELS:
qwen2.5:7b
qwen2.5-coder:7b

QUANTIZATION:
Q4_K_M

EFFECTIVE CONTEXT:
4096

EXECUTION:
CUDA
GPU-ACCELERATED
PARTIAL CPU OFFLOAD

============================================================
```

---

# 72. CURRENT VALIDATION STATUS

```text
Hardware Detection             VALIDATED
NVIDIA CUDA Detection          VALIDATED
Ollama Installation            VALIDATED
Ollama Runtime                 VALIDATED
Model Storage                  VALIDATED
Model Discovery                VALIDATED
Model Manifest                 VALIDATED
Model Blob Integrity           VALIDATED
Qwen2.5 Execution              VALIDATED
Qwen2.5-Coder Execution        VALIDATED
GPU Acceleration               VALIDATED
CPU/GPU Offload                OBSERVED
Performance Baseline           PENDING
Agent Evaluation               PENDING
Tool-Calling Evaluation        PENDING
Security Evaluation            PENDING
Production Approval            PENDING
```

---

# 73. IMPORTANT LIMITATION

The current evidence proves:

```text
The models run.
```

It does **not** yet prove:

```text
The models are the best JARVIS models.
```

It also does not prove:

```text
Production Agent Quality
```

or:

```text
Production Tool-Calling Reliability
```

or:

```text
Production Latency Target
```

Therefore those decisions remain open.

---

# 74. NEXT VALIDATION PHASE

The next model validation phase should measure:

```text
Prompt Latency
Time To First Token
Tokens / Second
VRAM Peak
RAM Peak
CPU Usage
GPU Usage
Tool Calling
Structured Output
Long Context
Error Recovery
Repeated Task Consistency
```

The same workload should be executed against:

```text
qwen2.5:7b
```

and:

```text
qwen2.5-coder:7b
```

where applicable.

---

# 75. MODEL SELECTION RULE

The larger or newer model must not automatically become the JARVIS primary model.

Selection must be based on:

```text
Capability
+
Reliability
+
Tool Use
+
Latency
+
Memory
+
Privacy
+
Cost
+
Hardware Compatibility
```

---

# 76. CURRENT MODEL ROLE HYPOTHESIS

Based only on the current local evidence:

```text
qwen2.5:7b
```

is a general-purpose local candidate.

```text
qwen2.5-coder:7b
```

is a coding-specialized local candidate.

Neither role is permanently locked as the production JARVIS primary model until behavioral evaluation is completed.

---

# 77. VERSION LOCK AND MODEL ROUTER

Version Lock defines:

```text
Which exact model artifacts are available and approved.
```

The Model Router defines:

```text
Which approved model should handle a particular task.
```

These responsibilities must remain separate.

```text
Version Lock
     ↓
Approved Models
     ↓
Model Registry
     ↓
Model Router
     ↓
Task
```

---

# 78. VERSION LOCK AND MANIFEST

Version Lock defines:

```text
Exact Identity
```

Manifest defines:

```text
Required / Optional Components
```

Therefore:

```text
VERSION LOCK
      ↓
Exact versions / artifacts
      ↓
MANIFEST
      ↓
Installation profile
```

---

# 79. VERSION LOCK AND BOOTSTRAP

Bootstrap must not independently decide which production versions to install.

Instead:

```text
Version Lock
      ↓
Bootstrap
      ↓
Exact Version
      ↓
Verification
```

Bootstrap must install what is locked.

It must not silently replace it with:

```text
latest
```

---

# 80. VERSION LOCK AND COMPLIANCE

The Architecture Compliance Checker should compare:

```text
Expected Version Lock
```

against:

```text
Observed Environment
```

and detect:

```text
Version Drift
Artifact Drift
Runtime Drift
Model Drift
Configuration Drift
Hardware Drift
```

---

# 81. VERSION LOCK AND SYSTEM VERIFICATION

System Verification shall verify:

```text
Installed Version
=
Locked Version
```

and, where possible:

```text
Installed Digest
=
Locked Digest
```

and:

```text
Runtime
=
Expected Runtime
```

and:

```text
Model
=
Expected Model
```

---

# 82. VERSION LOCK SECURITY PRINCIPLE

A valid version is not automatically a secure version.

The production baseline requires:

```text
Supported
+
Approved
+
Locked
+
Secure
+
Tested
+
Verified
```

This follows the production release rule already established by Version Support Policy. fileciteturn44file5L918-L942

---

# 83. VERSION LOCK IMMUTABILITY

Once a release is declared:

```text
LOCKED
```

its exact identities should not be silently modified.

A change creates:

```text
New Version Lock Revision
```

rather than an invisible mutation.

---

# 84. VERSION LOCK REVISIONING

Example:

```text
Version Lock v1.0
```

may become:

```text
Version Lock v1.1
```

for controlled updates.

A major architectural change may require:

```text
Version Lock v2.0
```

subject to JAS governance.

---

# 85. AUDITABILITY

Every locked artifact should be traceable to:

```text
Source
+
Evidence
+
Decision
+
Approval
```

For local models:

```text
Model Tag
+
Digest
+
Manifest
+
Blob
+
SHA-256
```

provides the artifact evidence chain.

---

# 86. CURRENT EVIDENCE CHAIN

For the current local Ollama environment:

```text
Hardware
    ↓
NVIDIA Driver
    ↓
CUDA
    ↓
Ollama
    ↓
Model Manifest
    ↓
Layer Digests
    ↓
Local Blobs
    ↓
SHA-256
    ↓
Runtime Execution
```

This chain has been successfully observed and partially validated.

---

# 87. REPRODUCIBILITY TARGET

A future JARVIS developer should be able to reconstruct the local inference environment from this document plus the corresponding bootstrap/configuration artifacts.

The target is:

```text
Fresh Environment
        ↓
Bootstrap
        ↓
Exact Runtime
        ↓
Exact Model
        ↓
Exact Artifact
        ↓
Exact Configuration
        ↓
Validation
        ↓
Reproducible Inference
```

---

# 88. NO FLOATING PRODUCTION DEPENDENCIES

The following patterns are prohibited in the final production Version Lock:

```text
latest
```

```text
unbounded version range
```

```text
mutable model alias without digest
```

```text
unknown runtime
```

```text
unknown model revision
```

```text
unverified artifact
```

---

# 89. DEVELOPMENT FLEXIBILITY

Development environments may temporarily use:

```text
Candidate
Experimental
Newer
```

versions.

However, those versions must remain clearly separated from:

```text
Production Locked
```

state.

---

# 90. FINAL VERSION LOCK CHAIN

The complete governance chain is:

```text
JAS
 ↓
Approved Stack
 ↓
License / Compliance
 ↓
Version Support Policy
 ↓
Roadmap / Technology Evaluation
 ↓
VERSION LOCK
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

# 91. CURRENT DOCUMENT STATUS

```text
============================================================

JAS-AS-26
VERSION LOCK

VERSION:
1.0

STATUS:
DRAFT

CURRENT BASELINE:
LOCAL DEVELOPMENT

HARDWARE:
GTX 1660 Ti / 6 GiB

RUNTIME:
Ollama 0.32.7

LOCAL MODELS:
qwen2.5:7b
qwen2.5-coder:7b

MODEL INTEGRITY:
VALIDATED

GPU ACCELERATION:
VALIDATED

PRODUCTION LOCK:
NOT YET FINAL

============================================================
```

---

# 92. DEFINITION OF DONE

Version Lock v1 shall be considered complete only when:

```text
[ ] All critical software versions identified
[ ] All critical runtime versions identified
[ ] All model revisions identified
[ ] All model digests recorded
[ ] All required artifact digests recorded
[ ] Hardware profiles documented
[ ] Browser revision documented
[ ] Python version documented
[ ] Node version documented
[ ] Package manager versions documented
[ ] Database versions documented
[ ] Redis version documented
[ ] Qdrant version documented
[ ] Docker version documented
[ ] MCP versions documented
[ ] Voice runtime versions documented
[ ] Vision model revisions documented
[ ] Embedding model documented
[ ] Reranker documented
[ ] Security validation completed
[ ] License validation completed
[ ] Performance baselines completed
[ ] Agent evaluation completed
[ ] Tool-calling evaluation completed
[ ] Bootstrap can reproduce the baseline
[ ] Compliance Checker can detect drift
[ ] System Verification passes
```

---

# 93. FINAL ARCHITECTURAL RULES

### Rule 1

**Version Support defines what may be used.**

### Rule 2

**Version Lock defines what is actually used.**

### Rule 3

**A model tag is not an immutable artifact identity.**

### Rule 4

**A model and its runtime are separate versioned components.**

### Rule 5

**A runtime and its hardware/backend form a compatibility profile.**

### Rule 6

**Model artifact integrity must be verified by digest where available.**

### Rule 7

**GPU acceleration must be validated through execution evidence, not a single utilization reading.**

### Rule 8

**Model file size alone is not sufficient for hardware compatibility.**

### Rule 9

**Context configuration belongs to the runtime profile.**

### Rule 10

**Development hardware is not automatically the production hardware requirement.**

### Rule 11

**Production must not depend on mutable `latest` aliases.**

### Rule 12

**A runtime update requires runtime validation.**

### Rule 13

**A model update requires model evaluation.**

### Rule 14

**A hardware change requires compatibility/performance revalidation where relevant.**

### Rule 15

**Version Lock changes must be auditable.**

### Rule 16

**Unknown versions must not silently enter production.**

### Rule 17

**JARVIS Core must remain inference-runtime agnostic.**

### Rule 18

**Local inference must remain replaceable.**

### Rule 19

**The Model Router may choose among approved models but may not bypass Version Lock.**

### Rule 20

**Version Lock is the final authority for the exact production baseline.**

---

# 94. FINAL PRINCIPLE

> **JARVIS must not run whatever happens to be installed.**

It must run:

```text
WHAT WAS APPROVED
        +
WHAT WAS LOCKED
        +
WHAT WAS VERIFIED
```

---

# 95. FINAL RELEASE RULE

```text
SUPPORTED
+
APPROVED
+
EXACT VERSION
+
EXACT ARTIFACT
+
SECURITY PASSED
+
LICENSE PASSED
+
TESTS PASSED
+
SYSTEM VERIFIED
=
PRODUCTION READY
```

---

# 96. END OF DOCUMENT

```text
============================================================

JAS-AS-26
VERSION LOCK v1.0

STATUS:
DRAFT — BASELINE CAPTURED

CURRENT LOCAL INFERENCE:
OLLAMA 0.32.7
+
QWEN2.5 7B
+
QWEN2.5-CODER 7B
+
GTX 1660 Ti 6 GiB
+
CUDA 13.3
+
NVIDIA DRIVER 610.62

============================================================
```

**END OF `26_VERSION_LOCK.md`**