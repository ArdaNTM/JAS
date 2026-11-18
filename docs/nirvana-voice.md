# Nirvana Voice Engine

Nirvana Voice is an opt-in, local voice path:

`browser microphone → local VAD → sherpa-onnx KWS/streaming ASR → streaming LLM → sentence queue → governed Kokoro MCP TTS → ordered Web Audio`

The microphone remains browser-permission controlled. Speech text, wake words,
and audio never grant permission for actions. TTS execution crosses the existing
MCP Gateway and Permission Engine; generated audio is delivered only to the
local UI event stream.

## Safe default

`AURA_NIRVANA_VOICE_ENABLED` defaults to `0`. No package/model is installed,
downloaded, or loaded automatically. The normal local faster-whisper path
continues when the flag is off or sherpa is unhealthy.

## Provision sherpa-onnx

Install the optional package in the same Core environment, then obtain a
compatible transducer model and keyword model under their upstream licenses.
Do not add binaries to this repository. Create a local `core/.env.local` with:

```ini
AURA_NIRVANA_VOICE_ENABLED=1
AURA_SHERPA_MODEL_LICENSE_ACCEPTED=1
AURA_SHERPA_TOKENS_PATH=D:\AURA\voices\sherpa\tokens.txt
AURA_SHERPA_ENCODER_PATH=D:\AURA\voices\sherpa\encoder.onnx
AURA_SHERPA_DECODER_PATH=D:\AURA\voices\sherpa\decoder.onnx
AURA_SHERPA_JOINER_PATH=D:\AURA\voices\sherpa\joiner.onnx
AURA_SHERPA_KEYWORDS_PATH=D:\AURA\voices\sherpa\keywords.txt
```

The keywords file must contain the owner-selected wake phrase (for example,
`AURA`) in the model's expected keyword format. AURA reports unavailable rather
than silently switching provider if the package, explicit license acknowledgement,
or any model file is absent. Check `GET /api/speech/health` before enabling a
microphone session.

## Kokoro and playback

Kokoro remains the selected `speech.synthesize` MCP provider (`AURA_TTS_PROVIDER=kokoro`).
The UI queues sentence-sized LLM output in source order through Web Audio;
incoming speech cancels that queue and requests a server-side interrupt. There
is no browser cloud-TTS fallback.

## Measurements and acceptance

`GET /api/speech/health` reports bounded p50/p95 samples for completed STT,
TTS-first-audio, and browser-first-audio stages. They are observations for the
current machine/model, not a 500 ms promise. Run:

```powershell
Set-Location D:\AURA\JAS\core
uv sync --frozen
uv run pytest tests/test_full_duplex_session.py tests/test_sherpa_onnx_provider.py -q
Set-Location ..\aura-ui
npm run build
```

For a real local smoke test, start Core with its existing launcher, visit the
local UI, explicitly start the full-duplex session, then verify health before
and after one wake-word utterance. CI uses mocks and does not prove microphone,
model, GPU, or end-to-end latency behavior.

## Revision 2: real PCM chunks and distinct profiles

Separate English KWS (gigaspeech-3.3M) and English streaming ASR
(zipformer-en-2023-06-26) are mandatory when Nirvana is enabled. The
AudioWorklet streams 1600 Float32 samples at 16kHz every 100ms to
`/api/speech/sessions/pcm`. KWS wake samples never replay to ASR. Audio
has local-only HTTP authentication and explicit microphone permission.

Opt-in installation: `core/scripts/install_nirvana_voice_models.py`.
Kokoro ONNX fp16 + voice assets use upstream-published SHA-256. The two
sherpa archives do NOT publish hashes in their GitHub release API; their
first download uses pinned URLs, byte sizes, safe extraction and records a
first-use SHA-256 receipt (TOFU, not independent integrity). Confirm model
licenses and archive hashes through an independent channel before production.

In the isolated worktree, run:

```powershell
Set-Location D:\AURA\JAS-voice-check\core
uv sync --frozen --group dev
uv pip install --python .\.venv\Scripts\python.exe sherpa-onnx kokoro-onnx sentencepiece
.\.venv\Scripts\python.exe .\scripts\install_nirvana_voice_models.py --accept-model-licenses --destination D:\AURA\voice-models --env-file .\.env.local
uv run --no-sync --frozen pytest -q tests/test_sherpa_onnx_provider.py tests/test_nirvana_voice_pcm.py tests/test_full_duplex_session.py
uv run --no-sync --frozen python scripts/verify_final_lock.py
```

Start the standalone test worktree with its own launcher only after tests
pass, local remote-storage prerequisites are available, and Electron
dependencies are installed. Check `/api/speech/health` for separate KWS/ASR
English, Kokoro `en-us`, and model availability. Say "AURA" followed by a
short English command; this is not yet validated on the owner's microphone.

The Work 913ms figure was one *warm* local Ollama time-to-first-token,
not complete wake/ASR/TTS playback latency or a guaranteed target.
