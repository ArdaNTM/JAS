# OBJECT DETECTION BENCHMARK SPECIFICATION

**Document ID:** JAS-CV-BENCH-001

**Version:** 1.0

**Status:** BENCHMARK SPECIFICATION

**Classification:** Computer Vision Evaluation Specification

**Layer:** Computer Vision

---

# 1. Purpose

This document defines the official benchmarking methodology for evaluating object detection technologies considered for the JAS Computer Vision Stack.

The purpose of this benchmark is to determine which object detection technologies provide the best combination of:

- detection accuracy
- latency
- throughput
- memory efficiency
- reliability
- deployment compatibility
- scalability
- JAS architectural compatibility
- security
- license compatibility

The benchmark shall provide objective evidence before any object detection technology is assigned an official role within JAS Version 1.

No technology shall be added to Version Lock solely because of popularity, community adoption, published benchmark results, or vendor claims.

---

# 2. Scope

This specification governs evaluation of:

- Standard object detection
- Real-time object detection
- Multi-class detection
- Small-object detection
- Crowded-scene detection
- Occlusion handling
- Computer-vision perception
- Camera-based detection
- Desktop perception
- Browser perception
- UI-related object detection
- Detection latency
- Detection throughput
- Resource consumption
- Reliability
- Safety
- Deployment compatibility

This specification does not define:

- final model versions
- final model weights
- final runtime versions
- final hardware configuration
- final Version Lock entries

Those decisions shall be made only after benchmark execution and architectural review.

---

# 3. Architectural Definition

Object Detection is defined as the capability of locating and classifying objects within an image or video frame.

The conceptual interface is:

```text
IMAGE / FRAME
      ↓
OBJECT DETECTOR
      ↓
Bounding Boxes
      +
Class Labels
      +
Confidence
```

For multiple objects:

```text
IMAGE
  ↓
DETECT
  ↓
┌─────────────────────────┐
│ Object A                │
│ bbox + class + score    │
├─────────────────────────┤
│ Object B                │
│ bbox + class + score    │
├─────────────────────────┤
│ Object C                │
│ bbox + class + score    │
└─────────────────────────┘
```

Object detection shall remain a perception capability.

It shall not directly execute external actions.

The approved architectural direction is:

```text
Detection
   ↓
Perception Result
   ↓
Policy
   ↓
Tool
   ↓
Action
```

---

# 4. Capability Separation

Object detection shall remain distinct from:

- Grounding
- Segmentation
- Tracking
- OCR
- Visual reasoning

The following architectural distinction is mandatory:

```text
Detection
=
Find known object classes

Grounding
=
Find target described by language

Segmentation
=
Determine target pixels

Tracking
=
Maintain target identity over time
```

A single model may implement several capabilities, but JAS shall expose them through independent architectural interfaces.

---

# 5. Candidate Technologies

The initial benchmark candidate pool shall include:

- RT-DETR
- Grounding DINO
- SAM 3.1
- Other technologies satisfying Approved Stack governance requirements

The benchmark shall remain open to additional candidates when strong technical justification exists.

The newest or most popular model shall not receive automatic preference.

---

# 6. Primary Candidate: RT-DETR

RT-DETR shall be evaluated as a primary candidate for conventional object detection.

The expected strengths include:

- Real-time inference
- Standard object detection
- Strong COCO performance
- Efficient inference
- End-to-end detection architecture
- Production-oriented deployment

External benchmark numbers published by the project shall be treated as reference information only.

They shall not be considered JAS benchmark results.

---

# 7. Open-Vocabulary Detection Candidates

Technologies such as Grounding DINO and SAM-family models may provide capabilities extending beyond conventional fixed-class detection.

These technologies shall therefore be evaluated separately for:

- Open-vocabulary detection
- Text-conditioned detection
- Concept detection
- Referring-expression tasks

Their performance in these areas shall not automatically replace conventional object detection evaluation.

---

# 8. Benchmark Levels

The JAS Object Detection benchmark shall contain three primary levels.

```text
LEVEL 1
Standard Detection
```

```text
LEVEL 2
JAS Real-World Detection
```

```text
LEVEL 3
JAS Computer-Vision Detection
```

Each level evaluates a different aspect of the capability.

---

# 9. Level 1 — Standard Detection

The first benchmark level shall use established object-detection datasets.

The initial dataset shall be:

**COCO 2017 validation**

where model compatibility permits.

Additional datasets may include:

- LVIS
- Open Images
- model-specific benchmark datasets

The exact dataset revision and subset shall be frozen before benchmark execution.

---

# 10. Standard Detection Metrics

Primary quality metrics:

```text
mAP@50
mAP@50:95
Precision
Recall
F1
```

Performance metrics:

```text
P50 latency
P90 latency
P95 latency
P99 latency
FPS
```

Resource metrics:

```text
Peak VRAM
Average VRAM
CPU utilization
GPU utilization
```

---

# 11. mAP@50

The benchmark shall record:

```text
mAP@50
```

as a primary detection metric.

This measures average precision at an IoU threshold of 0.50.

---

# 12. mAP@50:95

The benchmark shall also record:

```text
mAP@50:95
```

This provides a stricter measure of localization quality by averaging across multiple IoU thresholds.

Both:

```text
mAP@50
```

and:

```text
mAP@50:95
```

shall be reported.

One shall not replace the other.

---

# 13. Level 2 — JAS Real-World Detection

JAS shall maintain a dedicated real-world detection evaluation set.

Initial category groups:

```text
PERSON
ANIMAL
VEHICLE
ELECTRONICS
FURNITURE
HOUSEHOLD
TOOLS
DOCUMENTS
FOOD
OTHER
```

Electronics may include:

```text
Laptop
Phone
Tablet
Monitor
Keyboard
Mouse
Headphones
Camera
Router
```

The final category list shall be frozen before benchmark execution.

---

# 14. Camera Detection

Real-world camera scenarios shall include:

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

The benchmark shall evaluate robustness under environmental variation.

---

# 15. Desktop Detection

Desktop screenshots shall receive a dedicated evaluation category.

Candidate targets include:

```text
Window
Button
Icon
Menu
Tab
Text Field
Checkbox
Radio Button
Slider
Dialog
Notification
```

However, generic object detection shall not automatically be considered a suitable UI detection system.

UI element detection shall remain a separate capability that may require specialized grounding, segmentation, or vision-language models.

---

# 16. Detection vs UI Detection

The following distinction is mandatory:

```text
GENERAL OBJECT DETECTION
        ↓
Person
Car
Laptop
Phone
Chair
```

versus:

```text
UI ELEMENT DETECTION
        ↓
Button
Tab
Checkbox
Menu
Dialog
Icon
```

A detector shall not receive UI approval merely because it performs well on COCO.

---

# 17. Level 3 — JAS Computer-Vision Detection

This level evaluates real JARVIS scenarios.

Examples:

```text
"Find the Chrome window."

"Find the laptop."

"Find the phone."

"Find the warning icon."

"Find the person holding the phone."
```

These tasks may require grounding rather than conventional detection.

The benchmark shall record whether a candidate is capable of performing the task directly or requires another capability.

---

# 18. Grounding Separation

If a task requires:

```text
IMAGE
+
NATURAL LANGUAGE
```

the task shall be classified as:

**Visual Grounding**

rather than conventional object detection.

Therefore:

```text
"Detect all phones."
```

is detection.

Whereas:

```text
"Find the phone next to the laptop."
```

is grounding.

---

# 19. Input Resolution

Primary benchmark resolution:

```text
640 × 640
```

shall be used for standardized detector comparison where supported.

Real-world benchmark resolutions shall additionally include:

```text
1920 × 1080
2560 × 1440
3840 × 2160
```

where practical.

The model's own preprocessing behavior shall be recorded.

---

# 20. Batch Size

The primary JAS interactive configuration shall be:

```text
Batch = 1
```

because most JARVIS perception tasks are expected to occur interactively.

Additional throughput tests may use:

```text
Batch = 4
Batch = 8
Batch = 16
```

where supported.

Batch throughput shall never replace batch-1 latency as the primary interactive metric.

---

# 21. Latency Benchmark

Each candidate shall undergo:

```text
Warm-up
↓
Measured Inference
```

Warm-up:

```text
20 inferences
```

Measured:

```text
200 inferences
```

or an equivalent statistically sufficient workload.

The benchmark shall record:

```text
Mean
P50
P90
P95
P99
```

---

# 22. Cold Start Benchmark

Cold-start behavior shall be measured separately.

The benchmark shall record:

```text
Process Start
↓
Runtime Initialization
↓
Model Loading
↓
First Inference
```

The resulting measurement shall be recorded as:

```text
Cold Start Time
```

Cold-start latency shall not be mixed with warm inference latency.

---

# 23. VRAM Benchmark

Memory shall be measured at:

```text
Before model loading
After model loading
Peak inference
Steady state
```

The benchmark shall report:

```text
Base VRAM
Model VRAM
Peak VRAM
```

---

# 24. Precision Benchmark

Where supported:

```text
FP32
FP16
BF16
INT8
```

may be evaluated.

Each precision mode shall be evaluated for:

```text
Accuracy
Latency
VRAM
Reliability
```

A faster precision mode shall not automatically become the approved configuration.

---

# 25. Warm vs Cold Execution

Benchmark reports shall maintain separate categories:

```text
Cold Start
Warm Inference
```

This distinction is important because JARVIS may use both:

```text
Long-running perception workers
```

and:

```text
On-demand perception workers
```

---

# 26. Small Object Detection

Small-object detection shall receive a dedicated benchmark.

Examples:

```text
Small Icons
Small Phones
Distant Persons
Small Vehicles
Status Indicators
Tiny UI Elements
```

The benchmark shall measure:

```text
Recall
Precision
mAP
Localization Accuracy
```

for small targets separately.

---

# 27. Occlusion Benchmark

Objects shall be evaluated under:

```text
Partial Occlusion
Heavy Occlusion
Object Overlap
Temporary Visibility
```

The benchmark shall record:

```text
Detection Recall
False Positive Rate
Localization Quality
```

---

# 28. Crowded Scene Benchmark

Special datasets shall include:

```text
Multiple Persons
Multiple Vehicles
Multiple Similar Objects
Overlapping Objects
```

The benchmark shall evaluate:

```text
Object Separation
Detection Recall
False Positives
Localization Accuracy
```

---

# 29. Hard Cases

The JAS dataset shall intentionally contain:

```text
Low Light
Motion Blur
Small Objects
Occlusion
Crowded Scenes
Reflections
Partial Objects
Unusual Angles
Compression Artifacts
Screen Glare
Low Resolution
High Resolution
```

These cases shall be analyzed separately from the standard benchmark.

---

# 30. Detection Threshold

Confidence thresholds shall be determined using validation data.

Threshold optimization shall not be performed on the final test set.

The benchmark shall prevent:

```text
Test Leakage
```

by freezing threshold configuration before final evaluation.

---

# 31. Dataset Split

The JAS benchmark dataset shall use:

```text
TRAIN
VALIDATION
TEST
```

where applicable.

The final evaluation shall use a held-out test set.

The test set shall remain isolated from model-selection decisions.

---

# 32. JAS Held-Out Test Set

The final JAS test set shall be created or frozen before final model selection.

The intended process is:

```text
Candidate Evaluation
        ↓
Model Selection
        ↓
Frozen Test Set
        ↓
Final Evaluation
```

This prevents benchmark overfitting.

---

# 33. Safety Benchmark

Detection shall also be evaluated for high-risk visual targets.

Examples:

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

The detector shall only provide perception information.

It shall not authorize an action.

---

# 34. Unsafe Target Selection

If a perception system identifies the wrong high-risk target, the result shall be classified as:

```text
UNSAFE TARGET SELECTION
```

The following metric shall be recorded:

```text
Unsafe Target Rate
=
Unsafe Target Selections
/
Total High-Risk Target Tasks
```

The desired value is:

```text
0
```

---

# 35. Confidence Calibration

Model confidence shall not automatically be interpreted as probability of correctness.

Calibration shall therefore be evaluated.

Metrics may include:

```text
Expected Calibration Error
Brier Score
Precision by Confidence Bucket
```

---

# 36. Reliability Benchmark

Each candidate shall undergo repeated inference testing.

The benchmark shall record:

```text
Successful Inferences
Failed Inferences
Timeouts
Crashes
Invalid Outputs
Malformed Outputs
Memory Errors
```

Primary reliability metric:

```text
Valid Successful Inferences
/
Total Inferences
```

---

# 37. Output Validation

Every detector result shall pass structural validation.

Required fields:

```text
Bounding Box
Class
Confidence
```

Validation shall ensure:

```text
Coordinates are valid
Confidence is valid
Class exists
No NaN
No Infinity
No malformed output
```

Invalid output shall count as an inference failure.

---

# 38. Recovery Benchmark

Candidates shall be tested under:

```text
Invalid Image
Unsupported Image Format
Oversized Image
Invalid Configuration
Memory Pressure
Timeout
Temporary Runtime Failure
```

The detector shall fail safely.

A detector failure shall not crash the JAS core.

---

# 39. Cross-Model Evaluation

Multiple candidate detectors may be evaluated against the same dataset.

All candidates shall use:

```text
Same Dataset
Same Evaluation Rules
Same Hardware
Same Measurement Methodology
```

whenever technically possible.

---

# 40. Performance Normalization

Performance numbers shall only be compared when the following are equivalent or explicitly documented:

```text
Hardware
Runtime
Precision
Input Resolution
Batch Size
Model Revision
Preprocessing
Postprocessing
```

Undocumented differences shall invalidate direct performance comparisons.

---

# 41. Detection Score

The initial scoring proposal is:

```text
Detection Quality       35%
Latency                 20%
Resource Efficiency     15%
Reliability             10%
JAS Compatibility       10%
Deployment Complexity    5%
Maintainability          5%
```

Total:

```text
100%
```

This weighting remains provisional until benchmark data is available.

---

# 42. Veto Criteria

Weighted scores shall not override critical failures.

The following are veto conditions:

```text
Critical Security Failure
Critical License Incompatibility
Unrecoverable Runtime Instability
Critical Unsafe Behavior
Unsupported Required Platform
```

A candidate receiving a veto cannot become PRIMARY.

---

# 43. License Evaluation

Every candidate shall be independently evaluated for:

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

License incompatibility shall prevent approval regardless of technical score.

---

# 44. Hardware Record

Every benchmark result shall include:

```text
GPU
VRAM
CPU
RAM
Operating System
GPU Driver
CUDA Version
Runtime Version
Model Precision
Input Resolution
Batch Size
```

This information is mandatory for reproducibility.

---

# 45. Reproducibility

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

# 46. Benchmark Result Format

Each candidate shall generate a normalized result.

Example:

```yaml
technology: RT-DETR

capabilities:
  standard_detection: PASS
  small_object_detection: PASS
  crowded_scene_detection: PASS
  ui_detection: N/A
  grounding: N/A

quality:
  map50: ...
  map5095: ...
  precision: ...
  recall: ...

performance:
  p50_ms: ...
  p95_ms: ...
  p99_ms: ...
  fps: ...

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

# 47. Decision Categories

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

A model may be:

```text
PRIMARY
```

for one capability while remaining:

```text
REJECTED
```

for another capability.

---

# 48. Architecture Abstraction

The detector shall be hidden behind a stable interface.

Conceptually:

```python
class Detector:

    def detect(
        self,
        image,
        *,
        confidence_threshold=None,
    ):
        ...
```

The implementation may be:

```text
RT-DETR
Grounding DINO
SAM 3.1
Future Model
```

without changing the higher-level architecture.

---

# 49. Capability Independence

The following interfaces shall remain independently replaceable:

```text
Detector
Grounder
Segmenter
Tracker
OCR
Vision Reasoner
```

A model implementing multiple capabilities shall expose those capabilities through separate interfaces.

This prevents vendor/model coupling from spreading through JAS.

---

# 50. Current Architecture Hypothesis

The initial architecture hypothesis is:

```text
                 VISION
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
   Detection     Grounding   Segmentation
       │            │            │
    RT-DETR     Specialist    SAM Family
```

This is an architectural hypothesis and not a final Version Lock decision.

---

# 51. Current Candidate Roles

Initial candidates:

```text
RT-DETR
    ↓
Primary conventional detection candidate

Grounding DINO
    ↓
Open-vocabulary / text-conditioned candidate

SAM 3.1
    ↓
Multi-capability vision candidate
```

Final roles shall be determined by benchmark evidence.

---

# 52. What Is Locked

The following benchmark rules are now established:

```text
✓ Detection is separate from grounding
✓ Detection is separate from segmentation
✓ Detection is separate from tracking
✓ Standard detection is benchmarked independently
✓ JAS real-world detection is benchmarked independently
✓ Computer-vision detection is benchmarked independently
✓ Batch=1 is the primary interactive configuration
✓ Cold and warm latency are separated
✓ P50/P95/P99 are recorded
✓ VRAM is measured
✓ Reliability is measured
✓ Small objects receive dedicated tests
✓ Occlusion receives dedicated tests
✓ Crowded scenes receive dedicated tests
✓ Safety is a veto criterion
✓ License is a veto criterion
✓ Test leakage is prohibited
✓ External benchmark numbers are not JAS results
✓ Exact model artifacts are not yet Version Locked
```

---

# 53. What Is Not Locked

The following remain open:

```text
✗ Final detector
✗ Exact model variant
✗ Exact model revision
✗ Runtime
✗ Precision
✗ Input resolution
✗ Hardware
✗ Minimum mAP
✗ Minimum FPS
✗ Maximum VRAM
✗ Final primary/fallback architecture
```

---

# 54. Benchmark Execution Flow

The official execution sequence shall be:

```text
Candidate
   ↓
Environment Validation
   ↓
Model Integrity Validation
   ↓
Standard Dataset
   ↓
JAS Dataset
   ↓
Hard Cases
   ↓
Small Objects
   ↓
Occlusion
   ↓
Crowded Scenes
   ↓
Desktop / UI Cases
   ↓
Latency
   ↓
VRAM
   ↓
Reliability
   ↓
Safety
   ↓
License
   ↓
Score
   ↓
Architecture Decision
```

---

# 55. Final Principle

The JAS object detection strategy shall not be:

```text
"Choose the most popular detector."
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

The benchmark exists to ensure that the selected technology is supported by measurable evidence and can be replaced without destabilizing the JAS architecture.

# End of Document