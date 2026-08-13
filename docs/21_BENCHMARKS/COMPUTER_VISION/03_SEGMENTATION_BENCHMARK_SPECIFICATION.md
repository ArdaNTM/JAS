# SEGMENTATION BENCHMARK SPECIFICATION

**Document ID:** JAS-CV-BENCH-003

**Version:** 1.0

**Status:** BENCHMARK SPECIFICATION

**Classification:** Computer Vision Evaluation Specification

**Layer:** Computer Vision

---

# 1. Purpose

This document defines the official benchmarking methodology for evaluating image and video segmentation technologies considered for the JAS Computer Vision Stack.

The purpose of the benchmark is not merely to determine which model produces the highest-quality masks.

The benchmark shall determine which segmentation technology provides the best overall balance of:

- segmentation quality
- promptability
- temporal consistency
- interactive refinement
- small-object performance
- occlusion handling
- boundary accuracy
- multi-object capability
- latency
- memory consumption
- reliability
- deployment complexity
- security
- license compatibility
- JAS architectural compatibility

The benchmark shall provide the evidence required before a segmentation implementation can be assigned an official JAS Version 1 role.

No segmentation model shall enter Version Lock solely because it is considered state-of-the-art by external benchmarks.

---

# 2. Scope

This specification covers:

- Image segmentation
- Promptable segmentation
- Interactive segmentation
- Text-guided concept segmentation
- Box-prompted segmentation
- Point-prompted segmentation
- Mask-prompted segmentation
- Multi-object segmentation
- Video object segmentation
- Temporal mask propagation
- Occlusion handling
- Object disappearance and reappearance
- Boundary quality
- Small-object segmentation
- UI element segmentation
- Real-world object segmentation
- JAS-specific segmentation workloads
- Performance benchmarking
- Resource benchmarking
- Reliability evaluation
- Safety evaluation

This document does not define:

- final model versions
- final model weights
- final runtime versions
- final hardware configuration
- final Version Lock entries

Those decisions shall occur only after benchmark completion.

---

# 3. Architectural Definition

Segmentation is defined as the capability of determining which pixels belong to a target visual entity.

The conceptual interface is:

```text
IMAGE / FRAME
       +
OPTIONAL PROMPT
       ↓
SEGMENTATION ENGINE
       ↓
MASK
       +
CONFIDENCE
       +
TARGET METADATA
```

For video:

```text
VIDEO
  ↓
INITIAL TARGET
  ↓
SEGMENTATION
  ↓
TEMPORAL PROPAGATION
  ↓
FRAME N
  ↓
MASK N
```

Segmentation shall remain a perception capability.

It shall not directly perform computer actions.

Therefore:

```text
Vision
 ↓
Segmentation
 ↓
Mask / Target Information
 ↓
Policy
 ↓
Tool
 ↓
Action
```

is the approved architectural direction.

---

# 4. Segmentation Capability Classes

The JAS segmentation architecture shall distinguish between the following capabilities.

```text
SEGMENTATION
│
├── Image Segmentation
├── Promptable Segmentation
├── Concept Segmentation
├── Interactive Segmentation
├── Multi-Object Segmentation
├── Video Segmentation
└── Temporal Segmentation
```

These capabilities shall be benchmarked separately.

A model performing well in one category shall not automatically receive equivalent approval for another.

---

# 5. Candidate Technologies

The initial candidate pool shall include:

- SAM 2
- SAM 2.1
- SAM 3
- SAM 3.1

Additional segmentation technologies may be evaluated if they satisfy the Approved Stack governance requirements.

The benchmark shall not assume that the newest model is automatically the best model.

---

# 6. Primary Candidate: SAM 3.1

SAM 3.1 shall be evaluated as a primary candidate because the current Meta architecture combines detection, segmentation, and tracking capabilities and introduces object multiplexing for improved video processing efficiency. Meta reports that SAM 3.1 can track up to 16 objects in a single forward pass and reports approximately 32 FPS throughput on a single H100 for a medium number of objects. These figures are external reference figures and SHALL NOT be treated as JAS benchmark results. citeturn0search3

SAM 3.1 shall therefore be evaluated for:

- image segmentation
- promptable segmentation
- concept segmentation
- multi-object segmentation
- video segmentation
- temporal consistency
- tracking-assisted segmentation
- crowded-scene segmentation

---

# 7. Baseline Candidate: SAM 2.1

SAM 2.1 shall remain in the benchmark as an important baseline.

Meta describes SAM 2 as a unified model for promptable segmentation in images and videos, supporting point, box, and mask prompts and using session memory for video propagation. SAM 2.1 introduced an updated checkpoint with improvements for visually similar objects, small objects, and occlusion handling. citeturn0search0turn0search1turn0search6

SAM 2.1 therefore provides an important baseline for:

- image segmentation
- interactive segmentation
- video segmentation
- temporal propagation
- occlusion handling
- resource efficiency

---

# 8. Concept Segmentation

Modern JAS workloads require more than fixed semantic classes.

The benchmark shall therefore include:

```text
"person"
```

but also:

```text
"the person holding a phone"
"the red umbrella"
"the blue button"
"the object next to the laptop"
"the striped backpack"
```

This capability shall be classified as:

**Concept Segmentation**

SAM 3 introduced Promptable Concept Segmentation in which text or exemplar prompts can define concepts and the system returns masks and identities for matching instances. Meta also released the SA-Co benchmark for this task. citeturn0search9

SA-Co may be used as an external benchmark reference, while JAS-specific tests remain mandatory.

---

# 9. Prompt Types

The benchmark shall evaluate the following prompt types where supported:

## 9.1 Point Prompt

```text
Image
+
Positive Point
↓
Mask
```

---

## 9.2 Negative Point

```text
Image
+
Positive Point
+
Negative Point
↓
Refined Mask
```

---

## 9.3 Bounding Box Prompt

```text
Image
+
Bounding Box
↓
Mask
```

---

## 9.4 Existing Mask Prompt

```text
Image
+
Initial Mask
↓
Refined Mask
```

---

## 9.5 Text Prompt

```text
Image
+
"red car"
↓
Mask
```

---

## 9.6 Exemplar Prompt

```text
Image
+
Reference Image
↓
Target Mask
```

Only prompt types actually supported by the evaluated implementation shall be tested.

Unsupported capabilities shall be recorded as:

```text
N/A
```

rather than treated as failures.

---

# 10. Level 1 — Standard Image Segmentation

The first benchmark level shall measure conventional image segmentation quality.

Candidate datasets may include:

- SA-1B-derived evaluation subsets
- COCO
- LVIS
- standard segmentation benchmarks
- official model benchmark datasets

The exact dataset and subset shall be frozen before final benchmark execution.

---

# 11. Level 1 Metrics

Primary image segmentation metrics:

```text
Mask IoU
mIoU
Boundary IoU
Dice / F1
Precision
Recall
```

Where the benchmark supports instance segmentation:

```text
Mask AP
Mask AP50
Mask AP75
```

shall also be recorded.

---

# 12. Mask IoU

The primary pixel-level metric shall be:

```text
IoU =
Intersection(M_pred, M_gt)
/
Union(M_pred, M_gt)
```

where:

```text
M_pred = predicted mask
M_gt   = ground-truth mask
```

Higher values indicate better overlap.

---

# 13. Boundary Quality

A mask may achieve reasonable IoU while producing poor object boundaries.

This is particularly problematic for:

- hair
- fingers
- thin objects
- icons
- irregular objects
- UI elements
- partially transparent objects

Therefore the benchmark shall separately measure boundary quality.

Primary boundary metrics:

```text
Boundary IoU
Boundary F-score
Contour deviation
```

---

# 14. Level 2 — Interactive Segmentation

Interactive segmentation is highly relevant to JAS because future Vision interfaces may receive iterative corrections.

Example:

```text
User:
"Segment this object."

       ↓

Point Prompt

       ↓

Mask

       ↓

User:
"Not that part."

       ↓

Negative Point

       ↓

Refined Mask
```

The benchmark shall measure how efficiently a model reaches a high-quality mask after user interaction.

---

# 15. Interaction Efficiency

The benchmark shall measure:

```text
Interactions to IoU ≥ threshold
```

Example:

```text
1 interaction → IoU 0.70
2 interactions → IoU 0.85
3 interactions → IoU 0.92
```

This shall be recorded as:

```text
Interaction Efficiency
```

---

# 16. Human-in-the-Loop Simulation

Human interaction shall be simulated using deterministic policies where possible.

Examples:

```text
Positive point
Negative point
Boundary correction
Box correction
```

The same prompt policy shall be applied to all candidates.

This prevents benchmark bias.

---

# 17. Level 3 — Video Segmentation

Video segmentation is a separate capability.

Input:

```text
VIDEO
+
INITIAL PROMPT
```

Output:

```text
FRAME 1 → MASK
FRAME 2 → MASK
FRAME 3 → MASK
...
FRAME N → MASK
```

The benchmark shall evaluate both spatial mask quality and temporal consistency.

SAM 2 explicitly uses a memory mechanism for video propagation and is designed for streaming video segmentation, making temporal evaluation an essential part of the benchmark. citeturn0search0

---

# 18. Video Segmentation Metrics

Primary metrics:

```text
Mean IoU over frames
Mask AP over frames
Temporal IoU
Temporal Consistency
Identity Consistency
Boundary Stability
```

Performance:

```text
FPS
P50 latency
P95 latency
P99 latency
```

Resource:

```text
Peak VRAM
Average VRAM
CPU utilization
GPU utilization
```

---

# 19. Temporal Consistency

A segmentation system may produce individually accurate masks while visibly flickering between frames.

Therefore:

```text
Mask_t
```

and:

```text
Mask_(t+1)
```

shall be compared.

Temporal consistency shall consider:

- mask overlap
- boundary movement
- object identity
- unnecessary mask changes
- temporal flicker

The objective is:

```text
High spatial accuracy
+
Low temporal instability
```

---

# 20. Occlusion Benchmark

The benchmark shall contain objects that:

- become partially occluded
- become fully occluded
- disappear temporarily
- reappear
- overlap with similar objects

Example:

```text
PERSON
 ↓
behind object
 ↓
partial visibility
 ↓
reappears
```

The system shall be evaluated on whether it:

1. preserves the correct identity,
2. avoids mask contamination,
3. correctly recovers after reappearance.

---

# 21. Identity Consistency

For multi-object video segmentation:

```text
Object A
Object B
Object C
```

shall maintain stable identities.

Example failure:

```text
Frame 1:
A = Person 1
B = Person 2

Frame 50:
A = Person 2
B = Person 1
```

This shall be classified as:

**Identity Switch**

Identity switches shall be recorded separately from segmentation accuracy.

---

# 22. Multi-Object Segmentation

The benchmark shall evaluate:

```text
1 object
2 objects
4 objects
8 objects
16 objects
```

where supported.

This is especially important because current SAM 3.1 architecture explicitly introduces object multiplexing for processing multiple tracked objects in a shared forward pass. citeturn0search3

The benchmark shall determine whether the efficiency advantage remains under JAS workloads.

---

# 23. Crowded Scene Benchmark

Special test cases:

```text
multiple people
multiple similar vehicles
multiple identical objects
overlapping objects
dense UI
```

The objective is to measure:

```text
Object Separation
+
Identity Stability
+
Boundary Accuracy
```

---

# 24. Small Object Segmentation

Special benchmark category:

```text
Tiny Target
```

Target sizes shall include approximately:

```text
< 5% image area
< 1% image area
< 0.5% image area
< 0.1% image area
```

The exact thresholds shall be determined according to the dataset resolution.

This category is especially important for:

- UI icons
- buttons
- status indicators
- small tools
- distant objects
- camera scenes

---

# 25. Boundary-Critical Objects

Separate benchmark samples shall contain:

- hair
- wires
- cables
- thin objects
- transparent objects
- irregular contours
- overlapping objects

These cases shall be evaluated using boundary metrics rather than IoU alone.

---

# 26. UI Segmentation

Computer-use requires accurate segmentation of visual interface components.

JAS-specific UI segmentation categories shall include:

```text
Button
Checkbox
Radio Button
Slider
Icon
Window
Panel
Dialog
Tab
Input Field
Menu
Tooltip
Notification
```

The objective is not merely to detect the UI element.

The system must produce a mask sufficiently accurate for downstream visual reasoning.

---

# 27. UI Boundary Accuracy

For UI elements:

```text
Button
```

a bounding box may be insufficient.

The segmentation engine should ideally distinguish:

```text
button background
button border
button label
neighboring elements
```

where required by the downstream capability.

However, segmentation shall not be used as a substitute for OCR or UI semantic parsing.

---

# 28. Real-World Camera Benchmark

JAS shall include camera-based scenarios:

```text
Indoor
Outdoor
Low Light
Bright Light
Motion Blur
Occlusion
Reflections
Shadows
Crowded Scenes
```

Object classes shall include:

```text
Person
Phone
Laptop
Keyboard
Cup
Bottle
Vehicle
Animal
Tool
Furniture
```

The exact category list shall be frozen before evaluation.

---

# 29. Desktop Screenshot Benchmark

Separate screenshot scenarios shall include:

```text
Browser
IDE
Terminal
File Manager
Settings
Documents
Media Player
Communication Applications
```

Tests shall include:

```text
Dark Mode
Light Mode
Different Scaling
Different Resolutions
Different UI Themes
```

---

# 30. Resolution Benchmark

Primary resolutions:

```text
1920 × 1080
2560 × 1440
3840 × 2160
```

Secondary resolutions may include:

```text
1366 × 768
1280 × 720
```

The purpose is to determine whether segmentation quality and latency degrade significantly with increasing image size.

---

# 31. Performance Benchmark

All models shall be tested under:

```text
Batch = 1
```

as the primary JARVIS configuration.

Additional throughput tests may use:

```text
Batch = 4
Batch = 8
Batch = 16
```

when supported.

Batch throughput shall never replace batch-1 latency as the primary interactive metric.

---

# 32. Warm-Up Protocol

Before measurement:

```text
20 warm-up inferences
```

shall be performed unless the model architecture requires a different initialization procedure.

The benchmark shall then perform:

```text
200 measured inferences
```

or an equivalent statistically sufficient workload.

---

# 33. Latency Metrics

The following shall be recorded:

```text
Cold Start
Model Load
First Inference
Mean
P50
P90
P95
P99
```

For video:

```text
Frames Per Second
Time Per Frame
Startup Latency
Memory Initialization
```

shall additionally be recorded.

---

# 34. VRAM Benchmark

Memory shall be measured at:

```text
Before model loading
After model loading
Peak inference
Steady state
```

The report shall distinguish:

```text
Model Memory
Runtime Memory
Peak Memory
```

This distinction is required because total process memory alone does not adequately explain deployment requirements.

---

# 35. Precision Benchmark

Where supported:

```text
FP32
FP16
BF16
INT8
```

may be evaluated.

The benchmark shall compare:

```text
Quality
Latency
VRAM
Stability
```

between precision modes.

No precision mode shall be approved solely because it is faster.

---

# 36. Quality Regression Threshold

A reduced-precision implementation shall not be considered equivalent to the full-precision implementation unless:

```text
Quality degradation
```

remains below the threshold defined by the final JAS evaluation policy.

The threshold shall be established after baseline measurements rather than arbitrarily selected before the benchmark.

---

# 37. Reliability Benchmark

Each candidate shall undergo repeated inference testing.

The benchmark shall record:

```text
Successful Inferences
Failed Inferences
Timeouts
Crashes
Memory Errors
Invalid Outputs
Malformed Masks
NaN / Inf Outputs
```

Primary reliability metric:

```text
Successful Valid Inferences
/
Total Inferences
```

---

# 38. Output Validation

Every segmentation result shall pass structural validation.

Required output properties:

```text
Mask Exists
Mask Dimensions Correct
Mask Values Valid
Mask Coordinates Valid
No Unexpected NaN
No Unexpected Inf
Confidence Valid
Target Identity Valid where applicable
```

Malformed output shall count as a failed inference.

---

# 39. Recovery Benchmark

The system shall be tested against:

```text
Temporary GPU failure
Invalid prompt
Empty prompt
Invalid image
Oversized image
Unsupported format
Memory pressure
Timeout
```

The segmentation subsystem shall fail safely.

It shall not crash the JAS core.

---

# 40. Safety Requirements

Segmentation is a perception component and shall not independently trigger external actions.

The following architecture is mandatory:

```text
Segmentation
      ↓
Perception Result
      ↓
Policy Validation
      ↓
Action Authorization
      ↓
Tool
```

A segmentation result shall never be interpreted as authorization.

---

# 41. High-Risk Segmentation

Special benchmark scenarios shall include targets associated with:

```text
Delete
Purchase
Send
Publish
Execute
Install
Uninstall
Reset
Format
```

The segmentation subsystem shall only identify the visual region.

Action authorization belongs to the Security and Policy layers.

---

# 42. Adversarial Segmentation

Special cases:

```text
Visually similar objects
Overlapping objects
Partial objects
Misleading colors
Extreme lighting
Blurred boundaries
Low contrast
Compression artifacts
```

shall be included.

The benchmark shall measure whether segmentation incorrectly absorbs neighboring objects.

---

# 43. Mask Contamination

A critical segmentation error is:

```text
TARGET
+
NEIGHBOR
↓
ONE MASK
```

This shall be measured as:

**Mask Contamination Rate**

Definition:

```text
Contaminated Predictions
/
Total Predictions
```

Lower is better.

---

# 44. Under-Segmentation

Example:

```text
Target = Person
Prediction = torso only
```

shall be classified as:

**Under-Segmentation**

---

# 45. Over-Segmentation

Example:

```text
Target = Phone
Prediction = Phone + Hand + Table
```

shall be classified as:

**Over-Segmentation**

Both errors shall be tracked separately.

---

# 46. Temporal Drift

For video:

```text
Frame 1
Target = Object A

Frame 100
Mask gradually shifts toward Object B
```

shall be classified as:

**Temporal Drift**

This is separate from ordinary IoU degradation.

---

# 47. Reappearance Recovery

Special test:

```text
Object visible
↓
Object disappears
↓
Object returns
```

The system shall be evaluated on:

```text
Correct Re-identification
Mask Recovery
Identity Preservation
Recovery Latency
```

---

# 48. Interactive Refinement Benchmark

The benchmark shall measure:

```text
Initial Mask Quality
↓
Correction
↓
Refined Mask
↓
Correction
↓
Final Mask
```

Primary metrics:

```text
IoU improvement per interaction
Boundary improvement per interaction
Interactions to target quality
```

A model requiring fewer user corrections shall receive higher interaction efficiency.

---

# 49. Segmentation Efficiency

The benchmark shall calculate:

```text
Quality / VRAM
Quality / Latency
Quality / GPU Utilization
```

This prevents a very large model from automatically winning solely because it has the highest raw quality.

---

# 50. JAS Segmentation Score

The initial scoring proposal is:

```text
Image Quality                 20%
Video Quality                 20%
Boundary Quality              10%
Interactive Performance       10%
Temporal Consistency          10%
Small / Difficult Objects     10%
Reliability                    5%
Latency                        5%
Resource Efficiency            5%
JAS Compatibility              5%
```

Total:

```text
100%
```

This weighting shall remain provisional until baseline measurements are available.

---

# 51. Veto Criteria

Weighted scoring shall not override critical failures.

The following shall be veto conditions:

```text
Critical Security Failure
Critical License Incompatibility
Unrecoverable Runtime Instability
Unacceptable Output Corruption
Critical Unsafe Behavior
Unsupported Required Deployment Platform
```

A model receiving a veto cannot become PRIMARY regardless of numerical score.

---

# 52. License Evaluation

License compatibility shall be evaluated independently.

The benchmark shall record:

```text
Model License
Code License
Weight License
Dataset License
Dependency Licenses
Commercial Restrictions
Redistribution Restrictions
Attribution Requirements
```

Technical performance shall never override an incompatible license.

---

# 53. External Benchmark vs JAS Benchmark

External benchmark results shall be treated as:

```text
REFERENCE
```

not:

```text
JAS RESULT
```

For example, Meta reports performance characteristics for SAM 2 and SAM 3.1 using their own benchmark environments and hardware. These figures provide useful context but cannot replace JAS-controlled measurements. citeturn0search0turn0search3

---

# 54. Hardware Control

All candidate models shall be evaluated on identical hardware whenever practical.

The benchmark record shall include:

```text
GPU
VRAM
CPU
RAM
Operating System
CUDA Version
Driver Version
Runtime Version
Model Precision
Input Resolution
Batch Size
```

No two performance numbers shall be directly compared without confirming environment compatibility.

---

# 55. Reproducibility

Every benchmark execution shall record:

```text
Model Identifier
Model Revision
Code Revision
Dataset Revision
Dataset Hash
Runtime Version
Dependency Lock
Hardware
Precision
Configuration
Benchmark Version
Timestamp
```

The benchmark must be reproducible from the recorded environment.

---

# 56. Benchmark Result Format

Each candidate shall produce a normalized result record.

Example:

```yaml
technology: SAM_3_1

capabilities:
  image_segmentation: PASS
  promptable_segmentation: PASS
  concept_segmentation: PASS
  video_segmentation: PASS
  multi_object_segmentation: PASS

quality:
  mean_iou: ...
  boundary_iou: ...
  mask_ap: ...

video:
  temporal_consistency: ...
  identity_consistency: ...
  fps: ...

performance:
  p50_ms: ...
  p95_ms: ...
  p99_ms: ...

resources:
  peak_vram_mb: ...
  cpu_utilization: ...
  gpu_utilization: ...

reliability:
  success_rate: ...

safety:
  status: PASS

license:
  status: PASS

decision:
  status: PRIMARY / SECONDARY / FALLBACK / EXPERIMENTAL / REJECTED
```

---

# 57. Decision Categories

After benchmark completion, each technology shall receive one of:

```text
PRIMARY
SECONDARY
SPECIALIST
FALLBACK
EXPERIMENTAL
DEPRECATED
REJECTED
```

Possible architecture:

```text
Primary Segmentation
        ↓
SAM 3.1

Legacy / Lightweight Fallback
        ↓
SAM 2.1

Specialized Implementation
        ↓
Future candidate
```

This is only an example architecture.

The benchmark must determine the actual result.

---

# 58. Architecture Abstraction

The implementation shall be hidden behind a stable interface.

Conceptually:

```python
class SegmentationEngine:

    def segment(
        self,
        image,
        prompt=None,
        *,
        mode=None,
    ):
        ...
```

For video:

```python
class VideoSegmentationEngine:

    def initialize(self, frame, prompt):
        ...

    def propagate(self, frame):
        ...
```

The exact API shall be finalized during the implementation architecture phase.

---

# 59. Capability Separation

The following interfaces shall remain logically distinct:

```text
Detector
Grounder
Segmenter
Tracker
OCR
Vision Reasoner
```

A single foundation model may implement multiple interfaces.

However:

```text
One Model
≠
One Capability
```

This separation allows JAS to replace one capability without restructuring the entire Computer Vision subsystem.

---

# 60. Current Architecture Hypothesis

Based on current technology capabilities, the initial architecture hypothesis is:

```text
                 VISION
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
   Detection     Grounding   Segmentation
       │            │            │
    RT-DETR     Specialist    SAM Family
       │            │            │
       └────────────┼────────────┘
                    ↓
                 Tracking
```

The exact implementations remain subject to benchmark results.

---

# 61. Current Segmentation Candidates

At this stage:

```text
SAM 3.1
    ↓
Primary Candidate

SAM 2.1
    ↓
Baseline / Fallback Candidate

SAM 3
    ↓
Reference Candidate

Additional Models
    ↓
Optional Evaluation
```

This is **not yet a Version Lock decision**.

---

# 62. What Is Now Locked

The following architectural rules are now established for the benchmark:

```text
✓ Segmentation is a separate capability
✓ Image and video segmentation are separately evaluated
✓ Promptable segmentation is separately evaluated
✓ Concept segmentation is separately evaluated
✓ Interactive refinement is benchmarked
✓ Temporal consistency is benchmarked
✓ Identity consistency is benchmarked
✓ Boundary quality is benchmarked
✓ Small objects receive dedicated tests
✓ UI segmentation receives dedicated tests
✓ Batch=1 is the primary latency configuration
✓ Cold and warm inference are separated
✓ VRAM is measured separately
✓ Reliability is measured
✓ Safety is a veto criterion
✓ License compatibility is a veto criterion
✓ External benchmark numbers are not JAS results
✓ Exact model artifacts are not yet Version Locked
```

---

# 63. What Is Not Yet Locked

The following decisions remain open:

```text
✗ Final segmentation model
✗ Exact model checkpoint
✗ Exact model revision
✗ Runtime
✗ Precision
✗ Input resolution
✗ Hardware
✗ Minimum IoU requirement
✗ Minimum temporal consistency requirement
✗ Minimum FPS requirement
✗ Final VRAM ceiling
✗ Final primary/fallback architecture
```

These shall only be decided after benchmark execution.

---

# 64. Benchmark Execution Flow

The official evaluation sequence shall be:

```text
Candidate
   ↓
Environment Validation
   ↓
Model Integrity Validation
   ↓
Image Benchmark
   ↓
Prompt Benchmark
   ↓
Interactive Benchmark
   ↓
Concept Benchmark
   ↓
Video Benchmark
   ↓
Multi-Object Benchmark
   ↓
Occlusion Benchmark
   ↓
Small-Object Benchmark
   ↓
UI Benchmark
   ↓
Latency Benchmark
   ↓
VRAM Benchmark
   ↓
Reliability Benchmark
   ↓
Safety Evaluation
   ↓
License Evaluation
   ↓
Score
   ↓
Architecture Decision
```

---

# 65. Final Principle

The JAS segmentation strategy shall not be:

```text
"Use the newest SAM."
```

It shall be:

```text
Requirement
    ↓
Candidate
    ↓
Controlled Benchmark
    ↓
Evidence
    ↓
Architectural Evaluation
    ↓
Decision
    ↓
Version Lock
```

The purpose of the Approved Stack is not to predict which technology will win.

Its purpose is to ensure that **the technology that wins is selected for measurable reasons and can later be replaced without destabilizing JAS.**

---

# 66. Next Evaluation Stage

After segmentation, the next Computer Vision capability shall be:

**TRACKING BENCHMARK SPECIFICATION**

The tracking benchmark shall evaluate:

```text
Object Tracking
Multi-Object Tracking
Video Identity Persistence
Occlusion Recovery
Re-Identification
Temporal Stability
Track Switching
Track Fragmentation
Latency
Memory
```

The relationship shall be:

```text
Detection
    ↓
Grounding
    ↓
Segmentation
    ↓
Tracking
```

but these capabilities shall remain independently replaceable.

# End of Document