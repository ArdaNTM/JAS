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
capture adapter requires Pillow's `PIL.ImageGrab` on an interactive Windows
desktop; ensure Pillow is available in the Core Python environment. Vision
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
