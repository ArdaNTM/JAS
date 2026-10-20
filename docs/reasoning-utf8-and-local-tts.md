# Local Turkish TTS and reasoning execution

## UTF-8 from Windows PowerShell

The API accepts and returns UTF-8 JSON. Windows PowerShell 5.1 can create a .NET string correctly but send its request body using a legacy encoding in some invocation patterns. Send bytes explicitly when testing Turkish text:

```powershell
$body = @{
    directive = "Yapay zekâ modellerini araştır ve sonuçları karşılaştırıp özetle."
} | ConvertTo-Json -Compress

$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
$response = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/reasoning/plan" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body $utf8Body

$response.directive
```

Do not apply a server-side Latin-1/Windows-1252 round-trip to every request: it can corrupt valid text and cannot reliably recover text already damaged by an upstream client.

## Governed reasoning execution

- `POST /api/reasoning/plan` only previews a bounded plan and never executes tools.
- `POST /api/reasoning/execute` submits the public-web research step through the configured `AgentTaskService`; its runtime sends actual tool calls through `MCPGateway` and the Permission Engine.
- The research result is then passed to the configured inference backend to compose an answer. External side effects such as sending, deleting, buying, or publishing are not implemented by this adapter and are rejected, even when a caller sets `confirmed=true`.
- If the application is started without a task runtime, execution returns HTTP 503 rather than bypassing the Gateway.

Example:

```powershell
$body = @{
    directive = "Yapay zekâ modellerini araştır ve sonuçları karşılaştırıp özetle."
    confirmed = $false
} | ConvertTo-Json -Compress
$utf8Body = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/reasoning/execute" -Method Post -ContentType "application/json; charset=utf-8" -Body $utf8Body
```

## Optional local Piper TTS

Piper can be selected without changing the speech capability contract:

1. Install `piper-tts` in the same Python environment used to launch AURA.
2. Obtain a Piper ONNX voice model whose published metadata explicitly confirms Turkish (`tr_TR`); AURA does not download or bundle model files.
3. Set `AURA_TTS_PROVIDER=piper`, `AURA_PIPER_MODEL_PATH` to the model's `.onnx` file, and optionally `AURA_PIPER_CONFIG_PATH` to its matching JSON config.
4. Restart AURA so the MCP provider is registered from the environment.

If the package or model path is missing, synthesis returns an explicit provider error instead of silently falling back to an English voice. The selected model's actual Turkish quality still needs a local microphone/speaker listening test.
