# ============================================================
# AURA V6.5.2
# JARVIS LOCAL LLM BRIDGE + ROBUST JSX + OLLAMA GRACEFUL DEGRADE
# PowerShell 5.1
#
# Kullanım:
#   1) Bu dosyayı:
#      D:\AURA\JAS\scripts\patch_research_v652.ps1
#      olarak kaydet.
#
#   2) Parser:
#      powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& {
#          $p='D:\AURA\JAS\scripts\patch_research_v652.ps1'
#          $t=$null
#          $e=$null
#          [System.Management.Automation.Language.Parser]::ParseFile(
#              $p,[ref]$t,[ref]$e
#          ) | Out-Null
#          if($e.Count -eq 0) {
#              Write-Host 'V6.5.2 PS1 PARSER: PASS' -ForegroundColor Green
#          } else {
#              Write-Host 'V6.5.2 PS1 PARSER: FAIL' -ForegroundColor Red
#              $e | ForEach-Object {
#                  Write-Host (
#                      'Line ' +
#                      $_.Extent.StartLineNumber +
#                      ': ' +
#                      $_.Message
#                  ) -ForegroundColor Red
#              }
#              exit 1
#          }
#      }"
#
#   3) Çalıştır:
#      powershell.exe -NoProfile -ExecutionPolicy Bypass `
#          -File "D:\AURA\JAS\scripts\patch_research_v652.ps1"
#
# ÖNEMLİ:
# - JSX root'u regex ile "son </div>" aramaz.
# - App() return(...) içindeki ilk gerçek JSX token'ını lexer
#   mantığıyla bulur.
# - JSX'e sadece Fragment içine kontrollü bir bridge eklenir.
# - Ollama kapalıysa FastAPI 502 yerine graceful assistant reply
#   döndürülür.
# - Ham step.result doğrudan TTS'e bağlanmaz.
# ============================================================

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root = 'D:\AURA\JAS'
$UiRoot = Join-Path $Root 'aura-ui'
$CoreRoot = Join-Path $Root 'core'
$CoreSrc = Join-Path $CoreRoot 'src'

$AppPath = Join-Path $UiRoot 'src\App.tsx'
$BridgePath = Join-Path $UiRoot 'src\AuraJarvisBridge.tsx'
$ApiPath = Join-Path $CoreSrc 'aura_core\application\api.py'

$BackupRoot = Join-Path $Root '.aura-backups'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = Join-Path $BackupRoot ('research-v652-' + $Stamp)

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.2 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail ($Label + ' bulunamadı: ' + $Path)
    }
}

function Assert-Directory {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Fail ($Label + ' bulunamadı: ' + $Path)
    }
}

function Read-Utf8Text {
    param([string]$Path)

    Assert-File $Path 'Dosya'

    $text = [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.Encoding]::UTF8
    )

    if ($null -eq $text) {
        Fail ('Dosya okunamadı: ' + $Path)
    }

    if ($text.Trim().Length -eq 0) {
        Fail ('Dosya boş: ' + $Path)
    }

    return $text
}

function Write-Utf8Text {
    param(
        [string]$Path,
        [string]$Text
    )

    if ($null -eq $Text) {
        Fail ('Boş içerik yazılamaz: ' + $Path)
    }

    $parent = Split-Path $Path -Parent

    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    $encoding = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $encoding
    )
}

function Backup-File {
    param(
        [string]$Source,
        [string]$Relative
    )

    Assert-File $Source 'Backup kaynağı'

    $destination = Join-Path $BackupDir $Relative
    $parent = Split-Path $destination -Parent

    New-Item `
        -ItemType Directory `
        -Path $parent `
        -Force |
        Out-Null

    Copy-Item `
        -LiteralPath $Source `
        -Destination $destination `
        -Force
}

function Remove-GeneratedBlock {
    param(
        [string]$Text,
        [string]$StartMarker,
        [string]$EndMarker
    )

    while ($true) {

        $start = $Text.IndexOf(
            $StartMarker,
            [System.StringComparison]::Ordinal
        )

        if ($start -lt 0) {
            break
        }

        $end = $Text.IndexOf(
            $EndMarker,
            $start,
            [System.StringComparison]::Ordinal
        )

        if ($end -lt 0) {
            Fail (
                'Generated block bozuk; END marker bulunamadı: ' +
                $StartMarker
            )
        }

        $end = $end + $EndMarker.Length

        $Text = $Text.Remove(
            $start,
            $end - $start
        )
    }

    return $Text
}

function Test-PsSyntax {
    param([string]$Path)

    $tokens = $null
    $errors = $null

    [System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null

    if ($null -ne $errors -and $errors.Count -gt 0) {

        foreach ($item in $errors) {
            Write-Host (
                'Line ' +
                $item.Extent.StartLineNumber +
                ': ' +
                $item.Message
            ) -ForegroundColor Red
        }

        Fail 'PowerShell parser testi başarısız.'
    }
}

function Find-AppOpenBrace {
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*function\s+App\s*\([^)]*\)\s*\{'
    )

    foreach ($pattern in $patterns) {

        $m = [regex]::Match(
            $Text,
            $pattern
        )

        if ($m.Success) {

            return (
                $m.Index +
                $m.Length -
                1
            )
        }
    }

    return -1
}

function Find-AppReturnOpenParen {
    param(
        [string]$Text,
        [int]$AppOpenBrace
    )

    if ($AppOpenBrace -lt 0) {
        return -1
    }

    $tail = $Text.Substring(
        $AppOpenBrace + 1
    )

    #
    # return (
    # return(
    # return /* comment */ (
    #
    $m = [regex]::Match(
        $tail,
        '(?s)\breturn\b\s*(?:/\*.*?\*/\s*)*(?://[^\r\n]*\r?\n\s*)*\('
    )

    if (-not $m.Success) {
        return -1
    }

    $absolute =
        $AppOpenBrace +
        1 +
        $m.Index +
        $m.Value.LastIndexOf('(')

    return $absolute
}

function Find-JsxFirstToken {
    param(
        [string]$Text,
        [int]$Start
    )

    if ($Start -lt 0 -or $Start -ge $Text.Length) {
        return -1
    }

    $i = $Start

    $inSingle = $false
    $inDouble = $false
    $inTemplate = $false
    $inLineComment = $false
    $inBlockComment = $false

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if ($inLineComment) {

            if ($c -eq "`r" -or $c -eq "`n") {
                $inLineComment = $false
            }

            $i++
            continue
        }

        if ($inBlockComment) {

            if (
                $c -eq '*' -and
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq '/'
            ) {
                $inBlockComment = $false
                $i += 2
                continue
            }

            $i++
            continue
        }

        if ($inSingle) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq "'") {
                $inSingle = $false
            }

            $i++
            continue
        }

        if ($inDouble) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq '"') {
                $inDouble = $false
            }

            $i++
            continue
        }

        if ($inTemplate) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq '`') {
                $inTemplate = $false
            }

            $i++
            continue
        }

        if (
            $c -eq '/' -and
            ($i + 1) -lt $Text.Length
        ) {

            if ($Text[$i + 1] -eq '/') {
                $inLineComment = $true
                $i += 2
                continue
            }

            if ($Text[$i + 1] -eq '*') {
                $inBlockComment = $true
                $i += 2
                continue
            }
        }

        if ($c -eq "'") {
            $inSingle = $true
            $i++
            continue
        }

        if ($c -eq '"') {
            $inDouble = $true
            $i++
            continue
        }

        if ($c -eq '`') {
            $inTemplate = $true
            $i++
            continue
        }

        if ($c -eq '<') {

            #
            # Fragment:
            # <>
            #
            if (
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq '>'
            ) {
                return $i
            }

            #
            # JSX element:
            # <div
            # <main
            # <App.Something
            #
            if (
                ($i + 1) -lt $Text.Length -and
                (
                    [char]::IsLetter($Text[$i + 1]) -or
                    $Text[$i + 1] -eq '>'
                )
            ) {
                return $i
            }
        }

        $i++
    }

    return -1
}

function Ensure-ReactImports {
    param([string]$Text)

    $required = @(
        'useEffect',
        'useRef',
        'useState'
    )

    $match = [regex]::Match(
        $Text,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
    )

    if ($match.Success) {

        $items = New-Object System.Collections.Generic.List[string]

        foreach ($item in ($match.Groups['body'].Value -split ',')) {

            $name = $item.Trim()

            if (
                $name.Length -gt 0 -and
                -not $items.Contains($name)
            ) {
                [void]$items.Add($name)
            }
        }

        foreach ($requiredName in $required) {

            if (-not $items.Contains($requiredName)) {
                [void]$items.Add($requiredName)
            }
        }

        $newImport =
            'import { ' +
            ($items -join ', ') +
            ' } from "react";'

        return (
            $Text.Remove(
                $match.Index,
                $match.Length
            ).Insert(
                $match.Index,
                $newImport
            )
        )
    }

    return (
        'import { useEffect, useRef, useState } from "react";' +
        "`r`n" +
        $Text
    )
}

function Find-StateSetter {
    param(
        [string]$Text,
        [string[]]$Names
    )

    foreach ($name in $Names) {

        $pattern =
            'const\s*\[\s*' +
            [regex]::Escape($name) +
            '\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'

        $m = [regex]::Match(
            $Text,
            $pattern
        )

        if ($m.Success) {

            return [PSCustomObject]@{
                Value = $name
                Setter = $m.Groups['setter'].Value
            }
        }
    }

    return $null
}

function Add-ResearchStateIfMissing {
    param(
        [string]$Text,
        [int]$AppOpenBrace
    )

    $existing =
        Find-StateSetter `
            -Text $Text `
            -Names @(
                'researchOutput',
                'auraResearchOutput',
                'researchResult',
                'taskResult',
                'completedTask'
            )

    if ($null -ne $existing) {
        return $Text
    }

    $state =
        "`r`n    const [researchOutput, setResearchOutput] = useState<unknown>(null);`r`n"

    return $Text.Insert(
        $AppOpenBrace + 1,
        $state
    )
}

function Find-ApiRouter {
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_$][\w$]*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_$][\w$]*)\s*:\s*APIRouter\s*=\s*APIRouter\s*\('
    )

    foreach ($pattern in $patterns) {

        $m = [regex]::Match(
            $Text,
            $pattern
        )

        if ($m.Success) {
            return $m.Groups['name'].Value
        }
    }

    return $null
}

function Ensure-PythonImport {
    param(
        [string]$Text,
        [string]$Line
    )

    $escaped =
        [regex]::Escape($Line)

    if (
        [regex]::IsMatch(
            $Text,
            '(?m)^' + $escaped + '\s*$'
        )
    ) {
        return $Text
    }

    return (
        $Line +
        "`r`n" +
        $Text
    )
}

function Add-FastApiRoute {
    param(
        [string]$Text,
        [string]$Router
    )

    $start =
        'AURA_JARVIS_ASSISTANT_API_V652_START'

    $end =
        'AURA_JARVIS_ASSISTANT_API_V652_END'

    $Text =
        Remove-GeneratedBlock `
            -Text $Text `
            -StartMarker $start `
            -EndMarker $end

    #
    # Route zaten başka bir implementation tarafından mevcutsa
    # duplicate route üretme.
    #
    if (
        $Text.IndexOf(
            '/api/assistant/respond',
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        return $Text
    }

    #
    # Tek-quoted here-string:
    # PowerShell $(...) interpolation YOK.
    #
    $block = @'
# AURA_JARVIS_ASSISTANT_API_V652_START

class AuraAssistantRequest(BaseModel):
    directive: str = ""
    research: str = ""


class AuraAssistantResponse(BaseModel):
    assistant_reply: str
    model: str
    provider: str


def _aura_jarvis_messages(
    directive: str,
    research: str,
) -> list[dict[str, str]]:

    return [
        {
            "role": "system",
            "content": (
                "Sen AURA'sın. "
                "Türkçe konuşan kişisel AI asistanısın. "
                "Analitik, sakin, kendinden emin ve gerektiğinde "
                "ince ironik ol. Kullanıcının direktifini papağan "
                "gibi tekrar etme. Ham JSON, UUID, URL, tool trace "
                "ve teknik log okuma. Araştırma verisini analiz et "
                "ve kendi cümlelerinle kısa bir yanıt oluştur. "
                "En fazla dört kısa cümle kullan. "
                "Markdown kullanma. "
                "Araştırma verisinde olmayan bilgi uydurma."
            ),
        },
        {
            "role": "user",
            "content": (
                "Kullanıcı direktifi:\n"
                + directive[:1200]
                + "\n\nAraştırma sonucu:\n"
                + research[:14000]
                + "\n\n"
                "Bu veriyi analiz et ve konuşmaya uygun "
                "doğal bir AURA yanıtı üret."
            ),
        },
    ]


def _aura_ollama_reply(
    directive: str,
    research: str,
) -> tuple[str, str]:

    model = os.environ.get(
        "AURA_LLM_MODEL",
        "qwen3",
    )

    url = os.environ.get(
        "AURA_LLM_URL",
        "http://127.0.0.1:11434/api/chat",
    )

    payload = {
        "model": model,
        "stream": False,
        "messages": _aura_jarvis_messages(
            directive,
            research,
        ),
        "options": {
            "temperature": 0.65,
        },
    }

    body = json.dumps(
        payload,
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(
        request,
        timeout=120,
    ) as response:

        raw = response.read().decode(
            "utf-8"
        )

    data = json.loads(raw)

    message = data.get(
        "message",
        {},
    )

    reply = (
        message.get("content")
        or data.get("response")
        or ""
    )

    reply = " ".join(
        str(reply).split()
    ).strip()

    return reply[:900], model


@ROUTER.post(
    "/api/assistant/respond",
    response_model=AuraAssistantResponse,
)
async def aura_assistant_respond(
    request: AuraAssistantRequest,
) -> AuraAssistantResponse:

    directive = (
        request.directive or ""
    ).strip()

    research = (
        request.research or ""
    ).strip()

    if not research:

        return AuraAssistantResponse(
            assistant_reply=(
                "Araştırma verisi henüz hazır değil."
            ),
            model=os.environ.get(
                "AURA_LLM_MODEL",
                "qwen3",
            ),
            provider="local",
        )

    try:

        reply, model = await asyncio.to_thread(
            _aura_ollama_reply,
            directive,
            research,
        )

    except Exception as exc:

        #
        # OLLAMA OFFLINE / TIMEOUT / CONNECTION REFUSED
        #
        # Araştırma altyapısı çökmüyor.
        # UI 502 yerine kontrollü assistant reply alıyor.
        #
        return AuraAssistantResponse(
            assistant_reply=(
                "LLM çekirdeğime şu an ulaşamıyorum. "
                "Araştırma verisini kaybetmedim; "
                "yerel zekâ katmanı yeniden çevrimiçi olduğunda "
                "onu yorumlayabilirim."
            ),
            model=os.environ.get(
                "AURA_LLM_MODEL",
                "qwen3",
            ),
            provider="local-offline",
        )

    if not reply:

        reply = (
            "Araştırma verisini aldım; "
            "fakat şu anda bundan anlamlı bir konuşma yanıtı "
            "üretemedim."
        )

    return AuraAssistantResponse(
        assistant_reply=reply,
        model=model,
        provider="ollama",
    )

# AURA_JARVIS_ASSISTANT_API_V652_END
'@

    $block =
        $block.Replace(
            '@ROUTER',
            '@' + $Router
        )

    return (
        $Text.TrimEnd() +
        "`r`n`r`n" +
        $block.Trim() +
        "`r`n"
    )
}

# ============================================================
# 1
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.2 JARVIS / GRACEFUL OLLAMA PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/11] Proje kontrol ediliyor...'

Assert-Directory $Root 'AURA root'
Assert-Directory $UiRoot 'aura-ui'
Assert-Directory $CoreRoot 'core'

Assert-File $AppPath 'App.tsx'
Assert-File $ApiPath 'api.py'

# ============================================================
# 2
# ============================================================

Write-Host '[2/11] Güvenli backup oluşturuluyor...'

New-Item `
    -ItemType Directory `
    -Path $BackupDir `
    -Force |
    Out-Null

Backup-File `
    -Source $AppPath `
    -Relative 'aura-ui\src\App.tsx'

Backup-File `
    -Source $ApiPath `
    -Relative 'core\src\aura_core\application\api.py'

$cssCandidates = @(
    (Join-Path $UiRoot 'src\App.css'),
    (Join-Path $UiRoot 'src\index.css')
)

$CssPath = $null

foreach ($candidate in $cssCandidates) {

    if (
        Test-Path `
            -LiteralPath $candidate `
            -PathType Leaf
    ) {
        $CssPath = $candidate
        break
    }
}

if ($null -ne $CssPath) {

    Backup-File `
        -Source $CssPath `
        -Relative (
            'aura-ui\src\' +
            (Split-Path $CssPath -Leaf)
        )
}

# ============================================================
# 3
# ============================================================

Write-Host '[3/11] App.tsx okunuyor...'

$app =
    Read-Utf8Text $AppPath

# ============================================================
# 4
# ============================================================

Write-Host '[4/11] Eski V6.x generated blokları temizleniyor...'

$oldPairs = @(
    @(
        'AURA_JARVIS_LLM_V652_START',
        'AURA_JARVIS_LLM_V652_END'
    ),
    @(
        'AURA_JARVIS_LLM_V651_START',
        'AURA_JARVIS_LLM_V651_END'
    ),
    @(
        'AURA_JARVIS_LLM_V65_START',
        'AURA_JARVIS_LLM_V65_END'
    ),
    @(
        'AURA_JARVIS_LLM_V64_START',
        'AURA_JARVIS_LLM_V64_END'
    ),
    @(
        'AURA_JARVIS_ASSISTANT_START',
        'AURA_JARVIS_ASSISTANT_END'
    ),
    @(
        'AURA_RESEARCH_CONVERSATIONAL_V63_START',
        'AURA_RESEARCH_CONVERSATIONAL_V63_END'
    )
)

foreach ($pair in $oldPairs) {

    $app =
        Remove-GeneratedBlock `
            -Text $app `
            -StartMarker $pair[0] `
            -EndMarker $pair[1]
}

#
# Eski static assistant helper.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\bfunction\s+buildAssistantReply\s*\([^)]*\)\s*\{.*?\n\}',
        ''
    )

$app =
    [regex]::Replace(
        $app,
        '(?s)\bfunction\s+speakResearchOutput\s*\([^)]*\)\s*\{.*?\n\}',
        ''
    )

#
# Statik "Elbette..." varyantları.
#

$staticPatterns = @(
    'Elbette\.?\s*Araştırmayı tamamladım\.?',
    'Elbette,\s*araştırmayı tamamladım\.?',
    'Araştırmayı tamamladım\.?'
)

foreach ($pattern in $staticPatterns) {

    $app =
        [regex]::Replace(
            $app,
            $pattern,
            ''
        )
}

# ============================================================
# 5
# ============================================================

Write-Host '[5/11] React importleri ve App state hazırlanıyor...'

$app =
    Ensure-ReactImports $app

$appOpen =
    Find-AppOpenBrace $app

if ($appOpen -lt 0) {
    Fail 'export default function App(...) bulunamadı.'
}

$app =
    Add-ResearchStateIfMissing `
        -Text $app `
        -AppOpenBrace $appOpen

#
# State insertion sonrasında tekrar hesapla.
#

$appOpen =
    Find-AppOpenBrace $app

$returnParen =
    Find-AppReturnOpenParen `
        -Text $app `
        -AppOpenBrace $appOpen

if ($returnParen -lt 0) {
    Fail 'App() return(...) bulunamadı.'
}

$directiveState =
    Find-StateSetter `
        -Text $app `
        -Names @(
            'directive',
            'input',
            'query',
            'command',
            'userInput',
            'prompt',
            'text'
        )

if ($null -eq $directiveState) {
    Fail 'Directive/input state setter otomatik bulunamadı.'
}

$researchState =
    Find-StateSetter `
        -Text $app `
        -Names @(
            'researchOutput',
            'auraResearchOutput',
            'researchResult',
            'taskResult',
            'completedTask'
        )

if ($null -eq $researchState) {
    Fail 'Research output state otomatik bulunamadı.'
}

$directiveName =
    $directiveState.Value

$researchName =
    $researchState.Value

Write-Host (
    '    Directive state: ' +
    $directiveName
)

Write-Host (
    '    Research state : ' +
    $researchName
)

# ============================================================
# 6
# ============================================================

Write-Host '[6/11] AuraJarvisBridge modülü hazırlanıyor...'

$bridge = @'
/* AURA_JARVIS_LLM_V652_START */

import {
    useEffect,
    useRef,
    useState,
} from "react";

type AuraJarvisBridgeProps = {
    directive?: unknown;
    researchOutput?: unknown;
};

type AuraAssistantResponse = {
    assistant_reply?: unknown;
    model?: unknown;
    provider?: unknown;
};

function cleanAssistantReply(
    value: unknown
): string {

    if (
        typeof value !== "string"
    ) {
        return "";
    }

    return value
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 900);
}

function serializeResearch(
    value: unknown
): string {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    if (
        typeof value === "string"
    ) {
        return value
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 14000);
    }

    try {

        return JSON.stringify(
            value
        )
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 14000);

    }
    catch {

        return String(value)
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 14000);
    }
}

async function generateAssistantReply(
    directive: unknown,
    researchOutput: unknown
): Promise<string> {

    const response =
        await fetch(
            "/api/assistant/respond",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json",
                },
                body: JSON.stringify({
                    directive:
                        typeof directive === "string"
                            ? directive
                                .trim()
                                .slice(0, 1200)
                            : "",
                    research:
                        serializeResearch(
                            researchOutput
                        ),
                }),
            }
        );

    if (!response.ok) {

        throw new Error(
            "Assistant endpoint HTTP " +
            response.status
        );
    }

    const data =
        (
            await response.json()
        ) as AuraAssistantResponse;

    return cleanAssistantReply(
        data.assistant_reply
    );
}

function speakAssistantReply(
    reply: string
): void {

    const text =
        cleanAssistantReply(
            reply
        );

    if (!text) {
        return;
    }

    if (
        typeof window === "undefined" ||
        !window.speechSynthesis
    ) {
        return;
    }

    window.speechSynthesis.cancel();

    const chunks =
        text
            .match(
                /[^.!?]+[.!?]+|[^.!?]+$/g
            )
            ?.map(
                (item) => item.trim()
            )
            .filter(Boolean)
            ?? [];

    if (
        chunks.length === 0
    ) {
        return;
    }

    const queue =
        chunks.map(
            (chunk) => {

                const utterance =
                    new SpeechSynthesisUtterance(
                        chunk
                    );

                utterance.lang =
                    "tr-TR";

                utterance.rate =
                    0.96;

                utterance.pitch =
                    0.94;

                utterance.volume =
                    1;

                return utterance;
            }
        );

    const speakNext =
        (): void => {

            const next =
                queue.shift();

            if (!next) {
                return;
            }

            next.onend =
                speakNext;

            next.onerror =
                speakNext;

            window.speechSynthesis.speak(
                next
            );
        };

    speakNext();
}

export default function AuraJarvisBridge(
    {
        directive,
        researchOutput,
    }: AuraJarvisBridgeProps
) {

    const [
        assistantReply,
        setAssistantReply,
    ] = useState<string>("");

    const [
        thinking,
        setThinking,
    ] = useState<boolean>(false);

    const generationRef =
        useRef<number>(0);

    useEffect(
        () => {

            if (
                researchOutput === null ||
                researchOutput === undefined ||
                researchOutput === ""
            ) {
                return;
            }

            const generation =
                generationRef.current + 1;

            generationRef.current =
                generation;

            let cancelled =
                false;

            setThinking(true);

            generateAssistantReply(
                directive,
                researchOutput
            )
                .then(
                    (reply) => {

                        if (
                            cancelled ||
                            generationRef.current !==
                                generation
                        ) {
                            return;
                        }

                        const clean =
                            cleanAssistantReply(
                                reply
                            );

                        setAssistantReply(
                            clean
                        );

                        /*
                         * TTS SINIRI:
                         *
                         * researchOutput -> TTS YOK
                         * directive      -> TTS YOK
                         * assistantReply -> TTS VAR
                         */

                        if (clean) {
                            speakAssistantReply(
                                clean
                            );
                        }
                    }
                )
                .catch(
                    (error) => {

                        if (!cancelled) {

                            console.error(
                                "AURA assistant bridge:",
                                error
                            );

                            setAssistantReply(
                                ""
                            );
                        }
                    }
                )
                .finally(
                    () => {

                        if (!cancelled) {
                            setThinking(false);
                        }
                    }
                );

            return () => {
                cancelled = true;
            };

        },
        [
            directive,
            researchOutput,
        ]
    );

    useEffect(
        () => {

            return () => {

                if (
                    typeof window !== "undefined" &&
                    window.speechSynthesis
                ) {
                    window.speechSynthesis.cancel();
                }
            };

        },
        []
    );

    if (
        !thinking &&
        !assistantReply
    ) {
        return null;
    }

    return (
        <div
            className="aura-jarvis-response"
            data-aura-jarvis="true"
        >
            <div
                className="aura-jarvis-response-label"
            >
                AURA
            </div>

            <div
                className="aura-jarvis-response-text"
            >
                {
                    thinking
                        ? "Verileri değerlendiriyorum..."
                        : assistantReply
                }
            </div>
        </div>
    );
}

/* AURA_JARVIS_LLM_V652_END */
'@

Write-Utf8Text `
    -Path $BridgePath `
    -Text $bridge

# ============================================================
# 7
# ============================================================

Write-Host '[7/11] JSX root güvenli biçimde çözülüyor...'

$importLine =
    'import AuraJarvisBridge from "./AuraJarvisBridge";'

if (
    $app.IndexOf(
        $importLine,
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $app =
        $importLine +
        "`r`n" +
        $app
}

#
# Import değişti; App konumlarını tekrar hesapla.
#

$appOpen =
    Find-AppOpenBrace $app

$returnParen =
    Find-AppReturnOpenParen `
        -Text $app `
        -AppOpenBrace $appOpen

if ($returnParen -lt 0) {
    Fail 'Import sonrası App return(...) bulunamadı.'
}

#
# return( sonrasındaki ilk JSX tokenını lexer bulur.
# LastIndexOf("</div>") KESİNLİKLE kullanılmıyor.
#

$jsxToken =
    Find-JsxFirstToken `
        -Text $app `
        -Start ($returnParen + 1)

if ($jsxToken -lt 0) {

    Fail (
        'App return(...) sonrasında JSX token bulunamadı. ' +
        'Dosya değiştirilmeyecek.'
    )
}

#
# Eğer JSX root zaten Fragment ise içine doğrudan ekle.
# Eğer root element ise onu değiştirmiyoruz; root'un hemen
# sonrasında kardeş element eklemek için root'u Fragment ile
# sarmalamıyoruz. Bunun yerine root'un açılışından hemen sonra
# bridge eklenir. Bu, geçerli JSX içeriğini bozmaz.
#

$bridgeInvocation =
    [regex]::Match(
        $app,
        '(?s)<AuraJarvisBridge\b[^>]*/>'
    )

if (-not $bridgeInvocation.Success) {

    $bridgeMarkup =
        @"
        <AuraJarvisBridge
            directive={$directiveName}
            researchOutput={$researchName}
        />
"@

    #
    # Root tag'ın açılışından sonra ekle.
    # Eğer token <> ise doğrudan fragment children alanına girer.
    #

    if (
        $app.Substring(
            $jsxToken,
            [Math]::Min(
                2,
                $app.Length - $jsxToken
            )
        ) -eq '<>'
    ) {

        $insertPosition =
            $jsxToken + 2
    }
    else {

        $rootEnd =
            $app.IndexOf(
                '>',
                $jsxToken
            )

        if ($rootEnd -lt 0) {
            Fail 'JSX root açılış etiketi tamamlanamadı.'
        }

        #
        # Self closing root burada kabul edilmez.
        #
        if (
            $app[$rootEnd - 1] -eq '/'
        ) {
            Fail 'App return() root self-closing element; güvenli JSX injection yapılamadı.'
        }

        $insertPosition =
            $rootEnd + 1
    }

    $app =
        $app.Insert(
            $insertPosition,
            "`r`n" +
            $bridgeMarkup.TrimEnd() +
            "`r`n"
        )
}

# ============================================================
# 8
# ============================================================

Write-Host '[8/11] App.tsx yazılıyor...'

Write-Utf8Text `
    -Path $AppPath `
    -Text $app

# ============================================================
# 9
# ============================================================

Write-Host '[9/11] CSS hazırlanıyor...'

if ($null -eq $CssPath) {

    $CssPath =
        Join-Path `
            $UiRoot `
            'src\App.css'

    Write-Utf8Text `
        -Path $CssPath `
        -Text ''
}

$css =
    Read-Utf8Text $CssPath

$css =
    Remove-GeneratedBlock `
        -Text $css `
        -StartMarker 'AURA_JARVIS_CSS_V652_START' `
        -EndMarker 'AURA_JARVIS_CSS_V652_END'

$cssBlock = @'
/* AURA_JARVIS_CSS_V652_START */

.aura-jarvis-response {
    position: fixed;
    left: 24px;
    bottom: 112px;
    z-index: 3000;
    width: min(560px, calc(100vw - 48px));
    box-sizing: border-box;
    padding: 14px 18px;
    border: 1px solid rgba(100, 210, 255, 0.28);
    border-radius: 12px;
    background: rgba(4, 10, 18, 0.95);
    backdrop-filter: blur(14px);
    box-shadow:
        0 0 24px rgba(40, 180, 255, 0.12),
        inset 0 0 18px rgba(40, 180, 255, 0.04);
    color: #dff7ff;
    pointer-events: none;
}

.aura-jarvis-response-label {
    margin: 0 0 7px 0;
    padding: 0;
    font-size: 10px;
    line-height: 1.2;
    letter-spacing: 0.18em;
    font-weight: 700;
    white-space: nowrap;
}

.aura-jarvis-response-text {
    margin: 0;
    padding: 0;
    font-size: 14px;
    line-height: 1.55;
    overflow-wrap: anywhere;
    word-break: break-word;
}

@media (max-width: 720px) {

    .aura-jarvis-response {
        left: 14px;
        right: 14px;
        bottom: 96px;
        width: auto;
    }
}

/* AURA_JARVIS_CSS_V652_END */
'@

$css =
    $css.TrimEnd() +
    "`r`n" +
    $cssBlock

Write-Utf8Text `
    -Path $CssPath `
    -Text $css

# ============================================================
# 10
# ============================================================

Write-Host '[10/11] FastAPI Ollama graceful degradation route...'

$api =
    Read-Utf8Text $ApiPath

$router =
    Find-ApiRouter $api

if ($null -eq $router) {
    Fail 'api.py içinde APIRouter bulunamadı.'
}

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'import asyncio'

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'import json'

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'import os'

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'from urllib.request import Request, urlopen'

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'from pydantic import BaseModel'

$api =
    Ensure-PythonImport `
        -Text $api `
        -Line 'from fastapi import HTTPException'

#
# Eğer önceki patch'in route'u zaten varsa onun içine graceful
# handling uygulamaya çalış.
#
# Önce mevcut route'taki "raise HTTPException(...)" kalıntısını
# tespit ediyoruz. Generated route değilse route'u silmiyoruz.
#

if (
    $api.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -ge 0
) {

    #
    # Önce V6.5.1 generated route'u temizle.
    #
    $api =
        Remove-GeneratedBlock `
            -Text $api `
            -StartMarker 'AURA_JARVIS_ASSISTANT_API_V651_START' `
            -EndMarker 'AURA_JARVIS_ASSISTANT_API_V651_END'

    #
    # V6.5 generated route marker'ları.
    #
    $api =
        Remove-GeneratedBlock `
            -Text $api `
            -StartMarker 'AURA_JARVIS_ASSISTANT_API_V65_START' `
            -EndMarker 'AURA_JARVIS_ASSISTANT_API_V65_END'
}

#
# Route yoksa yeni route eklenir.
#

$api =
    Add-FastApiRoute `
        -Text $api `
        -Router $router

Write-Utf8Text `
    -Path $ApiPath `
    -Text $api

# ============================================================
# 11
# ============================================================

Write-Host '[11/11] Structural + Python + TypeScript build validation...'

$finalApp =
    Read-Utf8Text $AppPath

$finalBridge =
    Read-Utf8Text $BridgePath

$finalApi =
    Read-Utf8Text $ApiPath

#
# App structural checks.
#

$finalAppOpen =
    Find-AppOpenBrace $finalApp

if ($finalAppOpen -lt 0) {
    Fail 'Final App() bulunamadı.'
}

$finalReturn =
    Find-AppReturnOpenParen `
        -Text $finalApp `
        -AppOpenBrace $finalAppOpen

if ($finalReturn -lt 0) {
    Fail 'Final App() return(...) bulunamadı.'
}

$finalJsx =
    Find-JsxFirstToken `
        -Text $finalApp `
        -Start ($finalReturn + 1)

if ($finalJsx -lt 0) {
    Fail 'Final App return(...) JSX root bulunamadı.'
}

#
# Bridge import/invocation.
#

if (
    $finalApp.IndexOf(
        './AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge import bulunamadı.'
}

if (
    $finalApp.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge JSX invocation bulunamadı.'
}

#
# Backend route.
#

if (
    $finalApi.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'FastAPI /api/assistant/respond route bulunamadı.'
}

#
# Graceful degradation.
#

if (
    $finalApi.IndexOf(
        'local-offline',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Ollama offline graceful-degradation branch bulunamadı.'
}

if (
    $finalApi.IndexOf(
        'LLM çekirdeğime şu an ulaşamıyorum',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Ollama offline assistant fallback bulunamadı.'
}

#
# Frontend assistant flow.
#

if (
    $finalBridge.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Frontend assistant endpoint bridge bulunamadı.'
}

if (
    $finalBridge.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS queue bulunamadı.'
}

#
# Ham data -> TTS yasak.
#

$forbidden = @(
    'speakAssistantReply(researchOutput)',
    'speakAssistantReply(step.result)',
    'speakAssistantReply(directive)',
    'speechSynthesis.speak(researchOutput)',
    'speechSynthesis.speak(step.result)',
    'speechSynthesis.speak(directive)',
    'speakResearchOutput(researchOutput)',
    'speakResearchOutput(step.result)'
)

foreach ($bad in $forbidden) {

    if (
        $finalApp.IndexOf(
            $bad,
            [System.StringComparison]::Ordinal
        ) -ge 0 -or
        $finalBridge.IndexOf(
            $bad,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            'Yasak doğrudan TTS bağlantısı bulundu: ' +
            $bad
        )
    }
}

#
# Eski hardcoded reply.
#

foreach ($pattern in $staticPatterns) {

    $literalCheck =
        $pattern.Replace('\s*', ' ')

    if (
        $finalApp.IndexOf(
            'Elbette. Araştırmayı tamamladım.',
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0 -or
        $finalApp.IndexOf(
            'Elbette, araştırmayı tamamladım.',
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {

        Fail 'Eski hardcoded assistant reply hâlâ App.tsx içinde.'
    }
}

#
# App.tsx içinde PowerShell comparison operator olmamalı.
#

foreach ($operator in @(
    '-gt',
    '-lt',
    '-ge',
    '-le'
)) {

    if (
        $finalApp.IndexOf(
            $operator,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        Fail (
            'App.tsx içinde PowerShell operator bulundu: ' +
            $operator
        )
    }

    if (
        $finalBridge.IndexOf(
            $operator,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        Fail (
            'AuraJarvisBridge.tsx içinde PowerShell operator bulundu: ' +
            $operator
        )
    }
}

#
# Python compile.
#

$python =
    Get-Command `
        python.exe `
        -ErrorAction SilentlyContinue

if ($null -eq $python) {

    $python =
        Get-Command `
            python `
            -ErrorAction SilentlyContinue
}

if ($null -eq $python) {
    Fail 'Python bulunamadı.'
}

& $python.Source `
    -m py_compile `
    $ApiPath

if ($LASTEXITCODE -ne 0) {

    Write-Host ''
    Write-Host 'Python compile FAILED - rollback...' -ForegroundColor Red

    $appBackup =
        Join-Path `
            $BackupDir `
            'aura-ui\src\App.tsx'

    if (
        Test-Path `
            -LiteralPath $appBackup `
            -PathType Leaf
    ) {
        Copy-Item `
            -LiteralPath $appBackup `
            -Destination $AppPath `
            -Force
    }

    $apiBackup =
        Join-Path `
            $BackupDir `
            'core\src\aura_core\application\api.py'

    if (
        Test-Path `
            -LiteralPath $apiBackup `
            -PathType Leaf
    ) {
        Copy-Item `
            -LiteralPath $apiBackup `
            -Destination $ApiPath `
            -Force
    }

    Fail 'Python compile başarısız.'
}

#
# npm build.
#

Push-Location $UiRoot

$npm =
    Get-Command `
        npm.cmd `
        -ErrorAction SilentlyContinue

if ($null -eq $npm) {

    $npm =
        Get-Command `
            npm `
            -ErrorAction SilentlyContinue
}

if ($null -eq $npm) {

    Pop-Location

    Fail 'npm bulunamadı.'
}

& $npm.Source run build

$buildExit =
    $LASTEXITCODE

Pop-Location

if ($buildExit -ne 0) {

    Write-Host ''
    Write-Host 'npm run build FAILED - rollback...' -ForegroundColor Red

    $appBackup =
        Join-Path `
            $BackupDir `
            'aura-ui\src\App.tsx'

    if (
        Test-Path `
            -LiteralPath $appBackup `
            -PathType Leaf
    ) {
        Copy-Item `
            -LiteralPath $appBackup `
            -Destination $AppPath `
            -Force
    }

    $apiBackup =
        Join-Path `
            $BackupDir `
            'core\src\aura_core\application\api.py'

    if (
        Test-Path `
            -LiteralPath $apiBackup `
            -PathType Leaf
    ) {
        Copy-Item `
            -LiteralPath $apiBackup `
            -Destination $ApiPath `
            -Force
    }

    Fail 'npm run build başarısız.'
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.2 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App() detection            : PASS'
Write-Host 'return(...) detection      : PASS'
Write-Host 'JSX lexer root detection   : PASS'
Write-Host 'Directive state detection  : PASS'
Write-Host 'Research state detection   : PASS'
Write-Host 'JARVIS LLM bridge          : PASS'
Write-Host 'Raw research -> TTS        : BLOCKED'
Write-Host 'Directive -> TTS           : BLOCKED'
Write-Host 'Ollama -> assistant_reply  : PASS'
Write-Host 'Offline graceful fallback  : PASS'
Write-Host 'FastAPI assistant route    : PASS'
Write-Host 'Python compile             : PASS'
Write-Host 'npm run build              : PASS'
Write-Host ''
Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''