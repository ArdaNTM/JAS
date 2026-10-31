# AURA global HUD and consented ScreenRead (Windows, opt-in)

This package adds a second **Electron-only** browser window that is independent
of the normal Edge app/tab. It overlays other windows with a transparent,
frameless, always-on-top, taskbar-free shell. Windows mouse clicks pass through
by default. Press **Ctrl+Alt+H** to temporarily enable HUD controls and press
again to return to click-through. The system tray can show/hide the HUD.

The HUD is a presentation surface, **not** a new execution authority: text
panels are published as bounded `HUDPanelShown` Kernel events and projected
through the existing local SSE allowlist. It renders an illustrative wireframe
vehicle, scanning lines and reticles. The wireframe is **not a verified
photograph, CAD object, detection bounding box or live camera measurement**.

## Setup

Requires Core and Vite UI to be started by the existing
`scripts/Start-AURA.bat` supervisor. The supervisor keeps Core and UI alive
until Enter is pressed even if the main Edge window is closed. Electron HUD
launches as a separate child process only when enabled; it **does not start
another Core**. When the supervisor ends it stops its owned Electron tree.

From PowerShell in the JAS root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\enable-aura-hud.ps1
.\scripts\Start-AURA.bat
```

Optional screen analysis (requires operator's explicit action):

```powershell
ollama pull qwen2.5vl:3b
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\enable-aura-hud.ps1 -EnableScreenRead
.\scripts\Start-AURA.bat
```

The installer adds an uncommitted base64 ApprovalStore fingerprint key if
missing, never prints it, and does not overwrite an existing key. Existing
PostgreSQL, MinIO, Ollama and speech settings remain unchanged. The vision
capture adapter prefers Pillow's `PIL.ImageGrab` where available. On interactive Windows
without Pillow, it uses a bounded, in-memory PowerShell/.NET screenshot
fallback; neither path persists captured frames. Vision
uses the loopback Ollama endpoint and local `qwen2.5vl:3b` model; remote
endpoints are forbidden. No model download happens without explicit operator
request. HUD remains useful even with ScreenRead disabled.

## One-shot security boundary

1. The HUD's **Screen Read** button submits an authenticated, localhost-only
   HTTP request with a specific question and explicit `confirmed=true`.
2. Core requests authorization for high-risk `ScreenRead` with a
   principal-scoped local `PermissionPolicy(REQUIRE_APPROVAL)` through
   `MCPGateway`. A pending record is stored in the configured
   `ApprovalStore` (PostgreSQL in remote mode).
3. The user is shown a native Windows **Yes/No dialog (No by default)**.
   A denial stops here, without capturing pixels. Non-interactive or
   unsupported platforms fail closed.
4. A user click on Yes records approval by the distinct local physical
   operator identity. Core invokes the **same** Gateway request with this
   approval ID. The store must atomically consume it; replay fails. The
   provider checks the consumed high-risk dispatch grant itself.
5. Only after this chain does the provider capture one desktop frame.
   The image goes directly to the loopback Ollama vision model, is not stored
   or sent through SSE to the browser, and its interpretation is untrusted.
   Model output is never treated as instructions or permissions. The requesting
   HUD receives only the description (and an explicit flag that bounding
   boxes are *not verified*).

Voice triggers such as "Bana Porsche 911 göster" may publish a **presentation
event only**. No voice/text command can bypass native approval to read the
screen. ScreenControl (mouse/keyboard) remains an independent high-risk
capability and is not activated by HUD or ScreenRead.

Do not assume this version recognizes real people's identities, pinpoints
objects accurately or generates verified detection bounding boxes. Reticles
and scanning effects are intentionally procedural. Sensitive information
visible on the desktop may be seen by the local model when you consent, so
avoid screen capture during password or personal-data entry.

## Acceptance

CI validates permission denial, no capture before explicit approval,
approved one-time capture, local-only bearer-auth endpoints, Electron sandbox
and click-through configuration, Windows TypeScript build and release lock.
It cannot test Windows compositor behavior, native MessageBox interaction,
actual screenshot quality or GPU VLM latency in GitHub-hosted CI. Perform
those checks on the target Windows machine.

Documentation: <https://www.electronjs.org/docs/latest/api/browser-window>
and <https://ollama.com/library/qwen2.5vl>.

## Spatial HUD v2: runtime limits and safety

The HUD now spans the **primary Windows work area** with independent, bounded
hologram cards. A show request is a presentation event, not autonomous tool
execution. Up to nine cards may coexist; Ctrl+Alt+H enables dragging and
dismissal. When interaction is disabled, the overlay remains click-through.

ScreenRead (still one Windows-approved screenshot via MCP Gateway) requests
structured model-estimated normalized regions from Qwen2.5-VL. These are
**not verified detections**. Invalid/out-of-range boxes are discarded; the
ordinary text description remains available. Source imagery is never sent to
the renderer and object labels remain untrusted data. The overlay is aligned
to the primary display, not to other monitors or arbitrary 3D physical space.

The HUD control deck provides an optional continuous microphone mode. The
existing locally hosted faster-whisper STT receives voiced chunks while this
mode is enabled and recognizes the word "AURA" in the transcript. This is a
**transcript wake phrase**, not a dedicated offline keyword model: only
transcripts containing AURA trigger presentation commands. It must be opted
into every session and can be switched off to release the microphone. Neither
wake mode nor voice input can consent to ScreenRead or ScreenControl.

### ScreenRead 502 diagnosis

A 502 indicates an exception *after* one-time approval was consumed. New
responses include a non-sensitive `detail.code`, for example
`CAPTURE_DEPENDENCY_MISSING` (Pillow), `VISION_TIMEOUT` (local model warm-up),
`VISION_ENDPOINT_FAILURE`, or `SCREENREAD_PROVIDER_FAILURE`. No screenshot,
prompt, or raw VLM response is logged. Check `logs/aura-core.stderr.log`
and the diagnostic code; the actual cause requires a Windows repro.

If the error is `CAPTURE_DEPENDENCY_MISSING`, install Pillow into the exact
Python 3.13 environment reported by the AURA supervisor, for example
`core\.venv\Scripts\python.exe -m pip install Pillow`. Do not silently
download Python dependencies during startup. For slow local VLM warm-up,
`AURA_VISION_TIMEOUT_SECONDS` now defaults to 150 (allowed 1..180).

Reference principles: Microsoft Mixed Reality billboarding/tag-along and the
2026 Daniel Stallworth article "Iron Man Jarvis Capabilities" (capability
awareness and context-sensitive display, not screen-capture bypass).
