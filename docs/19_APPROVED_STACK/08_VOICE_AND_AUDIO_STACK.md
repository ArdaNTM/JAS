# 08 — VOICE AND AUDIO STACK

**Document ID:** JAS-AS-08  
**Document:** `08_VOICE_AND_AUDIO_STACK.md`  
**Project:** JARVIS / JAS  
**Specification Layer:** Approved Stack  
**Status:** APPROVED STACK SPECIFICATION  
**Version:** v1.0  
**Authority:** JAS v1  
**Depends On:** JAS v1, `00_APPROVED_STACK_OVERVIEW.md`, `01_STACK_GOVERNANCE_AND_SELECTION_POLICY.md`, `02_CORE_RUNTIME_AND_PROGRAMMING_LANGUAGES.md`, `03_AI_AND_LLM_FRAMEWORKS.md`  
**Related Documents:** `09_COMPUTER_VISION_STACK.md`, `11_BACKEND_STACK.md`, `14_SECURITY_STACK.md`, `16_MONITORING_AND_OBSERVABILITY_STACK.md`, `17_TESTING_AND_QUALITY_ASSURANCE_STACK.md`, `18_BUILD_TOOLCHAIN_AND_PACKAGE_MANAGEMENT.md`, `19_APPROVED_MODELS.md`  
**Feeds Into:** Version Lock, Manifest, Bootstrap, Compliance Checker, Voice Runtime, Voice Agent, Audio Infrastructure

---

# 1. PURPOSE

This document defines the voice and audio architecture for JARVIS.

The objective is not simply to add:

```text
Speech-to-Text
+
Text-to-Speech
```

to the system.

JARVIS requires a complete real-time voice subsystem capable of:

- microphone input,
- audio capture,
- device management,
- audio preprocessing,
- voice activity detection,
- speech segmentation,
- wake-word detection,
- speech-to-text,
- language detection,
- intent handoff,
- streaming inference,
- text-to-speech,
- audio playback,
- interruption,
- barge-in,
- conversational turn management,
- echo handling,
- noise handling,
- low-latency response,
- local inference,
- optional cloud fallback,
- voice model management,
- privacy protection,
- observability,
- testing,
- security enforcement.

The voice subsystem SHALL therefore be treated as a **first-class JARVIS platform capability**.

---

# 2. ARCHITECTURAL OBJECTIVE

The long-term objective is a natural conversational interface.

Conceptually:

```text
                    USER
                      │
                      ▼
                Microphone
                      │
                      ▼
                Audio Capture
                      │
                      ▼
             Audio Preprocessing
                      │
                      ▼
                  VAD
                      │
                      ▼
              Wake / Session
                      │
                      ▼
                   STT
                      │
                      ▼
              Intent / Context
                      │
                      ▼
            Agent Orchestrator
                      │
                      ▼
                   LLM
                      │
                      ▼
                 Response
                      │
                      ▼
                   TTS
                      │
                      ▼
              Audio Playback
                      │
                      ▼
                    USER
```

For real-time conversation, the architecture additionally supports:

```text
User Speech
     │
     ├──────────────► VAD
     │
     ├──────────────► Audio Stream
     │
     └──────────────► Interrupt Detection

JARVIS Speech
     │
     ├──────────────► Playback
     │
     └──────────────► Echo Reference
```

---

# 3. CORE DESIGN PRINCIPLES

## 3.1 Voice Is an Interface, Not the Core Intelligence

The voice layer does not contain JARVIS reasoning.

The architecture remains:

```text
Voice
 ↓
Input Representation
 ↓
JARVIS Core
 ↓
Agent / LLM
 ↓
Output Representation
 ↓
Voice
```

This means JARVIS must remain fully functional without voice.

---

## 3.2 Voice Must Be Streaming-Capable

The architecture SHALL support streaming at every practical stage:

```text
Microphone
 ↓
Audio Chunks
 ↓
VAD
 ↓
Streaming STT
 ↓
Incremental Text
 ↓
LLM Streaming
 ↓
Incremental Text
 ↓
Streaming TTS
 ↓
Audio Chunks
 ↓
Playback
```

The objective is to avoid:

```text
Speak
 ↓
Wait
 ↓
Full STT
 ↓
Wait
 ↓
Full LLM
 ↓
Wait
 ↓
Full TTS
 ↓
Play
```

where possible.

---

# 4. TARGET USER EXPERIENCE

The desired long-term experience is:

```text
User:
"JARVIS, search for the cheapest flight to Istanbul."

JARVIS:
"Of course."

[while the user continues speaking or after the command,
the system processes the request]

JARVIS:
"I found..."
```

The exact conversational behavior will be controlled by the core interaction architecture.

The voice layer must make this possible without imposing unnecessary latency.

---

# 5. LATENCY MODEL

Voice quality is strongly influenced by end-to-end latency.

The system therefore treats latency as a first-class engineering metric.

Conceptually:

```text
T_total =
    T_capture
  + T_VAD
  + T_STT
  + T_reasoning
  + T_TTS
  + T_playback
```

The system should optimize both:

### Time to first response

```text
User stops speaking
        ↓
First audible JARVIS response
```

and:

### Time to completion

```text
User stops speaking
        ↓
Full response completed
```

---

# 6. PRIMARY ARCHITECTURAL COMPONENTS

The voice subsystem consists of:

```text
Audio Device Layer
Audio Capture Layer
Audio Processing Layer
VAD Layer
Wake Word Layer
Speech Segmentation Layer
STT Layer
Language Layer
Conversation Turn Layer
Voice Generation Layer
TTS Layer
Audio Playback Layer
Interruption Layer
Voice Session Layer
Security Layer
Observability Layer
```

---

# 7. AUDIO DEVICE LAYER

The audio device layer manages:

- microphones,
- speakers,
- headsets,
- USB audio interfaces,
- Bluetooth devices,
- virtual audio devices,
- default devices,
- device switching.

It must support:

```text
Enumerate
Select
Open
Configure
Monitor
Recover
Close
```

---

# 8. DEVICE ABSTRACTION

JARVIS SHALL NOT hard-code one microphone or one speaker.

The architecture should expose:

```text
AudioInputDevice
AudioOutputDevice
AudioDeviceManager
```

Conceptually:

```text
Audio Device Manager
├── Input Devices
│   ├── Microphone A
│   ├── Microphone B
│   └── Headset Mic
│
└── Output Devices
    ├── Speakers
    ├── Headphones
    └── Bluetooth
```

---

# 9. AUDIO FORMAT

The voice subsystem should normalize internal audio representation.

The internal representation should support at minimum:

```text
PCM
Mono
16-bit or floating point representation
Configurable sample rate
```

The precise canonical format will be finalized during implementation and benchmark testing.

16 kHz is a particularly important target for speech-processing pipelines because common VAD/STT components support it.

Silero VAD, for example, supports 8 kHz and 16 kHz sampling rates. citeturn1search0

---

# 10. AUDIO CAPTURE

The capture layer must support:

```text
Continuous Capture
Push / Callback Mode
Chunked Streaming
Device Selection
Sample Rate Configuration
Channel Configuration
Buffer Management
Overflow Detection
Device Disconnect Detection
```

The capture layer must not block the entire JARVIS runtime.

---

# 11. AUDIO BUFFERING

The architecture should use bounded buffers.

Conceptually:

```text
Microphone
    ↓
Input Buffer
    ↓
Audio Processing Queue
    ↓
VAD
    ↓
Speech Buffer
```

Buffers must have:

- maximum size,
- overflow policy,
- underflow handling,
- backpressure,
- timestamps.

---

# 12. AUDIO TIMESTAMPS

Audio chunks should carry timing metadata.

Example:

```yaml
audio_chunk:
  session_id: ...
  sequence: 1042
  timestamp: ...
  duration_ms: ...
  sample_rate: 16000
  channels: 1
```

This is important for:

- streaming,
- synchronization,
- interruption,
- debugging,
- latency measurement.

---

# 13. AUDIO PREPROCESSING

The audio preprocessing layer may include:

```text
Resampling
Channel Mixing
Gain Normalization
Noise Suppression
High-pass Filtering
Echo Cancellation
Automatic Gain Control
Clipping Detection
```

However, preprocessing must not be blindly enabled.

Every processing stage may affect speech recognition quality.

---

# 14. NOISE SUPPRESSION

Noise suppression should be configurable.

Possible environments include:

```text
Quiet Room
Office
Street
Keyboard Noise
Fan Noise
Music
TV
Multiple Speakers
```

The system should support adaptive profiles.

---

# 15. ECHO CANCELLATION

Echo cancellation is important because JARVIS itself produces audio.

The architecture should support:

```text
Microphone Input
+
JARVIS Playback Reference
        ↓
Echo Cancellation
        ↓
Clean User Speech
```

This is particularly important for:

- speakers,
- laptops,
- smart displays,
- room-based JARVIS installations.

---

# 16. VOICE ACTIVITY DETECTION

VAD determines whether speech is present.

The conceptual pipeline is:

```text
Audio
 ↓
VAD
 ↓
Speech / Non-Speech
```

VAD is separate from STT.

This distinction is important because JARVIS must not continuously send silence and environmental audio to the STT system.

---

# 17. PRIMARY VAD TECHNOLOGY

**Selected Technology: Silero VAD**

Status:

```text
APPROVED
```

Silero VAD is selected as the primary VAD candidate because it is designed specifically for voice activity detection, supports CPU-oriented deployment, supports ONNX Runtime, and is distributed under the MIT license. The project also explicitly states that it has no built-in telemetry, keys, registration or vendor lock. citeturn1search0turn1search1

---

# 18. SILERO VAD ROLE

Silero VAD SHALL primarily provide:

```text
Speech Detection
Speech Start Detection
Speech End Detection
Speech Segmentation Support
```

It SHALL NOT be responsible for:

```text
Wake Word Recognition
Speech Transcription
Speaker Identity
Intent Recognition
Conversation Reasoning
```

---

# 19. VAD FALLBACK

A simpler VAD implementation may exist as a fallback for constrained environments.

WebRTC VAD remains a possible secondary option.

The Python WebRTC VAD interface supports speech classification for 10, 20 or 30 ms frames at common speech sample rates and has a lightweight implementation. citeturn3search0

Status:

```text
CONDITIONALLY APPROVED / FALLBACK
```

Reason:

```text
Low computational cost
+
Mature implementation
+
Useful fallback
```

but Silero VAD is preferred for JARVIS's primary speech-detection path.

---

# 20. VAD COMPARISON

| Criterion | Silero VAD | WebRTC VAD |
|---|---:|---:|
| Speech Detection | Excellent | Good |
| CPU Efficiency | Excellent | Excellent |
| Modern ML | Yes | No |
| ONNX Support | Yes | N/A |
| Portability | Excellent | Excellent |
| Low Latency | Excellent | Excellent |
| Noise Robustness | Strong | Good |
| License | MIT | BSD-derived components |
| JARVIS Fit | **Excellent** | Good |
| Primary | **Yes** | No |

---

# 21. SPEECH SEGMENTATION

VAD output should be converted into meaningful speech segments.

Conceptually:

```text
Silence
   ↓
Speech Start
   ↓
Speech
   ↓
Short Pause
   ↓
Speech
   ↓
Speech End
```

The system must distinguish:

```text
Pause
```

from:

```text
End of Turn
```

This is critical for natural conversation.

---

# 22. END-OF-TURN DETECTION

End-of-turn detection should combine:

```text
VAD
+
Silence Duration
+
Speech Content
+
Conversation State
+
Optional LLM Prediction
```

Example:

```text
"JARVIS, can you search for..."

[short pause]

"...the cheapest flight?"
```

The system should not prematurely submit the incomplete utterance.

---

# 23. WAKE WORD

The long-term JARVIS interface should support wake-word activation.

Conceptually:

```text
Always-listening low-power detector
             ↓
        "JARVIS"
             ↓
        Voice Session
             ↓
              STT
```

The wake-word subsystem should remain separate from general STT.

---

# 24. WAKE-WORD SECURITY

Wake-word detection should not be treated as authentication.

A detected wake word means:

```text
"Start listening"
```

not:

```text
"This person is authorized."
```

Identity and authorization remain separate security concepts.

---

# 25. WAKE-WORD TECHNOLOGY

No permanent v1 wake-word engine is frozen by this document.

Candidates may include:

```text
OpenWakeWord
Porcupine
Custom Wake-Word Model
Platform-native wake-word APIs
```

Selection requires separate evaluation based on:

```text
Accuracy
False Activation Rate
False Rejection Rate
Latency
CPU
Privacy
License
Offline Operation
Custom Wake Word Support
Windows Compatibility
Linux Compatibility
```

Status:

```text
WAKE-WORD ENGINE:
DEFERRED TO TECHNOLOGY EVALUATION
```

This prevents premature locking.

---

# 26. SPEAKER IDENTIFICATION

Speaker recognition is optional.

It may eventually support:

```text
Who is speaking?
```

but it must not be required for basic JARVIS functionality.

Possible future capabilities:

```text
Speaker Verification
Speaker Identification
Voice Profiles
Multi-user Sessions
```

These require additional privacy and biometric-data considerations.

---

# 27. SPEAKER AUTHENTICATION

Voice identity SHALL NOT be the sole authorization mechanism for sensitive actions.

For example:

```text
"JARVIS, transfer money."
```

must not become authorized solely because the voice matches a stored speaker profile.

High-risk operations require stronger authorization.

---

# 28. SPEECH-TO-TEXT

STT transforms:

```text
Audio
 ↓
Text
```

The STT subsystem must support:

```text
Streaming
Language Detection
Multilingual Input
Timestamps
Confidence Information
Local Inference
GPU Acceleration
CPU Fallback
```

---

# 29. PRIMARY STT TECHNOLOGY

**Selected Technology: faster-whisper**

Status:

```text
APPROVED
```

`faster-whisper` is a Whisper implementation using CTranslate2. Its project reports substantially faster inference and lower memory use than the original implementation in its benchmark configurations, with optional 8-bit quantization on CPU/GPU. It is MIT licensed. citeturn0search0

---

# 30. WHY FASTER-WHISPER

It is selected because it offers a strong combination of:

```text
Whisper-quality model family
+
Efficient inference
+
CPU support
+
GPU support
+
Quantization
+
Python integration
+
Local execution
+
Multilingual capability
```

This makes it a strong fit for JARVIS's Python-centered core architecture.

---

# 31. STT FALLBACK — WHISPER.CPP

**Technology:** whisper.cpp

Status:

```text
APPROVED AS SECONDARY / FALLBACK
```

whisper.cpp provides a C/C++ implementation of Whisper with CPU-only inference, multiple GPU backends, quantization, Windows/Linux support and other platform targets. Its repository is MIT licensed. citeturn0search3turn1search4

It is particularly valuable for:

```text
Embedded Deployment
Low-Level Integration
CPU-First Deployment
Native Runtime
Portable Builds
Resource-Constrained Environments
```

---

# 32. OPENAI WHISPER

**Technology:** OpenAI Whisper

Status:

```text
APPROVED AS REFERENCE / ALTERNATIVE
```

OpenAI's original Whisper implementation and model weights are released under MIT according to its repository. citeturn1search3turn1search9

It remains useful as:

```text
Reference Implementation
Evaluation Baseline
Compatibility Target
Research Tool
```

but faster-whisper is preferred as the primary production inference implementation.

---

# 33. STT COMPARISON

| Criterion | faster-whisper | whisper.cpp | OpenAI Whisper |
|---|---:|---:|---:|
| Whisper Compatibility | Excellent | Excellent | Reference |
| CPU | Excellent | Excellent | Good |
| GPU | Excellent | Excellent | Good |
| Quantization | Excellent | Excellent | Limited / ecosystem-dependent |
| Python Integration | Excellent | Good | Excellent |
| Native Integration | Good | Excellent | Limited |
| Windows | Excellent | Excellent | Good |
| Linux | Excellent | Excellent | Excellent |
| Memory Efficiency | Excellent | Excellent | Good |
| JARVIS Fit | **Excellent** | Excellent | Good |
| Primary | **Yes** | Fallback | Reference |

---

# 34. STT MODEL POLICY

This document approves the STT engine family.

It does not permanently select one model size.

Model selection belongs in:

```text
19_APPROVED_MODELS.md
```

Potential model classes include:

```text
Small
Medium
Large
Distilled
Quantized
Language-specific
```

The exact model must be selected according to:

```text
WER
Latency
VRAM
RAM
Language Coverage
Noise Robustness
CPU Performance
GPU Performance
```

---

# 35. MULTILINGUAL REQUIREMENT

JARVIS should support multilingual speech.

Initial priority languages may include:

```text
English
German
Turkish
```

Additional languages can be added later.

The architecture must not assume English-only processing.

---

# 36. LANGUAGE DETECTION

Language detection may occur:

```text
Before STT
```

or:

```text
Within STT
```

depending on the selected model.

The system should avoid unnecessary separate language-detection passes when the STT model can perform reliable language identification itself.

---

# 37. TRANSCRIPTION METADATA

STT output should not be plain text only.

Conceptually:

```yaml
transcription:
  text: "..."
  language: "de"
  confidence: 0.94
  start_time: ...
  end_time: ...
  segments:
    - ...
```

This metadata supports:

- debugging,
- turn detection,
- confidence thresholds,
- multilingual behavior,
- observability.

---

# 38. LOW-CONFIDENCE STT

If transcription confidence is insufficient, JARVIS should be able to:

```text
Ask for repetition
Request clarification
Use contextual correction
Use alternative STT configuration
```

Example:

```text
"I didn't catch that. Could you repeat it?"
```

The system should not confidently execute a high-risk action from low-confidence speech.

---

# 39. STT + LLM CORRECTION

LLM-based correction may be used carefully.

Pipeline:

```text
Raw STT
 ↓
Confidence / Context
 ↓
Optional Normalization
 ↓
Intent Understanding
```

The system must preserve the original transcript.

The corrected interpretation should not silently replace source audio/transcription evidence.

---

# 40. TTS

TTS transforms:

```text
Text
 ↓
Speech
```

The JARVIS TTS system must support:

```text
Natural Speech
Streaming
Low Latency
Voice Selection
Pitch / Prosody Controls
Volume
Speed
Multilingual Output
Local Inference
```

where supported.

---

# 41. TTS TECHNOLOGY EVALUATION

The current major candidates include:

```text
Kokoro
Chatterbox
Piper
Coqui TTS
Cloud TTS providers
```

The project must evaluate:

```text
Quality
Latency
Streaming
Voice Naturalness
Multilingual Coverage
Voice Consistency
Voice Cloning
License
Model License
CPU
GPU
Memory
Windows
Linux
Offline Capability
```

---

# 42. PRIMARY TTS CANDIDATE — KOKORO

**Technology:** Kokoro

Status:

```text
APPROVED CANDIDATE
```

Kokoro-82M is an open-weight TTS model whose Hugging Face model card identifies the weights as Apache 2.0 licensed. The model is relatively small at 82M parameters and is designed for efficient inference. citeturn2search1turn2search5

The Kokoro inference library is also available for Python and is designed around the Kokoro model. citeturn2search6

Kokoro is therefore a strong candidate for the local JARVIS voice.

---

# 43. KOKORO STRENGTHS

Advantages include:

```text
Small model size
+
Local inference
+
Apache 2.0 model license
+
Low resource requirement relative to larger TTS systems
+
Python integration
+
Multiple voice options
+
Potentially suitable for low-latency generation
```

The exact production voice must still undergo subjective and objective evaluation.

---

# 44. CHATTERBOX

**Technology:** Chatterbox

Status:

```text
EXPERIMENTAL / EVALUATION
```

Chatterbox is an open-source TTS family from Resemble AI. Its repository currently describes a multilingual V3 model with a 0.5B model size and improved speaker similarity and conversational speech. The repository code is MIT licensed. citeturn2search2turn2search3

Chatterbox is particularly interesting for:

```text
Expressiveness
Voice Similarity
Multilingual Speech
Voice Cloning
Conversational Output
```

However, its higher resource requirements and model-specific considerations mean it should remain under evaluation rather than automatically becoming the default JARVIS voice.

---

# 45. PIPER

**Technology:** Piper

Status:

```text
NOT APPROVED FOR DEFAULT JARVIS CORE
```

This requires an important distinction.

The original `rhasspy/piper` repository is archived and its development moved to `OHF-Voice/piper1-gpl`. citeturn0search8turn1search6

The current Piper codebase is GPL-3.0-or-later. citeturn1search8turn1search6

Furthermore, Piper's voice models have individual model-card licensing considerations; the project explicitly warns that voice licenses must be reviewed individually. citeturn1search5

Because JARVIS is intended to remain a long-lived platform with future distribution flexibility, GPL and model-level licensing complexity make Piper unsuitable as the default core TTS dependency at this stage.

Piper may remain available as:

```text
Optional Local TTS
Experimental
User-selected Deployment
```

subject to license compliance.

---

# 46. COQUI TTS

**Technology:** Coqui TTS

Status:

```text
EXPERIMENTAL / LEGACY REFERENCE
```

Coqui TTS is a mature research and production-oriented TTS toolkit, but the repository's latest listed release is from 2023. Its repository is MPL-2.0 licensed. citeturn2search13

It remains useful for:

```text
Research
Model Evaluation
Voice Experimentation
Legacy Compatibility
```

but its project activity and ecosystem position make it unsuitable for the default JARVIS TTS stack without further evaluation.

---

# 47. TTS COMPARISON

| Criterion | Kokoro | Chatterbox | Piper | Coqui TTS |
|---|---:|---:|---:|---:|
| Local | Excellent | Excellent | Excellent | Excellent |
| Model Size | Excellent | Moderate | Excellent | Variable |
| Naturalness | Excellent | Excellent | Good | Variable |
| Expressiveness | Good | Excellent | Moderate | Good |
| Multilingual | Good / evolving | Excellent | Excellent | Excellent |
| Voice Cloning | Limited / model-dependent | Strong | Model-dependent | Strong |
| License Simplicity | Excellent candidate | Requires review | **Complex** | Moderate |
| Project Activity | Active | Active | Active fork | Legacy |
| CPU Suitability | Good | Moderate | Excellent | Variable |
| JARVIS Fit | **Excellent candidate** | Excellent experimental | Conditional | Experimental |

---

# 48. FINAL TTS DECISION

At Approved Stack level:

```text
Primary TTS Candidate:
Kokoro

Status:
APPROVED CANDIDATE
```

```text
Secondary / Advanced:
Chatterbox

Status:
EXPERIMENTAL
```

```text
Optional:
Piper

Status:
CONDITIONALLY AVAILABLE / NOT DEFAULT
```

```text
Legacy / Research:
Coqui TTS

Status:
EXPERIMENTAL
```

The final production voice model will be selected in:

```text
19_APPROVED_MODELS.md
```

---

# 49. VOICE MODEL LICENSING

Voice model licensing SHALL be evaluated separately from engine licensing.

This distinction is mandatory.

For example:

```text
TTS Engine License
        ≠
Voice Model License
        ≠
Training Dataset License
        ≠
Generated Voice Rights
```

A permissively licensed TTS engine does not automatically make every voice model legally interchangeable.

---

# 50. VOICE IDENTITY

JARVIS should have a consistent default voice identity.

The architecture should allow:

```text
Voice ID
Voice Model
Language
Speaker
Style
Pitch
Speed
Emotion
```

to be configured independently.

---

# 51. VOICE PERSONALITY

Voice personality belongs to the presentation layer, not the reasoning layer.

The system should support:

```text
Calm
Professional
Concise
Conversational
Expressive
```

without modifying the underlying agent architecture.

---

# 52. PROSODY

TTS should eventually support:

```text
Speed
Pitch
Volume
Pauses
Emphasis
Intonation
Emotion
```

where the selected model supports these features.

The JARVIS response planner may eventually produce prosody metadata.

Example:

```yaml
speech:
  text: "The download is complete."
  style: professional
  emphasis:
    - "complete"
```

This is conceptual and not a final API.

---

# 53. STREAMING TTS

TTS should support incremental generation when technically possible.

Desired flow:

```text
LLM
 ↓
Sentence / Phrase
 ↓
TTS Chunk
 ↓
Audio Buffer
 ↓
Playback
```

rather than waiting for the entire response.

---

# 54. SENTENCE-LEVEL TTS BUFFERING

A practical first implementation may use:

```text
LLM Token Stream
 ↓
Text Buffer
 ↓
Sentence Boundary
 ↓
TTS
 ↓
Audio Chunk
```

This can significantly reduce perceived latency.

---

# 55. AUDIO PLAYBACK

Playback must support:

```text
Start
Pause
Resume
Stop
Flush
Volume
Device Selection
Queue
Interrupt
```

The playback system must support immediate interruption.

---

# 56. BARGE-IN

Barge-in is a mandatory long-term feature.

Example:

```text
JARVIS:
"The weather tomorrow will be..."

User:
"JARVIS, stop."

          ↓

Playback stops immediately
          ↓
Microphone becomes active
          ↓
New user turn
```

Barge-in requires simultaneous:

```text
Playback
+
Microphone Monitoring
+
VAD
```

---

# 57. INTERRUPTION MODEL

The system must support at least:

```text
USER_INTERRUPT
SYSTEM_INTERRUPT
TASK_CANCEL
VOICE_STOP
NEW_HIGH_PRIORITY_INPUT
```

These events should be handled by the interaction/session layer.

---

# 58. AUDIO DUCKING

When JARVIS needs to listen while speaking, the system may reduce playback volume.

Conceptually:

```text
JARVIS speaking
      ↓
User speech detected
      ↓
Lower playback volume
      ↓
Listen
```

This is especially useful for full-duplex interactions.

---

# 59. FULL-DUPLEX FUTURE

The long-term architecture should support:

```text
User speaks
+
JARVIS speaks
+
Both streams active
```

simultaneously.

This requires:

```text
Echo Cancellation
VAD
Speaker Diarization
Barge-in
Audio Mixing
Turn Management
```

Full-duplex conversation should therefore be treated as a later maturity level rather than a prerequisite for the first voice implementation.

---

# 60. VOICE SESSION

A voice session should contain state such as:

```yaml
voice_session:
  session_id: ...
  user_id: ...
  input_device: ...
  output_device: ...
  language: ...
  wake_state: ...
  listening: true
  speaking: false
  turn_id: ...
```

The exact schema will be defined during core implementation.

---

# 61. SESSION STATES

The voice runtime should support states such as:

```text
IDLE
LISTENING_FOR_WAKE
WAKE_DETECTED
LISTENING
PROCESSING
SPEAKING
INTERRUPTED
WAITING
ERROR
STOPPED
```

State transitions must be deterministic.

---

# 62. STATE MACHINE

Conceptually:

```text
                 ┌─────────────┐
                 │    IDLE     │
                 └──────┬──────┘
                        │
                        ▼
             ┌────────────────────┐
             │ LISTEN_FOR_WAKE    │
             └─────────┬──────────┘
                       │ Wake
                       ▼
                ┌─────────────┐
                │  LISTENING  │
                └──────┬──────┘
                       │ End Turn
                       ▼
                ┌─────────────┐
                │ PROCESSING  │
                └──────┬──────┘
                       │ Response
                       ▼
                ┌─────────────┐
                │  SPEAKING   │
                └──────┬──────┘
                       │
             ┌─────────┴─────────┐
             ▼                   ▼
        Completed            Interrupted
             │                   │
             ▼                   ▼
           IDLE               LISTENING
```

---

# 63. VOICE + AGENT INTEGRATION

The voice system should expose normalized input to the agent layer.

Correct:

```text
Microphone
 ↓
Voice Runtime
 ↓
Transcript
 ↓
JARVIS Input Interface
 ↓
Intent / Agent
```

Not:

```text
Microphone
 ↓
LLM
```

---

# 64. VOICE + MEMORY

Voice itself should not automatically create permanent memory.

The pipeline is:

```text
Voice
 ↓
Transcript
 ↓
Conversation
 ↓
Memory Policy
 ↓
Optional Memory
```

This prevents every spoken sentence from becoming permanent memory.

---

# 65. VOICE PRIVACY

Microphone access is a sensitive capability.

The system must make it clear when:

```text
Microphone is active
```

and when:

```text
Microphone is inactive
```

The UI should provide an explicit status indicator.

---

# 66. ALWAYS-ON LISTENING

If an always-on mode is implemented, it must be explicitly configurable.

Possible modes:

```text
OFF
WAKE-WORD ONLY
SESSION LISTENING
CONTINUOUS
```

Default behavior should prioritize privacy.

---

# 67. LOCAL-FIRST AUDIO POLICY

The preferred architecture is:

```text
Audio
 ↓
Local VAD
 ↓
Local STT
 ↓
JARVIS
 ↓
Local TTS
```

when local hardware can support it.

Cloud services may be used as optional fallbacks.

---

# 68. CLOUD FALLBACK

A future cloud fallback may exist:

```text
Local STT
   ↓
Failure / Quality Threshold
   ↓
Approved Cloud STT
```

and:

```text
Local TTS
   ↓
Failure / Quality Threshold
   ↓
Approved Cloud TTS
```

Cloud providers must be separately approved through:

```text
03_AI_AND_LLM_FRAMEWORKS.md
19_APPROVED_MODELS.md
23_LICENSE_AND_COMPLIANCE.md
```

where applicable.

---

# 69. CLOUD PRIVACY POLICY

Before sending audio to an external provider, the system should know:

```text
Provider
Data Sent
Retention Policy
Training Policy
Region
Encryption
Cost
Latency
```

Cloud audio transmission must be policy-controlled.

---

# 70. AUDIO DATA RETENTION

Raw microphone audio should not be permanently stored by default.

Default:

```text
Capture
 ↓
Process
 ↓
Discard
```

unless:

```text
User explicitly requests recording
```

or:

```text
System requires temporary artifact
```

---

# 71. TRANSCRIPT RETENTION

Transcripts follow the memory/privacy policy.

Possible classifications:

```text
Ephemeral
Session
Temporary
Memory Candidate
Permanent Memory
```

The voice layer must not decide retention independently.

---

# 72. RECORDING MODE

A future explicit recording mode may support:

```text
Start Recording
Stop Recording
Save
Transcribe
Summarize
Delete
```

Recording must provide clear user indication.

---

# 73. AUDIO SECURITY

Audio data should be considered sensitive.

Controls should include:

```text
Access Control
Encryption
Secure Temporary Storage
Deletion
Redaction
Audit
```

---

# 74. DEVICE PERMISSIONS

The operating system's microphone permissions must be respected.

JARVIS should detect:

```text
Permission Granted
Permission Denied
Device Missing
Device Busy
Device Disconnected
```

and produce actionable diagnostics.

---

# 75. AUDIO ERROR MODEL

Standard error classes should include:

```text
AUDIO_DEVICE_NOT_FOUND
AUDIO_PERMISSION_DENIED
AUDIO_DEVICE_BUSY
AUDIO_CAPTURE_FAILURE
AUDIO_BUFFER_OVERFLOW
AUDIO_FORMAT_ERROR
AUDIO_SAMPLE_RATE_ERROR
VAD_FAILURE
STT_FAILURE
TTS_FAILURE
PLAYBACK_FAILURE
AUDIO_OUTPUT_NOT_FOUND
ECHO_PROCESSING_FAILURE
VOICE_SESSION_FAILURE
```

---

# 76. RECOVERY

Example:

```text
Microphone disconnected
        ↓
Detect
        ↓
Re-enumerate devices
        ↓
Find replacement
        ↓
Reinitialize
        ↓
Resume if safe
```

The system should not crash the entire JARVIS runtime because a microphone was unplugged.

---

# 77. CPU/GPU RESOURCE MANAGEMENT

Voice workloads must cooperate with the main AI runtime.

Possible resource competition:

```text
LLM
+
Vision
+
STT
+
TTS
```

all using GPU resources simultaneously.

The architecture therefore requires resource-aware scheduling.

---

# 78. GPU PRIORITY

The voice subsystem should support configurable GPU policies.

Example:

```text
Interactive Voice:
    High priority

Background Transcription:
    Low priority
```

This prevents background audio processing from degrading conversational responsiveness.

---

# 79. QUANTIZATION

STT and TTS models may use:

```text
FP32
FP16
INT8
Other supported quantization
```

depending on model/runtime.

Quantization decisions belong in:

```text
19_APPROVED_MODELS.md
```

and:

```text
Version Lock
```

rather than being hard-coded into this architecture document.

---

# 80. CPU FALLBACK

Every critical voice component should have a CPU-capable deployment path where practical.

This provides:

```text
GPU unavailable
      ↓
CPU fallback
      ↓
Reduced performance
      ↓
JARVIS remains operational
```

rather than:

```text
No GPU
 ↓
Voice unavailable
```

---

# 81. WINDOWS

Windows is a first-class JARVIS development target.

Voice stack validation must include:

```text
Microphone Enumeration
Default Device
USB Devices
Bluetooth
Headphones
Playback
Capture
Permissions
STT
TTS
Device Switching
```

---

# 82. LINUX

Linux is required for:

```text
Server
Container
CI
Production
```

Audio support must be tested against the selected Linux audio stack.

The exact system-level audio backend belongs to implementation/bootstrap decisions.

---

# 83. MACOS

macOS support should be possible where practical.

It is not a primary JARVIS deployment target unless later architecture decisions change.

---

# 84. CONTAINERIZATION

Voice capture is primarily a host capability.

Therefore:

```text
Host
 ↓
Audio Device
 ↓
Voice Capture Service
 ↓
Containerized AI Services
```

may be preferable to attempting to place every audio component inside a container.

Server-side TTS/STT workers may nevertheless run in containers.

---

# 85. SERVICE SEPARATION

The long-term architecture may separate:

```text
Voice Capture Service
Voice Processing Service
STT Worker
TTS Worker
Audio Playback Service
```

but these should not become microservices prematurely.

The initial implementation should use logical module boundaries first.

Physical service separation should occur only when justified by:

```text
Scale
Resource Isolation
Deployment
Reliability
Security
```

---

# 86. AUDIO PIPELINE

The canonical pipeline is:

```text
MICROPHONE
   ↓
AUDIO CAPTURE
   ↓
PREPROCESSING
   ↓
VAD
   ↓
WAKE / SESSION CONTROL
   ↓
SPEECH SEGMENT
   ↓
STT
   ↓
TRANSCRIPT
   ↓
JARVIS CORE
   ↓
RESPONSE STREAM
   ↓
TTS
   ↓
AUDIO BUFFER
   ↓
PLAYBACK
```

---

# 87. INTERRUPT PIPELINE

When the user interrupts JARVIS:

```text
Microphone
   ↓
VAD
   ↓
Speech Detected
   ↓
Interrupt Controller
   ↓
Stop / Duck TTS
   ↓
Flush Playback Buffer
   ↓
Capture User Speech
   ↓
New Turn
```

This must happen with low latency.

---

# 88. VOICE PRIORITY MODEL

Voice interaction should support priority levels:

```text
BACKGROUND
NORMAL
INTERACTIVE
URGENT
SYSTEM
```

For example:

```text
Background transcription
    ↓
Low priority

User actively speaking
    ↓
High priority

Safety-critical system alert
    ↓
Highest priority
```

---

# 89. OBSERVABILITY

The voice system must integrate with JARVIS observability.

Metrics should include:

```text
audio_capture_latency
vad_latency
stt_latency
tts_latency
time_to_first_audio
time_to_first_token
time_to_first_speech
voice_turn_duration
interruption_count
false_wake_count
stt_failure_count
tts_failure_count
audio_device_errors
```

---

# 90. VOICE QUALITY METRICS

The project should evaluate:

### STT

```text
WER
CER
Latency
Real-Time Factor
Language Accuracy
Noise Robustness
```

### TTS

```text
MOS
Naturalness
Pronunciation
Latency
RTF
Voice Consistency
Intelligibility
```

### VAD

```text
False Positive Rate
False Negative Rate
Speech Onset Latency
Speech Offset Latency
Noise Robustness
```

---

# 91. REAL-TIME FACTOR

Voice inference should track:

```text
RTF = Processing Time / Audio Duration
```

For interactive systems, the target is:

```text
RTF < 1
```

where feasible.

Lower is better.

---

# 92. TESTING

Voice testing must include:

```text
Unit Tests
Integration Tests
Audio Pipeline Tests
Device Tests
STT Tests
TTS Tests
VAD Tests
Latency Tests
Noise Tests
Regression Tests
Failure Tests
```

---

# 93. AUDIO TEST DATA

The test suite should include:

```text
Clean Speech
Male Voices
Female Voices
Different Accents
German
English
Turkish
Background Noise
Keyboard Noise
Music
Multiple Speakers
Whispered Speech
Fast Speech
Slow Speech
Incomplete Sentences
Long Pauses
Interruptions
```

---

# 94. VAD TESTING

VAD should be tested against:

```text
Silence
Speech
Music
TV
Fan
Keyboard
Door
Traffic
Multiple Speakers
```

The system should measure false activations.

---

# 95. WAKE-WORD TESTING

Wake-word evaluation must include:

```text
Correct Wake
Similar Words
Background Speech
TV Speech
Multiple Speakers
Whisper
Different Accents
Different Distances
Different Microphones
```

---

# 96. STT TESTING

STT regression tests should compare:

```text
Expected Transcript
vs
Actual Transcript
```

using:

```text
WER
CER
Semantic Accuracy
Named Entity Accuracy
Command Accuracy
```

Command accuracy is particularly important.

Example:

```text
"Open GitHub"
```

being transcribed as something semantically similar may still be acceptable.

But:

```text
"Delete the file"
```

being misrecognized as another command is high risk.

---

# 97. TTS TESTING

TTS should be tested for:

```text
Pronunciation
Punctuation
Numbers
Dates
URLs
Technical Terms
Names
German
Turkish
English
Long Text
Short Text
Streaming
Interruptions
```

---

# 98. SECURITY TESTING

Security tests should include:

```text
Unauthorized Microphone Access
Unauthorized Recording
Credential Leakage
Transcript Leakage
Audio Artifact Leakage
Cloud Upload Without Permission
Sensitive Data in Logs
Unauthorized Voice Commands
Voice Spoofing
Permission Bypass
```

---

# 99. VOICE SPOOFING

Voice matching must not be treated as secure authentication unless a future dedicated security architecture explicitly validates it.

Voice cloning and synthetic speech can make speaker identification unreliable as a sole security mechanism.

High-risk actions require independent authorization.

---

# 100. MODEL SUPPLY CHAIN

Voice models are executable data in practical terms.

They must be treated as supply-chain dependencies.

Bootstrap and Version Lock should verify:

```text
Model Identifier
Model Version
Revision
Checksum
Source
License
```

---

# 101. MODEL DOWNLOADS

Models must be downloaded from approved sources.

The system should not blindly execute arbitrary model files from user-provided URLs.

Model acquisition pipeline:

```text
Approved Model
 ↓
Approved Source
 ↓
Download
 ↓
Checksum
 ↓
License Verification
 ↓
Install
```

---

# 102. MODEL STORAGE

Models should live in controlled model storage.

Conceptually:

```text
models/
├── stt/
├── tts/
├── vad/
└── wakeword/
```

The exact directory structure will be defined later.

---

# 103. BOOTSTRAP REQUIREMENTS

Bootstrap must support:

```text
Audio Runtime Dependencies
VAD Model
STT Runtime
STT Model
TTS Runtime
TTS Model
Audio Device Checks
Platform Dependencies
```

It must verify the installation.

---

# 104. VOICE SMOKE TEST

A minimal voice smoke test should be:

```text
Detect Microphone
 ↓
Capture Audio
 ↓
Detect Speech
 ↓
Transcribe
 ↓
Generate Response
 ↓
Synthesize Speech
 ↓
Play Audio
```

A successful smoke test proves that the complete voice chain is operational.

---

# 105. MANIFEST REQUIREMENTS

The future Manifest should be able to represent:

```yaml
voice:
  enabled: true

  input:
    device: default
    sample_rate: configurable

  vad:
    provider: silero

  stt:
    provider: faster-whisper

  tts:
    provider: kokoro

  wake_word:
    enabled: false

  streaming:
    enabled: true

  cloud_fallback:
    enabled: false
```

This is conceptual only.

The final schema belongs to the Manifest specification.

---

# 106. VERSION LOCK REQUIREMENTS

Version Lock SHALL capture:

```text
Audio Runtime
Audio Backend
VAD Runtime
VAD Model
STT Runtime
STT Model
TTS Runtime
TTS Model
Wake Word Runtime
Wake Word Model
Relevant Native Dependencies
Container Images
```

Exact versions must not be frozen in this document.

---

# 107. COMPLIANCE CHECKER REQUIREMENTS

The Architecture Compliance Checker should verify:

```text
Approved VAD
Approved STT
Approved TTS
Model License
Model Checksum
Audio Security
Permission Boundary
Cloud Policy
Credential Isolation
Streaming Interface
Voice Tool Boundary
Observability
Version Lock
Manifest
```

---

# 108. VOICE TOOL BOUNDARY

The LLM should never directly manipulate:

```text
Microphone Driver
Audio Device
STT Runtime
TTS Runtime
```

Correct:

```text
Agent
 ↓
Voice Capability
 ↓
Voice Runtime
 ↓
STT / TTS
```

---

# 109. JARVIS VOICE CAPABILITY API

Conceptually:

```text
voice.listen()
voice.transcribe()
voice.speak()
voice.stop()
voice.pause()
voice.resume()
voice.set_language()
voice.set_voice()
voice.get_devices()
voice.set_input_device()
voice.set_output_device()
```

The final API belongs to core implementation.

---

# 110. CLOUD VS LOCAL DECISION

The default policy is:

```text
LOCAL FIRST
```

because JARVIS is intended to provide:

- privacy,
- low recurring cost,
- offline capability,
- predictable latency,
- independence from external vendors.

Cloud services remain useful when:

```text
Local Quality Insufficient
Local Hardware Insufficient
Specialized Voice Required
Temporary Fallback Required
```

---

# 111. VENDOR LOCK-IN

The architecture must avoid:

```text
JARVIS
 ↓
Vendor API
 ↓
Vendor-specific voice architecture
```

Instead:

```text
JARVIS Voice Interface
        ↓
Provider Adapter
        ↓
Local / Cloud Provider
```

This permits future migration.

---

# 112. PROVIDER ADAPTER

The architecture should define:

```text
STTProvider
TTSProvider
VADProvider
WakeWordProvider
AudioInputProvider
AudioOutputProvider
```

This allows:

```text
faster-whisper
whisper.cpp
cloud STT
```

to coexist behind a common interface.

---

# 113. PROVIDER SELECTION

Provider selection may depend on:

```text
Language
Latency
Hardware
Privacy
Cost
Quality
Availability
Task
```

Example:

```text
Normal conversation
→ Local STT

Long offline recording
→ CPU STT

High-accuracy special task
→ Approved cloud STT
```

---

# 114. COST CONTROL

Cloud audio usage should be tracked.

Metrics:

```text
Audio Seconds
Characters
Requests
Cost
Provider
Latency
```

Budget policies should be supported.

---

# 115. OFFLINE MODE

JARVIS should eventually support:

```text
FULL OFFLINE VOICE
```

meaning:

```text
Microphone
 ↓
Local VAD
 ↓
Local STT
 ↓
Local JARVIS
 ↓
Local TTS
 ↓
Speaker
```

No external network should be required for core voice operation.

---

# 116. OFFLINE LIMITATIONS

Offline mode may have reduced:

```text
Voice Quality
Language Coverage
Latency
Model Size
```

depending on hardware.

The system should expose these limitations rather than silently falling back to cloud services.

---

# 117. NETWORK LOSS

If network connectivity disappears during an active voice session:

```text
Network Lost
 ↓
Check Local Capability
 ↓
Continue Locally
```

where possible.

---

# 118. DEVELOPMENT MATURITY LEVELS

Voice development should progress through:

### Level 1

```text
Push-to-Talk
+
STT
+
LLM
+
TTS
```

### Level 2

```text
VAD
+
Streaming
+
Interruptions
```

### Level 3

```text
Wake Word
+
Low Latency
+
Session State
```

### Level 4

```text
Full Duplex
+
Echo Cancellation
+
Advanced Turn Taking
```

### Level 5

```text
Multi-user
+
Speaker Identification
+
Adaptive Voice
```

The architecture supports all levels without requiring all features in the initial implementation.

---

# 119. RECOMMENDED V1 VOICE ARCHITECTURE

The initial JARVIS implementation should target:

```text
Audio Capture
        ↓
Silero VAD
        ↓
faster-whisper
        ↓
JARVIS Core
        ↓
Kokoro TTS
        ↓
Audio Playback
```

with:

```text
Streaming
+
Interruption Architecture
+
Provider Abstraction
+
Security Boundary
+
Observability
```

implemented from the beginning.

Wake-word functionality may initially remain optional.

---

# 120. RECOMMENDED FALLBACK ARCHITECTURE

If primary components fail:

```text
VAD:
Silero
 ↓
WebRTC fallback
```

```text
STT:
faster-whisper
 ↓
whisper.cpp
```

```text
TTS:
Kokoro
 ↓
Approved secondary TTS
```

The exact fallback providers must be finalized before production.

---

# 121. FINAL TECHNOLOGY STATUS

```text
┌──────────────────────────────────────────────────┐
│ JARVIS VOICE & AUDIO STACK — v1                 │
├──────────────────────────────────────────────────┤
│ Audio Capture        APPROVED ARCHITECTURE       │
│ Audio Device Layer   APPROVED ARCHITECTURE       │
│                                                  │
│ VAD                  Silero VAD — APPROVED      │
│ VAD Fallback         WebRTC VAD — CONDITIONAL   │
│                                                  │
│ STT                  faster-whisper — APPROVED  │
│ STT Fallback         whisper.cpp — APPROVED     │
│ STT Reference        OpenAI Whisper              │
│                                                  │
│ TTS                  Kokoro — APPROVED          │
│ TTS Advanced         Chatterbox — EXPERIMENTAL  │
│ TTS Optional         Piper — CONDITIONAL        │
│ TTS Legacy           Coqui — EXPERIMENTAL       │
│                                                  │
│ Wake Word            DEFERRED                   │
│ Speaker ID           DEFERRED                   │
│ Full Duplex          ARCHITECTURE SUPPORTED     │
│ Cloud Fallback       ARCHITECTURE SUPPORTED     │
└──────────────────────────────────────────────────┘
```

---

# 122. WHY THIS STACK

The proposed v1 stack:

```text
Silero VAD
+
faster-whisper
+
Kokoro
```

is selected because it provides a strong combination of:

```text
Local Execution
+
Open / Permissive Licensing
+
Python Compatibility
+
Low Latency Potential
+
Hardware Flexibility
+
Privacy
+
Provider Independence
```

Silero VAD is MIT licensed; faster-whisper is MIT licensed; Kokoro's model weights are Apache 2.0 licensed. citeturn1search0turn0search0turn2search1

This does **not** mean the entire voice stack is automatically license-safe: individual voice packs, model assets and transitive dependencies still require review.

---

# 123. LICENSE AND COMPLIANCE RULE

The following distinction is mandatory:

```text
Software License
        ≠
Model License
        ≠
Voice License
        ≠
Dataset License
        ≠
Output Rights
```

All must be evaluated before production distribution.

This is particularly relevant to Piper, where the current codebase is GPL-3.0-or-later and the project's voice documentation explicitly states that individual voice model licenses must be reviewed. citeturn1search5turn1search6turn1search8

---

# 124. REJECTED / NON-PRIMARY TECHNOLOGIES

## Piper

Status:

```text
NOT DEFAULT
```

Reason:

```text
GPL-3.0-or-later core
+
individual voice licensing complexity
+
future distribution flexibility concerns
```

Piper remains available for evaluation and user-specific deployments where licensing requirements are satisfied.

---

## Coqui TTS

Status:

```text
NOT PRIMARY
```

Reason:

```text
Older release cadence
+
legacy ecosystem position
+
better current alternatives
```

It remains useful for research and comparison.

---

## Raw WebRTC VAD

Status:

```text
FALLBACK
```

Reason:

```text
Very lightweight
+
mature
+
useful fallback
```

but Silero is preferred for primary speech detection.

---

# 125. FUTURE TECHNOLOGY WATCH

The following areas should be monitored:

```text
Real-Time Speech-to-Speech Models
Full-Duplex Foundation Models
Native Audio-Language Models
Streaming Multimodal Models
Neural Audio Codecs
On-Device Speech Models
Improved Wake Word Models
Speaker Diarization
Personal Voice Models
Low-Latency Voice Cloning
Neural Echo Cancellation
Audio Understanding Models
```

A particularly important future direction is speech-to-speech foundation models that could eventually collapse:

```text
STT
+
LLM
+
TTS
```

into a more unified conversational model.

However:

```text
Newer
≠
Automatically Better
```

JARVIS should retain the modular voice architecture until such models demonstrably outperform the modular stack in:

```text
Latency
Quality
Reliability
Control
Observability
Privacy
Cost
Licensing
```

---

# 126. FUTURE DIRECT SPEECH-TO-SPEECH

The long-term architecture may eventually support:

```text
Audio
 ↓
Speech-to-Speech Model
 ↓
Audio
```

alongside the modular pipeline:

```text
Audio
 ↓
STT
 ↓
JARVIS Core
 ↓
TTS
 ↓
Audio
```

Both should be possible behind the same:

```text
Voice Interface
```

---

# 127. NO PREMATURE MICROservices

The initial voice architecture should not automatically become:

```text
STT Microservice
TTS Microservice
VAD Microservice
Audio Microservice
Wakeword Microservice
```

unless there is a demonstrated need.

Logical modularity comes first.

Physical separation comes later.

---

# 128. DEFINITION OF DONE

The voice and audio stack is operationally complete when:

```text
[ ] Audio device abstraction exists
[ ] Microphone capture works
[ ] Audio playback works
[ ] VAD works
[ ] STT works
[ ] TTS works
[ ] Provider abstraction exists
[ ] Streaming pipeline works
[ ] Interruption works
[ ] Error recovery works
[ ] Security boundary exists
[ ] Cloud fallback policy exists
[ ] Offline mode exists
[ ] Observability exists
[ ] Voice smoke test exists
[ ] Windows validated
[ ] Linux validated
[ ] CI tests exist
[ ] Model checksums exist
[ ] Model licensing is tracked
[ ] Version Lock integration exists
[ ] Manifest integration exists
[ ] Compliance checks exist
```

---

# 129. FINAL ARCHITECTURAL RULES

### Rule 1

**Voice is a capability, not the JARVIS core.**

### Rule 2

**The voice architecture must remain provider-independent.**

### Rule 3

**Local inference is preferred where practical.**

### Rule 4

**Microphone access is a privileged capability.**

### Rule 5

**Raw audio is not persistent memory by default.**

### Rule 6

**Wake-word detection is not authentication.**

### Rule 7

**Voice identity must not be the sole authorization mechanism for high-risk actions.**

### Rule 8

**STT confidence must influence command execution safety.**

### Rule 9

**VAD, STT and TTS must remain independently replaceable.**

### Rule 10

**Streaming must be supported by the architecture from the beginning.**

### Rule 11

**Barge-in and interruption must be first-class concepts.**

### Rule 12

**Audio device failures must not crash the JARVIS core.**

### Rule 13

**Cloud audio transmission requires explicit policy.**

### Rule 14

**Model licenses must be evaluated separately from software licenses.**

### Rule 15

**Model versions belong in Version Lock.**

### Rule 16

**Voice model versions belong in Approved Models and Version Lock.**

### Rule 17

**Arbitrary voice/model downloads are prohibited.**

### Rule 18

**Audio artifacts must be protected as sensitive data.**

### Rule 19

**Full-duplex conversation is a supported architectural goal, not an initial implementation requirement.**

### Rule 20

**A future speech-to-speech model may replace the modular pipeline only after formal evaluation.**

---

# 130. SOURCE BASIS

The technology evaluation in this document is based primarily on official project documentation and repositories.

Key sources include:

- Silero VAD — official repository and license.
- faster-whisper — official repository and releases.
- OpenAI Whisper — official repository and license.
- whisper.cpp — official repository and license.
- Kokoro — official repository and model card.
- Chatterbox — official repository and license.
- Piper — official archived repository, current OHF-Voice repository, license and voice documentation.
- Coqui TTS — official repository.
- WebRTC VAD — official Python binding repository.
- NAudio — official repository, where relevant for platform-specific audio considerations.

The exact dependency and model versions are deliberately not frozen here.

They belong to:

```text
VERSION LOCK v1
```

---

# 131. HANDOFF TO NEXT ARCHITECTURAL PHASE

The dependency chain is:

```text
08_VOICE_AND_AUDIO_STACK.md
             │
             ▼
      19_APPROVED_MODELS.md
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
 Architecture Compliance Checker
             │
             ▼
       Voice Runtime
             │
             ▼
        Voice Agent
```

The important distinction is:

```text
08_BROWSER...
→ chooses browser technology

08_VOICE...
→ chooses voice/audio technology families

19_APPROVED_MODELS...
→ chooses exact models

VERSION LOCK...
→ chooses exact versions/revisions/checksums
```

---

# 132. FINAL DECISION

```text
========================================================
JARVIS VOICE & AUDIO STACK — FINAL v1 DECISION
========================================================

AUDIO ARCHITECTURE:
    Modular
    Streaming-capable
    Provider-independent
    Local-first

VAD:
    Silero VAD
    STATUS: APPROVED

VAD FALLBACK:
    WebRTC VAD
    STATUS: CONDITIONAL

STT:
    faster-whisper
    STATUS: APPROVED

STT FALLBACK:
    whisper.cpp
    STATUS: APPROVED

STT REFERENCE:
    OpenAI Whisper

TTS:
    Kokoro
    STATUS: APPROVED CANDIDATE

TTS ADVANCED:
    Chatterbox
    STATUS: EXPERIMENTAL

TTS OPTIONAL:
    Piper
    STATUS: CONDITIONAL / NOT DEFAULT

TTS LEGACY:
    Coqui TTS
    STATUS: EXPERIMENTAL

WAKE WORD:
    DEFERRED

SPEAKER IDENTIFICATION:
    DEFERRED

FULL DUPLEX:
    ARCHITECTURALLY SUPPORTED

BARGE-IN:
    REQUIRED

LOCAL-FIRST:
    REQUIRED

CLOUD FALLBACK:
    SUPPORTED, POLICY CONTROLLED

RAW AUDIO RETENTION:
    DISABLED BY DEFAULT

VERSION:
    DEFERRED TO VERSION LOCK

MODEL VERSION:
    DEFERRED TO APPROVED MODELS + VERSION LOCK

========================================================
PRIMARY V1 VOICE PIPELINE:

Microphone
    ↓
Audio Capture
    ↓
Silero VAD
    ↓
faster-whisper
    ↓
JARVIS Core
    ↓
Kokoro
    ↓
Audio Playback

========================================================
```

**Final architectural decision:** JARVIS v1 will use a modular, local-first voice architecture with **Silero VAD + faster-whisper STT + Kokoro TTS** as the primary technology path, while maintaining provider adapters for future replacement and fallback.