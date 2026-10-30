# Windows voice and interactive inference (AURA)

## Local Turkish speech

The original default Kokoro provider uses an English voice (`af_heart`).
AURA also has a *governed* Piper MCP provider using the same
`speech.synthesize` capability and Permission Engine policy. The Turkish
provider is explicit: no alternate browser WebSpeech fallback, no remote
speech API, and no direct tool bypass.

The current Turkish `tr_TR-dfki-medium` Piper voice is **CC BY-NC-SA 4.0**
according to its [MODEL_CARD](https://huggingface.co/rhasspy/piper-voices/blob/main/tr/tr_TR/dfki/medium/MODEL_CARD).
This voice **is not cleared for commercial use**. Read its terms, attribution
requirements and the Piper runtime's own GPLv3 terms before installing.
The setup script refuses to download until you explicitly acknowledge the
model license. Commercial operators must supply a separately licensed
Turkish Piper voice and its `.onnx.json` configuration instead.

From PowerShell with the repository and venv already installed:

```powershell
Set-Location D:\AURA\JAS
.\scripts\setup-turkish-tts.ps1 -AcceptVoiceLicense
.\scripts\Start-AURA.bat
```

The setup script installs optional `piper-tts==1.8.0` into the **local**
Core venv, downloads the voice **outside the repository** to
`D:\AURA\voices\piper`, and sets `AURA_TTS_PROVIDER=piper`,
`AURA_PIPER_MODEL_PATH` and `AURA_PIPER_CONFIG_PATH` in `core/.env.local`.
An `uv sync` can remove untracked optional packages; rerun the setup after
a locked environment rebuild. Do not commit `.env.local` or voice binaries.
No voice model is downloaded or enabled without the explicit setup action.

For an independently licensed Turkish Piper voice, place its files locally
and set the three variables manually. The provider validates `tr_TR`, caches
the loaded ONNX session, and emits structured WAV data only after
MCP Gateway authorization.

## Interactive local inference

The Windows launcher enables `AURA_OLLAMA_FAST_RESPONSE=1` by default:
- Ollama `think=false` for the interactive Qwen3 chat request
- a bounded 384-token response budget by default
- `keep_alive=10m` (trades GPU memory for lower model load latency)

Override `AURA_OLLAMA_FAST_MAX_TOKENS` (64..1024) or set
`AURA_OLLAMA_FAST_RESPONSE=0` for longer, more reflective responses.
An explicit request `max_tokens` always takes precedence. These are
performance trade-offs, **not guarantees** of a particular latency or quality.
The existing API response is still non-streaming: the time to first spoken
audio will include LLM generation plus TTS. Streaming is not claimed here.

## Health projection

`GET /api/health` now returns `components.event_bus.status` from the
actual runtime dispatcher, and `components.learning.status` from the real
continuous-learning scheduler. The scheduler is currently not wired in the
canonical composition root and will truthfully appear as
`not_configured`, **not** as a healthy running learner. Do not enable
background learning merely to make a dashboard indicator green; it needs
a separate explicit resource/permission/deployment review.
