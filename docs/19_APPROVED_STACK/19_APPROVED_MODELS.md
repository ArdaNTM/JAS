# 19 — APPROVED MODELS

**Document ID:** JAS-AS-19  
**Document:** `19_APPROVED_MODELS.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Version:** v1.0  
**Authority:** JAS v1  
**Status:** APPROVED MODEL GOVERNANCE SPECIFICATION  
**Primary Domain:** AI Models, LLMs, Embeddings, Rerankers, Speech, Vision, OCR, Multimodal AI and Model Lifecycle  
**Depends On:** JAS v1, `03_AI_AND_LLM_FRAMEWORKS.md`, `04_AGENT_ORCHESTRATION_STACK.md`, `05_MEMORY_AND_VECTOR_DATABASE_STACK.md`, `08_VOICE_AND_AUDIO_STACK.md`, `09_COMPUTER_VISION_STACK.md`, `14_SECURITY_STACK.md`, `15_DEVOPS_AND_DEPLOYMENT_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Model Registry, Model Router, System Verification, Runtime Configuration, Evaluation System

---

# 1. PURPOSE

This document defines the official model architecture and model approval policy for JARVIS.

The purpose is not merely to maintain a list of models.

It defines:

```text
Which models may be used
+
For which capabilities
+
Under which conditions
+
With which licenses
+
On which hardware
+
With which inference mode
+
At which model revision
+
With which fallback
+
With which evaluation requirements
```

---

# 2. CORE PRINCIPLE

JARVIS must never be architecturally dependent on a single AI model.

The architecture is:

```text
JARVIS
   ↓
Model Abstraction
   ↓
Model Router
   ↓
Capability
   ↓
Approved Model
   ↓
Provider / Runtime
```

rather than:

```text
JARVIS
   ↓
One Model
```

---

# 3. MODEL ≠ PROVIDER

A model and a provider are separate concepts.

For example:

```text
Model
```

may be served by:

```text
Local Runtime
Cloud API
Self-hosted Server
Third-party Inference Provider
```

The model registry must distinguish them.

---

# 4. MODEL ≠ INFERENCE RUNTIME

The same model may be executed through different runtimes.

Examples:

```text
Transformers
vLLM
llama.cpp
ONNX Runtime
TensorRT-LLM
Ollama
Provider API
```

Runtime selection belongs to the infrastructure layer.

---

# 5. MODEL ≠ QUANTIZATION

A model family and a quantized artifact are separate objects.

Example:

```text
Qwen3-32B
```

is different from:

```text
Qwen3-32B-AWQ
```

and:

```text
Qwen3-32B-GGUF
```

The registry must preserve this distinction.

---

# 6. MODEL ≠ CHECKPOINT

A model family can have multiple checkpoints.

Therefore:

```text
Model Family
↓
Checkpoint
↓
Revision
↓
Artifact
```

must be represented explicitly.

---

# 7. MODEL IDENTITY

Every approved model must have a canonical identity.

Minimum:

```text
Provider / Organization
Model Family
Model Variant
Model Revision
Artifact Format
Quantization
```

---

# 8. MODEL REVISION

Production JARVIS deployments must pin a model revision.

---

# 9. `latest`

Production systems must not depend on an implicit:

```text
latest
```

model revision.

---

# 10. MODEL REVISION PINNING

Preferred:

```text
Immutable Revision
```

rather than:

```text
Mutable Branch
```

---

# 11. MODEL HASH

Where supported, model artifacts should be verified using:

```text
SHA-256
```

or an equivalent cryptographic digest.

---

# 12. MODEL REGISTRY

JARVIS will maintain a conceptual Model Registry:

```text
Model Registry
├── Model Identity
├── Capability
├── Provider
├── Runtime
├── Revision
├── License
├── Hardware Requirements
├── Quantization
├── Evaluation
├── Status
└── Fallback
```

---

# 13. MODEL APPROVAL STATES

Approved model states:

```text
APPROVED
CONDITIONALLY APPROVED
EXPERIMENTAL
EVALUATION
DEPRECATED
REJECTED
```

---

# 14. APPROVED

An APPROVED model may be used in production where its capability assignment permits it.

---

# 15. CONDITIONALLY APPROVED

A CONDITIONALLY APPROVED model may be used only under explicitly documented conditions.

Examples:

```text
Specific hardware
Specific license
Specific deployment mode
Specific capability
```

---

# 16. EXPERIMENTAL

Experimental models must not become hidden production dependencies.

---

# 17. EVALUATION

Models under evaluation may be benchmarked but are not production-authorized.

---

# 18. DEPRECATED

Deprecated models remain documented for migration purposes but should not be selected for new deployments.

---

# 19. REJECTED

Rejected models may not be used in JARVIS production.

The rejection reason must be documented.

---

# 20. MODEL CAPABILITY CLASSES

JARVIS will maintain the following model classes:

```text
1. General LLM
2. Reasoning Model
3. Coding Model
4. Small / Edge LLM
5. Embedding Model
6. Reranker
7. Speech-to-Text
8. Text-to-Speech
9. Voice / Audio Model
10. Vision Encoder
11. Vision-Language Model
12. OCR Model
13. Document Retrieval Model
14. Image Generation Model
15. Audio Understanding Model
16. Multimodal Model
17. Specialized Classifier
18. Safety / Moderation Model
19. Auxiliary Model
```

---

# 21. GENERAL LLM

General LLMs provide:

```text
Conversation
Reasoning
Tool Calling
Structured Output
Planning
General Knowledge
```

---

# 22. REASONING MODEL

Reasoning models are optimized for complex inference.

Potential uses:

```text
Planning
Research
Complex Problem Solving
Architecture Analysis
Long-Horizon Tasks
```

---

# 23. CODING MODEL

Coding models are optimized for:

```text
Code Generation
Code Understanding
Debugging
Refactoring
Repository Analysis
```

---

# 24. SMALL / EDGE MODEL

Small models are optimized for:

```text
Low Latency
Low VRAM
Offline Operation
Background Tasks
Classification
Simple Tool Routing
```

---

# 25. EMBEDDING MODEL

Embedding models convert:

```text
Text
Documents
Images
Multimodal Content
```

into vector representations.

---

# 26. RERANKER

Rerankers improve retrieval precision after initial candidate retrieval.

---

# 27. SPEECH-TO-TEXT

STT models convert:

```text
Audio
↓
Text
```

---

# 28. TEXT-TO-SPEECH

TTS models convert:

```text
Text
↓
Audio
```

---

# 29. VISION ENCODER

Vision encoders provide representations for:

```text
Image
Video Frame
Document Image
```

---

# 30. VISION-LANGUAGE MODEL

VLMs combine visual and language reasoning.

---

# 31. OCR MODEL

OCR models convert visual text into machine-readable text.

---

# 32. DOCUMENT RETRIEVAL MODEL

Document retrieval models specialize in retrieving relevant information from visually or structurally complex documents.

---

# 33. MULTIMODAL MODEL

Multimodal models may process combinations of:

```text
Text
Image
Audio
Video
```

---

# 34. SAFETY / MODERATION MODEL

Safety models may classify:

```text
Unsafe Content
Policy Violations
Prompt Injection
Malicious Requests
```

where applicable.

---

# 35. MODEL ROUTING

JARVIS must select models based on capability rather than hard-coded model names.

Example:

```text
User Request
↓
Capability
↓
Model Router
↓
Best Approved Model
```

---

# 36. ROUTING CRITERIA

Model routing may consider:

```text
Capability
Latency
Quality
Cost
Privacy
Hardware
Context Length
Availability
Task Complexity
Power Consumption
```

---

# 37. PRIMARY MODEL

A capability may define a:

```text
Primary Model
```

---

# 38. FALLBACK MODEL

A capability may define:

```text
Fallback Model
```

---

# 39. FALLBACK PRINCIPLE

Fallback must preserve the capability contract as closely as possible.

---

# 40. CLOUD FALLBACK

Local models may fall back to cloud models only when:

```text
Policy
Permission
Privacy
Network
```

conditions allow it.

---

# 41. LOCAL-FIRST POLICY

For privacy-sensitive tasks, local inference should be preferred where capability and quality are sufficient.

---

# 42. CLOUD-FIRST POLICY

For capabilities where local inference cannot provide adequate quality or latency, an approved cloud provider may be selected.

---

# 43. PROVIDER ABSTRACTION

JARVIS must avoid hard-coding provider-specific semantics throughout the core.

---

# 44. MODEL ADAPTER

Provider-specific APIs should be isolated behind model/provider adapters.

---

# 45. MODEL ROUTER ARCHITECTURE

```text
                 USER REQUEST
                      │
                      ▼
                 CAPABILITY
                      │
                      ▼
                 MODEL ROUTER
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
        LOCAL       CLOUD       FALLBACK
          │           │           │
          ▼           ▼           ▼
       Model A      Model B     Model C
```

---

# 46. GENERAL LLM SELECTION CRITERIA

General LLMs are evaluated on:

```text
Reasoning
Instruction Following
Tool Calling
Structured Output
Coding
Multilingual Quality
Context Length
Latency
Reliability
Safety
License
Cost
Local Deployability
```

---

# 47. REASONING EVALUATION

Reasoning models must be tested against JARVIS-specific tasks rather than relying solely on public benchmark scores.

---

# 48. TOOL CALLING EVALUATION

The ability to correctly select and invoke tools is a first-class evaluation criterion.

---

# 49. STRUCTURED OUTPUT

Models used in orchestration should support reliable structured outputs where the selected runtime/provider permits it.

---

# 50. JSON RELIABILITY

Structured output evaluation must measure:

```text
Schema Validity
Field Completeness
Type Correctness
Recovery Rate
```

---

# 51. LONG CONTEXT

Long context capability is useful but does not automatically imply good long-context reasoning.

---

# 52. CONTEXT EVALUATION

JARVIS-specific context tests must evaluate:

```text
Retrieval
Retention
Instruction Priority
Conflict Resolution
```

---

# 53. MULTILINGUAL REQUIREMENT

JARVIS is expected to operate in multiple languages.

Model evaluation should include at minimum:

```text
English
German
Turkish
```

where those languages are required by the deployment.

---

# 54. LANGUAGE QUALITY

Language support must be evaluated separately from English benchmark scores.

---

# 55. LOCAL MODEL POLICY

Local models must provide:

```text
Model Artifact
License
Runtime Compatibility
Hardware Requirements
Revision
```

---

# 56. CLOUD MODEL POLICY

Cloud models must additionally define:

```text
Provider
API Version
Data Handling
Retention
Regional Availability
Pricing
Rate Limits
```

---

# 57. DATA PRIVACY

A model may not be approved for sensitive tasks solely based on benchmark quality.

Its data handling policy must also be acceptable.

---

# 58. CLOUD DATA POLICY

Cloud inference must be routed through security/privacy policy.

---

# 59. USER CONSENT

Tasks requiring external data transmission may require user authorization.

---

# 60. MODEL DATA CLASSIFICATION

JARVIS should classify model inputs as:

```text
PUBLIC
INTERNAL
PRIVATE
SENSITIVE
RESTRICTED
```

---

# 61. MODEL ROUTING BY DATA CLASS

Example:

```text
RESTRICTED
   ↓
LOCAL ONLY
```

unless explicitly authorized otherwise.

---

# 62. MODEL COST

Cloud model cost is a routing criterion.

---

# 63. COST OPTIMIZATION

JARVIS should not use the most expensive model for every request.

---

# 64. MODEL CASCADE

Potential architecture:

```text
Small Model
↓
Does task require escalation?
↓
No → Complete
Yes
↓
Large Model
```

---

# 65. MODEL ESCALATION

Escalation may be triggered by:

```text
Confidence
Task Complexity
Failure
Tool Error
User Request
Policy
```

---

# 66. MODEL CONFIDENCE

Self-reported confidence must not be treated as ground truth.

---

# 67. EXTERNAL VALIDATION

Where correctness matters, model output should be validated through:

```text
Tools
Retrieval
Tests
Structured Validators
External Sources
```

---

# 68. MODEL HALLUCINATION

Hallucination risk is considered a system-level property, not merely a model property.

---

# 69. GROUNDING

Models used for research should support grounded workflows.

---

# 70. RETRIEVAL-AUGMENTED GENERATION

RAG may be used for:

```text
Private Memory
Documentation
Knowledge Bases
Research
```

---

# 71. EMBEDDING REQUIREMENT

The embedding model must be compatible with the memory architecture.

---

# 72. APPROVED EMBEDDING — BGE-M3

`BAAI/bge-m3` is approved as a multilingual embedding candidate for JARVIS memory/retrieval.

Its published model card identifies it as MIT licensed. citeturn0search1

---

# 73. BGE-M3 CAPABILITIES

BGE-M3 is suitable for multilingual text embedding and retrieval workloads.

---

# 74. BGE-M3 STATUS

```text
APPROVED
```

for:

```text
Semantic Memory
Document Retrieval
Multilingual Retrieval
```

subject to evaluation against the JARVIS corpus.

---

# 75. BGE-M3 REVISION

The exact model revision must be pinned in Version Lock.

---

# 76. EMBEDDING DIMENSION

The actual vector dimension must be treated as a versioned schema property.

---

# 77. EMBEDDING MIGRATION

Changing embedding models may require re-indexing memory.

---

# 78. EMBEDDING MODEL CHANGE

A production embedding change is a data migration event.

---

# 79. EMBEDDING COMPATIBILITY

The vector database configuration must match:

```text
Embedding Model
Dimension
Distance Function
Normalization
```

---

# 80. RERANKER

Reranking should be applied where retrieval precision justifies its latency.

---

# 81. APPROVED RERANKER — BGE-RERANKER-V2-M3

`BAAI/bge-reranker-v2-m3` is approved for multilingual retrieval reranking.

Its model card identifies Apache-2.0 licensing. citeturn0search3

---

# 82. RERANKER USE

Recommended pipeline:

```text
Query
 ↓
Embedding Retrieval
 ↓
Top-K Candidates
 ↓
Reranker
 ↓
Top-N Results
 ↓
LLM
```

---

# 83. RERANKER LATENCY

Reranking must be disabled for low-latency tasks where its benefit is insufficient.

---

# 84. RERANKER THRESHOLD

The system may use configurable thresholds for when reranking is activated.

---

# 85. SPEECH-TO-TEXT

JARVIS requires multilingual speech recognition.

---

# 86. APPROVED STT — WHISPER FAMILY

OpenAI Whisper is approved as a local speech recognition model family.

Whisper supports multilingual speech recognition, speech translation and language identification. Its code and model weights are released under MIT. citeturn0search4

---

# 87. WHISPER LARGE V3

`openai/whisper-large-v3` is approved for high-quality local multilingual transcription where hardware permits.

Its Hugging Face model card lists Apache-2.0 for that model repository. citeturn0search15

---

# 88. WHISPER TURBO

Whisper `turbo` may be used for lower-latency transcription when its quality/latency tradeoff passes JARVIS evaluation.

The official Whisper repository documents `turbo` as an available model and notes that it is intended for transcription rather than English translation. citeturn0search4

---

# 89. STT MODEL ROUTING

Potential routing:

```text
Low Latency
↓
Whisper Turbo

High Accuracy
↓
Whisper Large V3
```

---

# 90. STT LANGUAGE DETECTION

Language detection may be performed by the STT system or an auxiliary component.

---

# 91. STT STREAMING

Streaming STT requires an inference/runtime layer capable of incremental processing.

---

# 92. STT PARTIAL RESULTS

Partial transcription must be treated as provisional.

---

# 93. STT FINALIZATION

Only finalized transcription should trigger irreversible actions unless explicitly permitted.

---

# 94. STT COMMAND SAFETY

Voice commands with destructive consequences should require confirmation according to Security Stack.

---

# 95. WAKE WORD

Wake-word detection is separate from the primary STT model.

---

# 96. WAKE-WORD MODEL

A dedicated lightweight model may be used for:

```text
Wake Word Detection
```

---

# 97. WAKE-WORD POLICY

Wake-word models must operate locally whenever possible.

---

# 98. VOICE ACTIVITY DETECTION

VAD is separate from STT.

---

# 99. VAD MODEL

The selected VAD model must optimize:

```text
Latency
False Positives
False Negatives
CPU Usage
```

---

# 100. TTS

JARVIS requires local and potentially cloud TTS.

---

# 101. LOCAL TTS

Local TTS is preferred for:

```text
Privacy
Offline Mode
Low Latency
Fallback
```

---

# 102. PIPER

Piper is recognized as a fast local neural TTS engine.

However, the current `piper1-gpl` project is GPL-3.0 licensed, and individual voices can have separate licensing conditions. citeturn0search10turn0search6

---

# 103. PIPER STATUS

Therefore:

```text
ENGINE:
CONDITIONALLY APPROVED

VOICE MODELS:
INDIVIDUAL LICENSE REVIEW REQUIRED
```

---

# 104. TTS VOICE LICENSE

A TTS engine license does not automatically authorize every voice model.

---

# 105. VOICE MODEL REGISTRY

Each voice must define:

```text
Voice ID
Language
Gender / Style if relevant
Model Revision
License
Attribution
Distribution Rights
```

---

# 106. COMMERCIAL VOICE

Commercial distribution requires separate review of:

```text
Engine License
Voice License
Provider Terms
```

---

# 107. VOICE CLONING

Voice cloning models are subject to additional security and consent requirements.

---

# 108. VOICE CLONING POLICY

A voice may not be cloned or deployed without appropriate authorization.

---

# 109. VISION

JARVIS requires multiple vision model classes.

---

# 110. VISION MODEL CLASSES

```text
Image Encoder
VLM
OCR
Document VLM
Object Detection
Segmentation
Image Retrieval
```

---

# 111. SIGLIP 2

SigLIP 2 is approved as a vision encoder candidate for:

```text
Image Embedding
Image-Text Retrieval
Zero-Shot Classification
```

The published model card lists Apache-2.0 licensing. citeturn1search4turn1search15

---

# 112. SIGLIP 2 STATUS

```text
APPROVED
```

for encoder/retrieval workloads subject to hardware evaluation.

---

# 113. SIGLIP 2 VARIANTS

The exact variant must be selected based on:

```text
Accuracy
VRAM
Latency
Resolution
Deployment Target
```

---

# 114. VISION-LANGUAGE MODELS

A VLM may be used for:

```text
Image Understanding
Screenshot Analysis
Document Understanding
UI Perception
Visual Reasoning
```

---

# 115. PALIGEMMA 2

PaliGemma 2 is a candidate VLM family.

Google documents 3B, 10B and 28B variants with multiple resolutions. citeturn1search1

---

# 116. PALIGEMMA LICENSE

PaliGemma 2 uses Google's Gemma license rather than a permissive license such as MIT or Apache-2.0, and access to model weights may be gated. citeturn1search0turn1search1

---

# 117. PALIGEMMA STATUS

```text
CONDITIONALLY APPROVED
```

Reason:

```text
License review
Gated access
Deployment terms
Model-specific restrictions
```

must be satisfied.

---

# 118. DOCUMENT VISION

Document understanding may use:

```text
OCR
+
Vision Encoder
+
VLM
+
Layout Analysis
```

rather than a single model.

---

# 119. COLPALI

ColPali is approved as a candidate for visual document retrieval.

The published ColPali repository identifies the adapters as MIT licensed but states that the underlying PaliGemma backbone is under the Gemma license. citeturn0search2turn0search0

---

# 120. COLPALI STATUS

```text
CONDITIONALLY APPROVED
```

because its licensing must be evaluated together with its backbone.

---

# 121. VISUAL DOCUMENT RETRIEVAL

Potential architecture:

```text
PDF
 ↓
Rendered Pages
 ↓
Visual Encoder
 ↓
Multi-vector Representation
 ↓
Vector / Late Interaction Retrieval
 ↓
Relevant Pages
 ↓
VLM
```

---

# 122. OCR

OCR should be treated as an independent capability.

---

# 123. OCR MODEL SELECTION

OCR models are evaluated on:

```text
Language
Layout
Tables
Handwriting
Resolution
Speed
```

---

# 124. OCR FALLBACK

If primary OCR fails:

```text
Alternative OCR
↓
VLM
```

may be used.

---

# 125. DOCUMENT PIPELINE

```text
Document
 ↓
Classification
 ↓
OCR / Vision
 ↓
Layout
 ↓
Embedding
 ↓
Retrieval
 ↓
Reranking
 ↓
VLM / LLM
```

---

# 126. MODEL COMPOSITION

JARVIS should prefer specialized model composition when it improves reliability.

---

# 127. SINGLE-MODEL FALLACY

A single multimodal model should not automatically replace specialized models.

---

# 128. MODEL SPECIALIZATION

Use specialized models when they provide:

```text
Higher Accuracy
Lower Latency
Lower Cost
Better Privacy
```

---

# 129. MODEL FALLBACK GRAPH

```text
              PRIMARY
                 │
        ┌────────┴────────┐
        ▼                 ▼
     SUCCESS            FAILURE
        │                 │
        ▼                 ▼
      RESULT          FALLBACK
                          │
                   ┌──────┴──────┐
                   ▼             ▼
                 LOCAL          CLOUD
```

---

# 130. MODEL AVAILABILITY

Model routing must detect availability.

---

# 131. MODEL HEALTH

A model endpoint may be:

```text
AVAILABLE
DEGRADED
UNAVAILABLE
RATE LIMITED
```

---

# 132. MODEL CIRCUIT BREAKER

Repeated model failures may trigger a circuit breaker.

---

# 133. MODEL RETRY

Retries must be bounded.

---

# 134. MODEL TIMEOUT

Every model invocation must have a timeout policy.

---

# 135. MODEL LATENCY

Latency should be measured at:

```text
Queue
Inference
Postprocessing
Total
```

---

# 136. MODEL COST METRICS

Cloud models should track:

```text
Input Tokens
Output Tokens
Requests
Estimated Cost
```

---

# 137. LOCAL RESOURCE METRICS

Local models should track:

```text
VRAM
RAM
CPU
GPU Utilization
Power
Latency
```

---

# 138. MODEL PERFORMANCE

Model performance must be evaluated under JARVIS workloads.

---

# 139. BENCHMARK SOURCES

Public benchmarks may inform candidate selection.

They must not be the sole approval criterion.

---

# 140. JARVIS BENCHMARKS

JARVIS must eventually maintain internal evaluation suites.

---

# 141. GENERAL LLM EVALUATION

Metrics may include:

```text
Instruction Following
Tool Calling
Reasoning
Coding
Structured Output
Multilingual
Hallucination
Safety
Latency
```

---

# 142. AGENT EVALUATION

Models must be evaluated in agentic environments.

---

# 143. AGENT BENCHMARK

Example tasks:

```text
Research
Browser Navigation
File Operations
Coding
Planning
Memory Retrieval
```

---

# 144. TOOL FAILURE

Evaluate whether the model recovers from failed tools.

---

# 145. TOOL SELECTION

Evaluate whether the model chooses the correct tool.

---

# 146. TOOL ARGUMENTS

Evaluate schema correctness.

---

# 147. TOOL SAFETY

Evaluate whether the model avoids unsafe or unauthorized tool use.

---

# 148. MEMORY EVALUATION

Evaluate:

```text
Recall
Precision
Context Relevance
Temporal Reasoning
Conflicting Memory
```

---

# 149. EMBEDDING EVALUATION

Evaluate:

```text
Recall@K
MRR
nDCG
Multilingual Retrieval
Domain Retrieval
```

---

# 150. RERANKER EVALUATION

Evaluate:

```text
Precision@K
nDCG
Latency
```

---

# 151. STT EVALUATION

Metrics:

```text
WER
CER
Language Accuracy
Latency
Noise Robustness
```

---

# 152. TTS EVALUATION

Metrics:

```text
Naturalness
Intelligibility
Latency
Stability
CPU Usage
Voice Consistency
```

---

# 153. VISION EVALUATION

Metrics:

```text
Accuracy
OCR Accuracy
Object Detection
Grounding
Visual Question Answering
UI Understanding
```

---

# 154. MULTIMODAL EVALUATION

Test:

```text
Text → Image
Image → Text
Image → Action
Screenshot → Tool
Document → Answer
```

---

# 155. MODEL SAFETY

Models must be evaluated for:

```text
Prompt Injection
Instruction Hijacking
Tool Abuse
Unsafe Completion
Data Leakage
```

---

# 156. MODEL RED TEAM

Critical models should undergo adversarial evaluation.

---

# 157. MODEL REGRESSION

Changing model versions must trigger regression evaluation.

---

# 158. MODEL UPGRADE ≠ PATCH

A model update is a behavior change even if the API remains identical.

---

# 159. MODEL VERSION UPDATE

Every model update requires:

```text
Evaluation
Compatibility
Resource
License
```

review.

---

# 160. MODEL DEPRECATION

A model becomes deprecated when:

```text
Better Replacement
Security Issue
License Change
Provider Retirement
Performance Regression
```

occurs.

---

# 161. MODEL RETIREMENT

Retirement requires migration planning.

---

# 162. MODEL MIGRATION

```text
Old Model
 ↓
Candidate
 ↓
Parallel Evaluation
 ↓
Shadow Traffic
 ↓
Compatibility
 ↓
Migration
 ↓
Old Model Deprecated
```

---

# 163. SHADOW MODEL

A candidate model may run in shadow mode without affecting user-visible output.

---

# 164. A/B MODEL TESTING

A/B testing is allowed for controlled evaluation.

---

# 165. MODEL CANARY

Production model changes should support canary deployment where infrastructure permits.

---

# 166. MODEL ROLLBACK

Every production model update must have a rollback path.

---

# 167. MODEL ROLLBACK REQUIREMENT

The previous approved revision must remain retrievable until migration is complete.

---

# 168. MODEL STORAGE

Local model artifacts must be stored in a controlled model directory or model cache.

---

# 169. MODEL CACHE

Example:

```text
models/
cache/
```

must not be treated as the model authority.

---

# 170. MODEL AUTHORITY

The authority is:

```text
Model Registry
+
Version Lock
```

---

# 171. MODEL DOWNLOAD

Bootstrap may download models from approved sources.

---

# 172. MODEL DOWNLOAD SECURITY

Downloaded models must be integrity-verified where possible.

---

# 173. MODEL SOURCE

Approved sources may include:

```text
Official Provider
Official Model Repository
Approved Artifact Registry
```

---

# 174. MIRROR

Mirrored models must preserve:

```text
Original Identity
Revision
Digest
License
Provenance
```

---

# 175. MODEL FORMAT

Approved formats may include:

```text
Safetensors
GGUF
ONNX
TensorRT
Provider-specific
```

depending on runtime.

---

# 176. UNSAFE SERIALIZATION

Untrusted model formats capable of arbitrary code execution must not be loaded without security review.

---

# 177. SAFETENSORS

Safetensors is preferred for compatible local model artifacts.

---

# 178. QUANTIZATION

Quantization is a deployment optimization.

---

# 179. QUANTIZATION TYPES

Potential formats:

```text
INT8
INT4
AWQ
GPTQ
GGUF
FP8
BF16
FP16
```

---

# 180. QUANTIZATION APPROVAL

A quantized artifact must be evaluated independently when quality changes materially.

---

# 181. QUANTIZATION QUALITY

A smaller artifact is not automatically equivalent to the original model.

---

# 182. QUANTIZATION TEST

Measure:

```text
Quality
Latency
VRAM
Throughput
Stability
```

---

# 183. LOCAL MODEL HARDWARE

Each model must define:

```text
Minimum RAM
Recommended RAM
Minimum VRAM
Recommended VRAM
CPU Requirement
GPU Requirement
```

---

# 184. HARDWARE PROFILES

JARVIS should eventually support:

```text
CPU_ONLY
ENTRY_GPU
DESKTOP_GPU
HIGH_END_GPU
SERVER_GPU
CLOUD
```

profiles.

---

# 185. CPU-ONLY

CPU-only operation should be supported for lightweight models where practical.

---

# 186. GPU PREFERENCE

GPU acceleration should be used when it materially improves latency.

---

# 187. VRAM ROUTING

Model router may select models based on available VRAM.

---

# 188. MODEL MEMORY BUDGET

A model should not consume the entire system GPU memory without explicit policy.

---

# 189. MEMORY HEADROOM

Runtime should reserve memory for:

```text
OS
Other Services
KV Cache
Vision
Browser
```

where applicable.

---

# 190. MODEL CONCURRENCY

Concurrency must be evaluated.

---

# 191. MODEL QUEUE

Large local models may use request queues.

---

# 192. MODEL PRELOADING

Preloading is allowed for latency-sensitive models.

---

# 193. MODEL UNLOADING

Models may be unloaded when resource pressure requires it.

---

# 194. MODEL MEMORY MANAGER

JARVIS may eventually implement a model lifecycle manager:

```text
LOAD
READY
BUSY
IDLE
UNLOAD
ERROR
```

---

# 195. MODEL WARMUP

Models may require warmup before latency-sensitive execution.

---

# 196. MODEL COLD START

Cold-start latency must be measured.

---

# 197. MODEL SERVER

Large models should preferably run behind a dedicated inference service rather than being loaded independently by every agent.

---

# 198. MODEL SERVICE

Conceptually:

```text
Agent
 ↓
Model Gateway
 ↓
Inference Service
 ↓
Model
```

---

# 199. MODEL GATEWAY

The Model Gateway abstracts:

```text
Provider
Runtime
Model
Version
Authentication
Routing
Fallback
```

---

# 200. MODEL API

The core should interact with stable capability-level interfaces.

---

# 201. MODEL API EXAMPLE

Conceptually:

```text
generate()
embed()
rerank()
transcribe()
synthesize()
vision()
```

rather than provider-specific calls throughout the codebase.

---

# 202. MODEL STREAMING

Models supporting streaming should expose streaming through the model abstraction.

---

# 203. TOKEN STREAMING

LLM streaming should support:

```text
Partial Output
Tool Call Events
Completion
Cancellation
```

---

# 204. CANCELLATION

Long-running model calls must be cancellable where runtime permits.

---

# 205. MODEL CONTEXT MANAGEMENT

Context windows must be tracked by the runtime.

---

# 206. CONTEXT BUDGET

JARVIS should allocate context according to:

```text
System
Memory
Tools
User
Retrieved Data
```

priorities.

---

# 207. MODEL ROUTING + MEMORY

Embedding model and LLM selection must remain separate.

---

# 208. MODEL ROUTING + SECURITY

Security policy may override model quality.

---

# 209. MODEL ROUTING + PRIVACY

Privacy policy may force local inference.

---

# 210. MODEL ROUTING + COST

Cost policy may choose a smaller model where acceptable.

---

# 211. MODEL ROUTING + LATENCY

Interactive voice tasks require low-latency models.

---

# 212. VOICE MODEL ROUTING

Potential:

```text
Wake Word
 ↓
Small STT
 ↓
Small LLM
 ↓
Large LLM only if needed
 ↓
Low-latency TTS
```

---

# 213. RESEARCH ROUTING

Research tasks may use:

```text
Large Reasoning Model
+
Browser
+
Retrieval
+
Citation Validation
```

---

# 214. CODING ROUTING

Coding tasks may use:

```text
Coding Model
+
Repository Tools
+
Tests
+
Static Analysis
```

---

# 215. VISION ROUTING

Vision tasks may use:

```text
Image Encoder
+
OCR
+
VLM
```

depending on task.

---

# 216. DOCUMENT ROUTING

Documents may use:

```text
OCR
+
Layout
+
Embedding
+
Reranker
+
VLM
```

---

# 217. MODEL COMPOSITION POLICY

Use multiple models when specialization improves system-level performance.

---

# 218. MODEL MINIMALISM

Do not deploy ten models where two can satisfy the requirements.

---

# 219. MODEL SPRAWL

Model sprawl increases:

```text
VRAM
Complexity
Maintenance
Security Surface
```

---

# 220. MODEL COUNT

Every model must have a documented purpose.

---

# 221. UNUSED MODEL

Unused production models should be removed.

---

# 222. EXPERIMENTAL MODEL ISOLATION

Experimental models should not pollute production model configuration.

---

# 223. MODEL REGISTRY STRUCTURE

Conceptually:

```text
models/
├── llm/
├── reasoning/
├── coding/
├── embedding/
├── reranker/
├── stt/
├── tts/
├── vision/
├── ocr/
├── multimodal/
└── safety/
```

---

# 224. MODEL METADATA

Each model entry should contain:

```text
id
family
variant
revision
source
license
capability
runtime
format
quantization
hardware
status
evaluation
fallback
```

---

# 225. MODEL MANIFEST

The Manifest will later identify which models are required for installation.

---

# 226. MODEL VERSION LOCK

Version Lock will contain exact model revisions/artifacts.

---

# 227. MODEL BOOTSTRAP

Bootstrap will acquire and verify required models.

---

# 228. MODEL VERIFICATION

System Verification will confirm:

```text
Model Present
Revision Correct
Digest Correct
Runtime Compatible
Hardware Compatible
License Accepted
```

---

# 229. MODEL HEALTH CHECK

Model health check may verify:

```text
Load
Inference
Output
Latency
```

---

# 230. MODEL SMOKE TEST

Every required production model should have a minimal smoke test.

---

# 231. LLM SMOKE TEST

Example:

```text
Simple instruction
→
Valid response
```

---

# 232. EMBEDDING SMOKE TEST

Example:

```text
Text
→
Expected vector dimension
```

---

# 233. RERANKER SMOKE TEST

Example:

```text
Query + Documents
→
Ranking
```

---

# 234. STT SMOKE TEST

Example:

```text
Known audio
→
Expected transcription class
```

---

# 235. TTS SMOKE TEST

Example:

```text
Known text
→
Valid audio
```

---

# 236. VISION SMOKE TEST

Example:

```text
Known image
→
Valid structured result
```

---

# 237. MODEL REGRESSION DATASET

JARVIS should maintain representative evaluation datasets.

---

# 238. DATA PRIVACY

Evaluation datasets containing private user data must be handled according to security policy.

---

# 239. SYNTHETIC TEST DATA

Synthetic datasets should be used where possible for private workflows.

---

# 240. MODEL EVALUATION VERSION

Evaluation suites must themselves be versioned.

---

# 241. BENCHMARK REPRODUCIBILITY

Model benchmark results must record:

```text
Model Revision
Runtime
Hardware
Quantization
Prompt
Dataset Version
Temperature
Decoding Parameters
```

---

# 242. DECODING PARAMETERS

Model behavior can change with:

```text
Temperature
Top-p
Top-k
Max Tokens
Reasoning Settings
```

---

# 243. MODEL CONFIGURATION

Runtime parameters must be version-controlled where they materially affect behavior.

---

# 244. TEMPERATURE

Deterministic workflows should use controlled generation settings.

---

# 245. RANDOM SEED

Where supported, evaluation should use controlled seeds.

---

# 246. NON-DETERMINISM

GPU/runtime nondeterminism must be documented.

---

# 247. MODEL SAFETY EVALUATION

Models must be tested against:

```text
Prompt Injection
Jailbreaks
Tool Abuse
Sensitive Data Extraction
```

---

# 248. SYSTEM PROMPT ROBUSTNESS

Model approval must not assume that a system prompt alone guarantees safety.

---

# 249. TOOL PERMISSION

Security controls remain outside the model.

---

# 250. MODEL TRUST BOUNDARY

```text
MODEL
≠
SECURITY AUTHORITY
```

---

# 251. MODEL NEVER GRANTS PERMISSION

The model may request an action.

The policy engine decides whether the action is allowed.

---

# 252. MODEL OUTPUT VALIDATION

Critical outputs must be validated before execution.

---

# 253. CODE MODEL OUTPUT

Generated code must pass:

```text
Static Analysis
Tests
Security Checks
```

before trusted execution.

---

# 254. BROWSER MODEL OUTPUT

Browser actions must pass browser/tool policy.

---

# 255. SHELL MODEL OUTPUT

Shell commands must pass security policy.

---

# 256. MODEL-BASED PLANNING

Planning models must produce structured plans where possible.

---

# 257. PLAN VALIDATION

Plans must be validated before execution.

---

# 258. MODEL FAILURE

If a model fails:

```text
Retry
↓
Fallback
↓
Escalate
↓
Ask User
```

depending on task risk.

---

# 259. CRITICAL ACTION

For high-impact actions:

```text
Model Failure
→
Do Not Guess
```

---

# 260. MODEL OUTPUT CONFIDENCE

Low confidence should trigger:

```text
Verification
Clarification
Fallback
```

rather than fabricated certainty.

---

# 261. MODEL LICENSE

Every model requires explicit license metadata.

---

# 262. LICENSE TYPES

Examples:

```text
MIT
Apache-2.0
GPL-3.0
Gemma
Proprietary
Commercial API Terms
Research Only
```

---

# 263. LICENSE ≠ API TERMS

A cloud API may have service terms separate from model licensing.

---

# 264. MODEL LICENSE REVIEW

License review must include:

```text
Weights
Code
Tokenizer
Voice
Dataset Restrictions
Provider Terms
```

where relevant.

---

# 265. GATED MODELS

Gated models require explicit access tracking.

---

# 266. GATED ACCESS

Bootstrap must not assume gated model access exists.

---

# 267. LICENSE ACCEPTANCE

If manual license acceptance is required, Bootstrap must report it clearly.

---

# 268. MODEL ATTRIBUTION

Required attribution must be preserved.

---

# 269. MODEL NOTICE

Distributed systems must retain required notices.

---

# 270. MODEL COMMERCIAL USE

Commercial use must be verified independently for each model.

---

# 271. MODEL DISTRIBUTION

Redistribution rights must be verified before packaging model weights.

---

# 272. MODEL HOSTING

Self-hosting rights must be verified.

---

# 273. MODEL FINE-TUNING

Fine-tuning rights must be verified.

---

# 274. MODEL DERIVATIVES

Derivative model rights must be verified.

---

# 275. VOICE MODEL RIGHTS

Voice-specific licenses must be independently evaluated.

---

# 276. DATASET RESTRICTIONS

Model training datasets may impose indirect restrictions depending on the model license/terms.

---

# 277. LICENSE MATRIX

The Approved Software Matrix should eventually reference model license status.

---

# 278. MODEL SECURITY

Model files can be supply-chain attack vectors.

---

# 279. MODEL FILE VALIDATION

Model downloads should verify:

```text
Source
Hash
File Type
Expected Size
Revision
```

---

# 280. MODEL CODE EXECUTION

Model loading mechanisms that execute arbitrary code must require explicit approval.

---

# 281. `trust_remote_code`

Remote code execution mechanisms require security review before approval.

---

# 282. MODEL SANDBOX

Untrusted experimental models should run in isolated environments.

---

# 283. MODEL NETWORK ACCESS

Inference models should not require unrestricted network access unless necessary.

---

# 284. MODEL EXFILTRATION

Model services must not be allowed to exfiltrate user data.

---

# 285. CLOUD MODEL EXFILTRATION

Cloud routing must follow data policy.

---

# 286. MODEL AUDIT

Model invocations should be observable.

---

# 287. MODEL TRACE

Observability should record:

```text
Model ID
Revision
Provider
Latency
Tokens
Outcome
```

without unnecessarily recording private content.

---

# 288. MODEL CONTENT LOGGING

Raw prompts/responses must not be logged by default when they contain private information.

---

# 289. MODEL COST OBSERVABILITY

Cloud model costs should be observable.

---

# 290. MODEL RESOURCE OBSERVABILITY

Local model resource usage should be observable.

---

# 291. MODEL LATENCY SLO

Interactive model classes should eventually have latency targets.

---

# 292. MODEL QUALITY SLO

Important model classes should eventually have quality thresholds.

---

# 293. MODEL AVAILABILITY SLO

Production model services should have availability targets.

---

# 294. MODEL ROUTER TELEMETRY

Router decisions should be observable.

---

# 295. ROUTER EXPLANATION

For debugging, the router should be able to explain:

```text
Selected Model
Rejected Alternatives
Reason
```

without exposing sensitive internal data.

---

# 296. MODEL ROUTING POLICY

Example:

```text
IF private:
    local_model

ELIF latency_critical:
    fast_model

ELIF complex:
    reasoning_model

ELSE:
    default_model
```

Actual routing must use the policy engine rather than hard-coded application logic.

---

# 297. MODEL POLICY OVERRIDE

User may request a specific model where policy allows it.

---

# 298. MODEL USER SELECTION

User-selected models must still be approved models.

---

# 299. UNAPPROVED MODEL REQUEST

If user requests an unapproved model:

```text
Reject
```

or route through explicit experimental mode.

---

# 300. EXPERIMENTAL MODE

Experimental models must be isolated from production state.

---

# 301. MODEL EXPERIMENT

Experimental evaluation must record:

```text
Model
Revision
Purpose
Metrics
Result
```

---

# 302. EXPERIMENT PROMOTION

```text
Experimental
↓
Evaluation
↓
Candidate
↓
Approval
↓
Version Lock
```

---

# 303. MODEL REJECTION

Rejection reasons include:

```text
Poor Quality
High Latency
License
Security
Hardware
Instability
Poor Maintenance
No Deployment Path
```

---

# 304. REJECTION RECORD

Rejected models must be recorded in:

```text
22_REJECTED_TECHNOLOGIES_AND_RATIONALE.md
```

where applicable.

---

# 305. MODEL ROADMAP

Future model families belong in:

```text
25_ROADMAP_AND_FUTURE_TECHNOLOGIES.md
```

until formally evaluated.

---

# 306. MODEL GOVERNANCE

Model approval follows:

```text
Research
↓
Candidate
↓
Evaluation
↓
Security
↓
License
↓
Hardware
↓
JARVIS Benchmark
↓
Approval
↓
Version Lock
```

---

# 307. MODEL APPROVAL BOARD

Final approval should consider:

```text
Engineering
Security
Licensing
Performance
Operations
```

---

# 308. MODEL APPROVAL SCORE

Candidate models may be scored on:

```text
Quality
Reasoning
Tool Calling
Latency
Cost
Hardware
License
Security
Reliability
Maintenance
JAS Compatibility
```

---

# 309. HARD BLOCKERS

A model cannot be approved if:

```text
License incompatible
Security unacceptable
No legal deployment path
Critical unresolved vulnerability
Unacceptable privacy model
```

---

# 310. MODEL SCORE ≠ APPROVAL

A high benchmark score cannot override a hard blocker.

---

# 311. MODEL DIVERSITY

JARVIS should maintain model diversity across:

```text
Cloud
Local
Large
Small
General
Specialized
```

---

# 312. PROVIDER DIVERSITY

Where strategically important, JARVIS should avoid dependence on a single provider.

---

# 313. PROVIDER FAILURE

A provider outage should not necessarily disable all JARVIS capabilities.

---

# 314. LOCAL FALLBACK

Critical capabilities should have local fallback where feasible.

---

# 315. OFFLINE MODE

JARVIS should eventually support a degraded offline mode.

---

# 316. OFFLINE CAPABILITIES

Potential offline capabilities:

```text
STT
Small LLM
Memory Retrieval
TTS
Vision
Basic Tools
```

---

# 317. OFFLINE MODEL PROFILE

```text
OFFLINE_PROFILE
```

may define a minimal model set.

---

# 318. ONLINE PROFILE

```text
ONLINE_PROFILE
```

may enable larger cloud/local models.

---

# 319. HIGH_PERFORMANCE PROFILE

```text
HIGH_PERFORMANCE_PROFILE
```

may select larger models when sufficient GPU resources exist.

---

# 320. MODEL PROFILE ROUTING

Hardware and user policy determine the active profile.

---

# 321. MODEL PROFILE EXAMPLE

```text
CPU_ONLY
→ Small LLM + Whisper + lightweight embeddings

DESKTOP_GPU
→ Medium LLM + Vision + STT + Reranker

HIGH_END_GPU
→ Large LLM + VLM + advanced retrieval

CLOUD
→ Approved cloud frontier models
```

---

# 322. MODEL RESOURCE RESERVATION

JARVIS should prevent multiple large models from exhausting GPU memory.

---

# 323. MODEL SCHEDULING

Future model scheduling may consider:

```text
Priority
Latency
VRAM
Task Type
User Interaction
```

---

# 324. MODEL PREEMPTION

Interactive tasks may preempt background model workloads.

---

# 325. BACKGROUND MODEL TASKS

Examples:

```text
Memory Consolidation
Indexing
Embedding
Summarization
```

---

# 326. BACKGROUND MODEL PRIORITY

Background model tasks should have lower resource priority than interactive tasks.

---

# 327. MODEL BATCHING

Batch inference may be used for background workloads.

---

# 328. MODEL CACHE

Repeated embeddings or inference may use caching where semantically safe.

---

# 329. CACHE INVALIDATION

Model output cache must include model revision/configuration in its key.

---

# 330. MODEL OUTPUT CACHE KEY

Conceptually:

```text
Model Revision
+
Prompt/Input Hash
+
Generation Configuration
```

---

# 331. EMBEDDING CACHE

Embedding cache must include:

```text
Embedding Model Revision
Text Normalization
```

---

# 332. RERANK CACHE

Rerank cache must include:

```text
Reranker Revision
Query
Candidate Set
```

---

# 333. MODEL MIGRATION CACHE

Caches must be invalidated or migrated when model revisions change.

---

# 334. MODEL VERSION LOCK STRUCTURE

Conceptually:

```text
models:
  llm:
    primary:
      provider:
      model:
      revision:
      runtime:
      quantization:

  embedding:
    model:
    revision:

  reranker:
    model:
    revision:

  stt:
    model:
    revision:

  tts:
    model:
    revision:

  vision:
    model:
    revision:
```

---

# 335. MODEL MANIFEST STRUCTURE

Manifest should define:

```text
required
optional
experimental
```

models.

---

# 336. REQUIRED MODEL

Bootstrap must install required models.

---

# 337. OPTIONAL MODEL

Optional models may be installed according to user profile.

---

# 338. EXPERIMENTAL MODEL

Experimental models must require explicit opt-in.

---

# 339. MODEL DOWNLOAD SIZE

Bootstrap should show approximate model download/storage requirements before installation where possible.

---

# 340. MODEL DISK REQUIREMENT

Model provisioning must check available disk space.

---

# 341. MODEL VRAM REQUIREMENT

Model provisioning must check available GPU memory.

---

# 342. MODEL RAM REQUIREMENT

Model provisioning must check available system memory.

---

# 343. MODEL CPU REQUIREMENT

CPU requirements should be recorded for CPU inference.

---

# 344. MODEL DRIVER REQUIREMENT

GPU models must define driver/runtime compatibility where relevant.

---

# 345. MODEL RUNTIME REQUIREMENT

The model registry must define compatible inference runtimes.

---

# 346. MODEL FORMAT REQUIREMENT

The model registry must define expected artifact format.

---

# 347. MODEL ARTIFACT INTEGRITY

Model artifacts must be verified before use.

---

# 348. MODEL LICENSE ACCEPTANCE

Model provisioning must verify required license acceptance.

---

# 349. MODEL PROVENANCE

Model metadata should preserve original source and revision.

---

# 350. MODEL BACKUP

Critical model artifacts may be mirrored to an approved artifact store.

---

# 351. MODEL RE-DOWNLOAD

A failed/corrupted model should be safely re-downloaded.

---

# 352. MODEL CLEANUP

Unused model revisions may be removed after migration.

---

# 353. MODEL RETENTION

The currently deployed revision and rollback revision should remain available during migration.

---

# 354. MODEL DISK GOVERNANCE

JARVIS should prevent uncontrolled accumulation of model versions.

---

# 355. MODEL STORAGE POLICY

Potential structure:

```text
models/
├── registry/
├── active/
├── cache/
└── archive/
```

---

# 356. ACTIVE MODEL

Only approved and verified revisions may appear in active production configuration.

---

# 357. ARCHIVED MODEL

Archived models are retained for rollback/reproducibility.

---

# 358. MODEL DELETION

Model deletion must not break the active deployment.

---

# 359. MODEL RESTORE

Model restore must verify revision and digest.

---

# 360. MODEL REPRODUCIBILITY

A production model configuration must be reconstructable from:

```text
Model Registry
+
Version Lock
+
Artifact Source
+
Digest
```

---

# 361. MODEL DOCUMENTATION

Every approved model must have an official model card or equivalent technical documentation.

---

# 362. MODEL CARD

The model card should document:

```text
Capabilities
Limitations
License
Training Information
Intended Use
Known Risks
```

---

# 363. LIMITATIONS

Model limitations must be represented in the registry.

---

# 364. MODEL LIMITATION → ROUTER

Known limitations may affect routing.

---

# 365. MODEL LIMITATION → SECURITY

Known safety limitations may require additional controls.

---

# 366. MODEL LIMITATION → USER EXPERIENCE

JARVIS should not represent an uncertain model result as verified fact.

---

# 367. MODEL ERROR HANDLING

Model errors should be classified:

```text
TIMEOUT
OOM
INVALID_OUTPUT
PROVIDER_ERROR
SAFETY_BLOCK
RATE_LIMIT
MODEL_UNAVAILABLE
```

---

# 368. MODEL ERROR RETRY

Retry policy must depend on error type.

---

# 369. MODEL OOM

Out-of-memory errors may trigger:

```text
Smaller Model
Quantized Model
CPU
Fallback
```

---

# 370. MODEL RATE LIMIT

Rate limiting may trigger:

```text
Queue
Backoff
Alternative Provider
Local Fallback
```

---

# 371. MODEL SAFETY BLOCK

Safety blocks should not be blindly bypassed.

---

# 372. MODEL INVALID OUTPUT

Invalid structured output should trigger controlled repair or fallback.

---

# 373. MODEL REPAIR

LLM output repair must not create hidden semantic changes.

---

# 374. MODEL SELF-REFLECTION

Self-reflection may improve reliability but must not replace external validation.

---

# 375. MODEL VERIFICATION

For high-risk tasks:

```text
Model
↓
Independent Verification
```

should be preferred.

---

# 376. DUAL-MODEL VERIFICATION

Critical workflows may use:

```text
Generator Model
+
Verifier Model
```

---

# 377. VERIFIER INDEPENDENCE

Where practical, the verifier should not share identical failure modes with the generator.

---

# 378. CODING VERIFICATION

Generated code should be validated by actual execution/tests rather than another LLM alone.

---

# 379. RESEARCH VERIFICATION

Research outputs should be validated against source material.

---

# 380. DOCUMENT VERIFICATION

Extracted document facts should retain provenance.

---

# 381. MODEL PROVENANCE

Responses requiring evidence should retain:

```text
Source
Document
Page
Retrieval Result
```

as applicable.

---

# 382. MODEL + BROWSER

Browser research may use:

```text
LLM
+
Browser
+
Retrieval
+
Citation
```

---

# 383. MODEL + MEMORY

Memory retrieval should be separated from model generation.

---

# 384. MODEL + TOOLS

Tools should remain independent from model implementation.

---

# 385. MODEL + PLUGINS

Plugins may declare required model capabilities rather than specific model names.

---

# 386. PLUGIN MODEL REQUIREMENT

Example:

```text
requires:
  capability: vision
  minimum_quality: X
```

rather than:

```text
requires:
  model: exact-model-name
```

where possible.

---

# 387. MCP MODEL REQUIREMENT

MCP integrations should not assume a specific LLM unless required.

---

# 388. MODEL CAPABILITY CONTRACT

The model abstraction should expose capability-level contracts.

---

# 389. MODEL CAPABILITY EXAMPLE

```text
Capability:
    text_generation
    tool_calling
    vision
    embedding
    reranking
    transcription
    synthesis
```

---

# 390. MODEL APPROVAL TABLE

The initial JARVIS model matrix is:

| Capability | Model / Family | Deployment | License | Status |
|---|---|---|---|---|
| General LLM | Approved frontier provider models | Cloud | Provider Terms | CONDITIONALLY APPROVED |
| Local LLM | Qwen3 family | Local | Apache-2.0 for listed Qwen3 checkpoints | APPROVED |
| Embedding | BGE-M3 | Local | MIT | APPROVED |
| Reranker | BGE-Reranker-v2-M3 | Local | Apache-2.0 | APPROVED |
| STT | Whisper family | Local | MIT / model-artifact-specific review | APPROVED |
| STT High Accuracy | Whisper Large V3 | Local | Apache-2.0 model repository | APPROVED |
| STT Low Latency | Whisper Turbo | Local | Model-specific verification | CONDITIONALLY APPROVED |
| Vision Encoder | SigLIP 2 | Local | Apache-2.0 | APPROVED |
| VLM | PaliGemma 2 | Local | Gemma | CONDITIONALLY APPROVED |
| Visual Retrieval | ColPali | Local | MIT adapters + Gemma backbone | CONDITIONALLY APPROVED |
| TTS | Piper | Local | GPL-3.0 engine | CONDITIONALLY APPROVED |

Qwen3 model repositories such as Qwen3-32B-AWQ and Qwen3-235B-A22B list Apache-2.0 licensing. citeturn0search8turn0search14

---

# 391. QWEN3 LOCAL LLM FAMILY

Qwen3 is approved as a local LLM family candidate.

---

# 392. QWEN3 LICENSE

The referenced Qwen3 model repositories list Apache-2.0 licensing. citeturn0search8turn0search14

---

# 393. QWEN3 VARIANT SELECTION

The exact variant is hardware-dependent.

Potential profiles:

```text
Small
Medium
Large
MoE
Quantized
```

---

# 394. QWEN3 QUANTIZATION

Quantized variants may be used when benchmarked.

---

# 395. QWEN3 MODEL ROUTING

Qwen3 may serve:

```text
Local General LLM
Local Reasoning
Coding
Fallback
Offline Mode
```

depending on selected variant.

---

# 396. FRONTIER CLOUD MODELS

Cloud frontier models remain a separate category.

Because provider model catalogs and terms change rapidly, the exact provider/model revision must be resolved during Version Lock rather than permanently hard-coded into this architectural document.

---

# 397. CLOUD MODEL APPROVAL

A cloud model must satisfy:

```text
Capability
API Stability
Privacy
Security
Terms
Cost
Latency
Reliability
```

---

# 398. CLOUD MODEL VERSION

The API model identifier and provider API version must be locked.

---

# 399. CLOUD MODEL RETIREMENT

Provider retirement must trigger migration planning.

---

# 400. CLOUD MODEL FALLBACK

Critical capabilities should have an alternative model/provider where practical.

---

# 401. MODEL MATRIX PRINCIPLE

The model matrix is a living engineering inventory.

---

# 402. MODEL MATRIX ≠ VERSION LOCK

This document defines approval.

Version Lock defines exact deployed revision.

---

# 403. MODEL MATRIX ≠ MANIFEST

Manifest defines installation requirements.

---

# 404. MODEL MATRIX ≠ ROUTER

Router selects models at runtime.

---

# 405. MODEL GOVERNANCE RELATIONSHIP

```text
Approved Models
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
Model Registry
      │
      ▼
Model Router
      │
      ▼
Runtime
```

---

# 406. MODEL CHANGE PROCESS

```text
Candidate
   ↓
Research
   ↓
License Review
   ↓
Security Review
   ↓
Hardware Evaluation
   ↓
JARVIS Benchmark
   ↓
Integration Test
   ↓
Approval
   ↓
Version Lock
   ↓
Bootstrap
   ↓
Release
```

---

# 407. MODEL UPGRADE PROCESS

```text
Existing Model
      ↓
Candidate Replacement
      ↓
Parallel Evaluation
      ↓
Quality Comparison
      ↓
Latency Comparison
      ↓
Resource Comparison
      ↓
License Comparison
      ↓
Security Comparison
      ↓
Decision
```

---

# 408. MODEL ROLLBACK PROCESS

```text
New Model
 ↓
Failure
 ↓
Detection
 ↓
Router Rollback
 ↓
Previous Model
 ↓
Incident Analysis
```

---

# 409. MODEL INCIDENT

Model incidents should be recorded when:

```text
Quality collapses
Latency becomes unacceptable
Provider fails
Model leaks data
Safety behavior changes
License changes
```

---

# 410. MODEL INCIDENT RESPONSE

```text
Detect
↓
Contain
↓
Rollback
↓
Investigate
↓
Evaluate
↓
Remediate
```

---

# 411. MODEL CHANGELOG

Every production model change must have a changelog entry.

---

# 412. MODEL CHANGE RECORD

Record:

```text
Old Model
New Model
Reason
Evaluation
Risks
Rollback
Approval
```

---

# 413. MODEL APPROVAL DATE

Registry entries should record approval date.

---

# 414. MODEL REVIEW DATE

Long-lived models should have periodic review dates.

---

# 415. MODEL SUPPORT WINDOW

Support lifecycle follows:

```text
Current
Supported
Maintenance
Deprecated
Removed
```

---

# 416. MODEL SUPPORT

A model without upstream support may remain approved if:

```text
Artifact Stable
Security Acceptable
License Acceptable
JARVIS Evaluation Strong
```

---

# 417. MODEL END-OF-LIFE

Provider/model end-of-life requires migration evaluation.

---

# 418. MODEL ROADMAP

Future model families are tracked separately from approved models.

---

# 419. MODEL EXPERIMENTAL AREA

Potential future categories:

```text
Video Models
Real-Time Multimodal Models
Audio-Language Models
World Models
Advanced Reasoning Models
Local Frontier Models
```

---

# 420. FUTURE MODEL PRINCIPLE

A future model is not approved merely because it is newer.

---

# 421. MODEL QUALITY OVER SIZE

Larger parameter count does not automatically mean better JARVIS performance.

---

# 422. MODEL SIZE

Size is one engineering variable:

```text
Quality
Latency
VRAM
Cost
```

must be considered together.

---

# 423. MODEL ROUTER OPTIMIZATION

The optimal system may use several models rather than one largest model.

---

# 424. JARVIS MODEL STACK

Conceptually:

```text
                   JARVIS
                      │
             ┌────────┴────────┐
             │                 │
          ROUTER            MEMORY
             │                 │
      ┌──────┼──────┐          │
      ▼      ▼      ▼          ▼
     LLM    VLM    STT      Embedding
      │      │      │          │
      ▼      ▼      ▼       Reranker
     Tools  Vision Audio       │
             │                  ▼
             └──────────── Retrieval
```

---

# 425. MODEL PRINCIPLE

> **No model is the JARVIS architecture. Models are replaceable capabilities inside the architecture.**

---

# 426. LOCAL-FIRST PRINCIPLE

> **When quality is sufficient, privacy-sensitive workloads should prefer local inference.**

---

# 427. PROVIDER-NEUTRAL PRINCIPLE

> **Core JARVIS logic must not depend on a single model provider.**

---

# 428. VERSION PRINCIPLE

> **Production model identity includes an immutable revision, not merely a model name.**

---

# 429. LICENSE PRINCIPLE

> **Model quality never overrides licensing or deployment restrictions.**

---

# 430. SECURITY PRINCIPLE

> **Models are untrusted reasoning components, not security authorities.**

---

# 431. FALLBACK PRINCIPLE

> **Critical capabilities should have a defined degradation path whenever practical.**

---

# 432. EVALUATION PRINCIPLE

> **JARVIS-specific evaluation outranks marketing benchmarks for production approval.**

---

# 433. REPRODUCIBILITY PRINCIPLE

> **A production model must be reconstructable from its registry, revision and artifact source.**

---

# 434. MODEL MINIMALISM PRINCIPLE

> **Every production model must justify its operational cost and architectural complexity.**

---

# 435. FINAL APPROVED MODEL POLICY

```text
============================================================
              JARVIS APPROVED MODELS v1
============================================================

GENERAL LLM
------------------------------------------------------------
Local Family              Qwen3
Status                    APPROVED
License                   Apache-2.0 on referenced checkpoints
Deployment                Local
Exact Variant             Version Lock

Cloud Frontier
Status                    CONDITIONALLY APPROVED
Provider                  Approved Provider
Exact Model               Version Lock
API Version               Version Lock

============================================================

EMBEDDING
------------------------------------------------------------
Model                     BAAI/bge-m3
Status                    APPROVED
License                   MIT
Primary Use               Semantic / Multilingual Retrieval

============================================================

RERANKER
------------------------------------------------------------
Model                     BAAI/bge-reranker-v2-m3
Status                    APPROVED
License                   Apache-2.0
Primary Use               Retrieval Reranking

============================================================

SPEECH-TO-TEXT
------------------------------------------------------------
Family                    OpenAI Whisper
Status                    APPROVED
Primary Use               Local STT
Languages                 Multilingual

High Accuracy
Model                     Whisper Large V3
Status                    APPROVED

Low Latency
Model                     Whisper Turbo
Status                    CONDITIONALLY APPROVED

============================================================

TEXT-TO-SPEECH
------------------------------------------------------------
Engine                    Piper
Status                    CONDITIONALLY APPROVED
License                   GPL-3.0
Voice License             Per-voice review required

============================================================

VISION ENCODER
------------------------------------------------------------
Family                    SigLIP 2
Status                    APPROVED
License                   Apache-2.0
Primary Use               Image Retrieval / Classification

============================================================

VISION-LANGUAGE
------------------------------------------------------------
Family                    PaliGemma 2
Status                    CONDITIONALLY APPROVED
License                   Gemma
Reason                    License / gated access review

============================================================

VISUAL DOCUMENT RETRIEVAL
------------------------------------------------------------
Model                     ColPali
Status                    CONDITIONALLY APPROVED
Adapters                  MIT
Backbone                  Gemma License
Reason                    Combined license review

============================================================

MODEL GOVERNANCE
------------------------------------------------------------
Revision Pinning          REQUIRED
Artifact Digest           REQUIRED WHERE AVAILABLE
License Metadata          REQUIRED
Hardware Metadata         REQUIRED
Evaluation                REQUIRED
Fallback                  REQUIRED FOR CRITICAL CAPABILITIES
Model Registry            REQUIRED
Version Lock              REQUIRED
Bootstrap Verification    REQUIRED
System Verification       REQUIRED

============================================================
```

# 436. FINAL MODEL ARCHITECTURE

The complete model architecture is:

```text
                       JARVIS
                          │
                          ▼
                    MODEL GATEWAY
                          │
                          ▼
                    MODEL ROUTER
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
    LOCAL               CLOUD             FALLBACK
       │                  │                  │
 ┌─────┼─────┐       Provider A        Provider B
 │     │     │
 ▼     ▼     ▼
LLM   VLM   Audio
 │     │      │
 ▼     ▼      ▼
Tools Vision  STT/TTS
 │
 ▼
Memory / Agents
```

---

# 437. MODEL LIFECYCLE

```text
RESEARCH
   ↓
CANDIDATE
   ↓
EVALUATION
   ↓
SECURITY
   ↓
LICENSE
   ↓
APPROVAL
   ↓
VERSION LOCK
   ↓
BOOTSTRAP
   ↓
VERIFY
   ↓
PRODUCTION
   ↓
MONITOR
   ↓
UPDATE / DEPRECATE
   ↓
REMOVE
```

---

# 438. RELATION TO PREVIOUS APPROVED STACK DOCUMENTS

```text
03 AI / LLM Frameworks
          │
          ▼
19 Approved Models
          │
          ├──→ Version Lock
          │
          ├──→ Manifest
          │
          ├──→ Bootstrap
          │
          ├──→ Model Router
          │
          └──→ System Verification
```

---

# 439. RELATION TO MEMORY

```text
Embedding
    ↓
Vector Database
    ↓
Reranker
    ↓
Relevant Context
    ↓
LLM
```

---

# 440. RELATION TO VOICE

```text
Microphone
    ↓
VAD
    ↓
STT
    ↓
LLM / Agent
    ↓
TTS
    ↓
Speaker
```

---

# 441. RELATION TO VISION

```text
Camera / Screenshot / Document
              ↓
        Vision Encoder
              ↓
       OCR / VLM / Retrieval
              ↓
             Agent
              ↓
            Action
```

---

# 442. RELATION TO AGENTS

```text
Agent
 ↓
Capability Request
 ↓
Model Router
 ↓
Approved Model
 ↓
Structured Result
 ↓
Agent
```

---

# 443. RELATION TO SECURITY

```text
Model
 ↓
Output
 ↓
Validation
 ↓
Policy
 ↓
Tool
```

The model does not bypass policy.

---

# 444. RELATION TO OBSERVABILITY

```text
Model Request
 ↓
Model Revision
 ↓
Provider
 ↓
Latency
 ↓
Tokens / Resources
 ↓
Result
```

---

# 445. RELATION TO TESTING

Every approved model must have:

```text
Smoke Test
Integration Test
Capability Test
Regression Test
```

where applicable.

---

# 446. RELATION TO DEPLOYMENT

Deployment artifacts must reference:

```text
Model ID
Revision
Digest
Runtime
Configuration
```

---

# 447. RELATION TO BUILD SYSTEM

Model artifacts are external build inputs and must be controlled like other supply-chain artifacts.

---

# 448. RELATION TO BOOTSTRAP

Bootstrap must:

```text
Detect
Download
Verify
Install
Register
Test
```

models.

---

# 449. RELATION TO VERSION LOCK

Version Lock is the final authority for the exact production model revision.

---

# 450. RELATION TO MANIFEST

Manifest describes which model artifacts are required/optional for the selected installation profile.

---

# 451. FINAL DECISION

The JARVIS model architecture is therefore:

```text
                       JAS
                        │
                        ▼
                 APPROVED MODELS
                        │
                        ▼
                  MODEL REGISTRY
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
                 MODEL VERIFICATION
                        │
                        ▼
                   MODEL GATEWAY
                        │
                        ▼
                   MODEL ROUTER
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
        LOCAL          CLOUD       FALLBACK
          │             │             │
          └─────────────┼─────────────┘
                        ▼
                     AGENTS
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
            MEMORY    TOOLS     PERCEPTION
                        │
                        ▼
                    JARVIS CORE
```

---

# 452. CONCLUSION

`19_APPROVED_MODELS.md` establishes that JARVIS will not be built around a single model.

Instead, the system will use a governed **Model Stack** consisting of:

```text
General LLM
Reasoning
Coding
Embedding
Reranking
STT
TTS
Vision
VLM
OCR
Document Retrieval
Safety
```

with:

```text
Model Registry
+
Model Router
+
Version Lock
+
Hardware Profiles
+
License Governance
+
Security
+
Evaluation
+
Fallback
```

as the control system.

The initial v1 baseline therefore establishes:

```text
Qwen3
        → Local LLM family

BGE-M3
        → Embeddings

BGE-Reranker-v2-M3
        → Retrieval reranking

Whisper
        → Local STT

SigLIP 2
        → Vision encoder

PaliGemma 2
        → Conditional VLM

ColPali
        → Conditional visual document retrieval

Piper
        → Conditional local TTS
```

while cloud frontier models remain **provider/version-lock decisions rather than permanently hard-coded architecture dependencies**.

This distinction is deliberate: model technology changes much faster than the JAS architecture.

**The architecture must remain stable while the models underneath it remain replaceable.**