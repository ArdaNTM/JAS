# ============================================================
# AURA V6.5.3
# JARVIS LOCAL LLM BRIDGE
# ROBUST FASTAPI APP / ROUTER DISCOVERY
# OLLAMA GRACEFUL DEGRADATION
#
# PowerShell 5.1
#
# Bu sürüm:
# - APIRouter() bulunamadı diye abort etmez.
# - FastAPI() instance'ını arar.
# - @app.get/@app.post/@router.get/@router.post decorator
#   hedeflerini analiz eder.
# - api.py içinde mevcut route target varsa onu kullanır.
# - Router yok ama FastAPI app varsa doğrudan app'e ekler.
# - api.py yalnızca APIRouter içeriyorsa router'a ekler.
# - Hiçbir uygun target yoksa ana FastAPI modülünü arar.
# - /api/assistant/respond route'unu duplicate etmez.
# - Ollama bağlantı hatasını 502'ye dönüştürmez.
# - Ham research/directive verisini frontend TTS'e göndermez.
# - App.tsx JSX injection için lexer tabanlı root discovery kullanır.
# - Build başarısızsa App.tsx ve api.py rollback edilir.
# ============================================================

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root = 'D:\AURA\JAS'
$UiRoot = Join-Path $Root 'aura-ui'
$CoreRoot = Join-Path $Root 'core'
$CoreSrc = Join-Path $CoreRoot 'src'
$AppPath = Join-Path $UiRoot 'src\App.tsx'
$BridgePath = Join-Path $UiRoot 'src\AuraJarvisBridge.tsx'

$ApplicationRoot =
    Join-Path `
        $CoreSrc `
        'aura_core\application'

$ApiPath =
    Join-Path `
        $ApplicationRoot `
        'api.py'

$BackupRoot =
    Join-Path `
        $Root `
        '.aura-backups'

$Stamp =
    Get-Date `
        -Format 'yyyyMMdd-HHmmss'

$BackupDir =
    Join-Path `
        $BackupRoot `
        ('research-v653-' + $Stamp)

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param(
        [string]$Message
    )

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.3 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Label
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Path `
                -PathType Leaf
        )
    ) {
        Fail (
            $Label +
            ' bulunamadı: ' +
            $Path
        )
    }
}

function Assert-Directory {
    param(
        [string]$Path,
        [string]$Label
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Path `
                -PathType Container
        )
    ) {
        Fail (
            $Label +
            ' bulunamadı: ' +
            $Path
        )
    }
}

function Read-Utf8Text {
    param(
        [string]$Path
    )

    Assert-File $Path 'Dosya'

    $value =
        [System.IO.File]::ReadAllText(
            $Path,
            [System.Text.Encoding]::UTF8
        )

    if ($null -eq $value) {
        Fail (
            'Dosya okunamadı: ' +
            $Path
        )
    }

    if ($value.Trim().Length -eq 0) {
        Fail (
            'Dosya boş: ' +
            $Path
        )
    }

    return $value
}

function Write-Utf8Text {
    param(
        [string]$Path,
        [string]$Text
    )

    if ($null -eq $Text) {
        Fail (
            'Boş içerik yazılamaz: ' +
            $Path
        )
    }

    $parent =
        Split-Path `
            $Path `
            -Parent

    New-Item `
        -ItemType Directory `
        -Path $parent `
        -Force |
        Out-Null

    $encoding =
        New-Object `
            System.Text.UTF8Encoding(
                $false
            )

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

    $destination =
        Join-Path `
            $BackupDir `
            $Relative

    $parent =
        Split-Path `
            $destination `
            -Parent

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

        $start =
            $Text.IndexOf(
                $StartMarker,
                [System.StringComparison]::Ordinal
            )

        if ($start -lt 0) {
            break
        }

        $end =
            $Text.IndexOf(
                $EndMarker,
                $start,
                [System.StringComparison]::Ordinal
            )

        if ($end -lt 0) {
            Fail (
                'Generated block END marker bulunamadı: ' +
                $StartMarker
            )
        }

        $end =
            $end +
            $EndMarker.Length

        $Text =
            $Text.Remove(
                $start,
                $end - $start
            )
    }

    return $Text
}

# ============================================================
# JSX DISCOVERY
# ============================================================

function Find-AppOpenBrace {
    param(
        [string]$Text
    )

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*function\s+App\s*\([^)]*\)\s*\{'
    )

    foreach ($pattern in $patterns) {

        $match =
            [regex]::Match(
                $Text,
                $pattern
            )

        if ($match.Success) {

            return (
                $match.Index +
                $match.Length -
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

    $tail =
        $Text.Substring(
            $AppOpenBrace + 1
        )

    $match =
        [regex]::Match(
            $tail,
            '(?s)\breturn\b\s*(?:/\*.*?\*/\s*)*(?://[^\r\n]*\r?\n\s*)*\('
        )

    if (-not $match.Success) {
        return -1
    }

    $local =
        $match.Value.LastIndexOf(
            '('
        )

    if ($local -lt 0) {
        return -1
    }

    return (
        $AppOpenBrace +
        1 +
        $match.Index +
        $local
    )
}

function Find-JsxFirstToken {
    param(
        [string]$Text,
        [int]$Start
    )

    if (
        $Start -lt 0 -or
        $Start -ge $Text.Length
    ) {
        return -1
    }

    $i = $Start

    $single = $false
    $double = $false
    $template = $false
    $lineComment = $false
    $blockComment = $false

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if ($lineComment) {

            if (
                $c -eq "`r" -or
                $c -eq "`n"
            ) {
                $lineComment = $false
            }

            $i++
            continue
        }

        if ($blockComment) {

            if (
                $c -eq '*' -and
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq '/'
            ) {
                $blockComment = $false
                $i += 2
                continue
            }

            $i++
            continue
        }

        if ($single) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq "'") {
                $single = $false
            }

            $i++
            continue
        }

        if ($double) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq '"') {
                $double = $false
            }

            $i++
            continue
        }

        if ($template) {

            if (
                $c -eq '\' -and
                ($i + 1) -lt $Text.Length
            ) {
                $i += 2
                continue
            }

            if ($c -eq '`') {
                $template = $false
            }

            $i++
            continue
        }

        if (
            $c -eq '/' -and
            ($i + 1) -lt $Text.Length
        ) {

            if ($Text[$i + 1] -eq '/') {
                $lineComment = $true
                $i += 2
                continue
            }

            if ($Text[$i + 1] -eq '*') {
                $blockComment = $true
                $i += 2
                continue
            }
        }

        if ($c -eq "'") {
            $single = $true
            $i++
            continue
        }

        if ($c -eq '"') {
            $double = $true
            $i++
            continue
        }

        if ($c -eq '`') {
            $template = $true
            $i++
            continue
        }

        if ($c -eq '<') {

            if (
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq '>'
            ) {
                return $i
            }

            if (
                ($i + 1) -lt $Text.Length -and
                (
                    [char]::IsLetter(
                        $Text[$i + 1]
                    ) -or
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

# ============================================================
# REACT HELPERS
# ============================================================

function Ensure-ReactImports {
    param(
        [string]$Text
    )

    $required = @(
        'useEffect',
        'useRef',
        'useState'
    )

    $match =
        [regex]::Match(
            $Text,
            '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
        )

    if ($match.Success) {

        $items =
            New-Object `
                System.Collections.Generic.List[string]

        foreach (
            $item in
            ($match.Groups['body'].Value -split ',')
        ) {

            $name =
                $item.Trim()

            if (
                $name.Length -gt 0 -and
                -not $items.Contains($name)
            ) {
                [void]$items.Add($name)
            }
        }

        foreach ($name in $required) {

            if (-not $items.Contains($name)) {
                [void]$items.Add($name)
            }
        }

        $replacement =
            'import { ' +
            ($items -join ', ') +
            ' } from "react";'

        return (
            $Text.Remove(
                $match.Index,
                $match.Length
            ).Insert(
                $match.Index,
                $replacement
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

        $match =
            [regex]::Match(
                $Text,
                $pattern
            )

        if ($match.Success) {

            return [PSCustomObject]@{
                Value = $name
                Setter = $match.Groups['setter'].Value
            }
        }
    }

    return $null
}

function Ensure-ResearchState {
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
        @'
    const [researchOutput, setResearchOutput] = useState<unknown>(null);
'@

    return (
        $Text.Insert(
            $AppOpenBrace + 1,
            "`r`n" +
            $state.TrimEnd() +
            "`r`n"
        )
    )
}

# ============================================================
# FASTAPI DISCOVERY
# ============================================================

function Find-FastApiInstance {
    param(
        [string]$Text
    )

    #
    # app = FastAPI(...)
    # application = FastAPI(...)
    # api = fastapi.FastAPI(...)
    # api_app: FastAPI = FastAPI(...)
    #
    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*FastAPI\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.FastAPI\s*\('
    )

    foreach ($pattern in $patterns) {

        $match =
            [regex]::Match(
                $Text,
                $pattern
            )

        if ($match.Success) {
            return $match.Groups['name'].Value
        }
    }

    return $null
}

function Find-ApiRouterInstance {
    param(
        [string]$Text
    )

    #
    # router = APIRouter(...)
    # api_router = APIRouter(...)
    # router: APIRouter = APIRouter(...)
    # router = fastapi.APIRouter(...)
    #
    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*APIRouter\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.APIRouter\s*\('
    )

    foreach ($pattern in $patterns) {

        $match =
            [regex]::Match(
                $Text,
                $pattern
            )

        if ($match.Success) {
            return $match.Groups['name'].Value
        }
    }

    return $null
}

function Find-DecoratorTargets {
    param(
        [string]$Text
    )

    $targets =
        New-Object `
            System.Collections.Generic.List[string]

    $matches =
        [regex]::Matches(
            $Text,
            '(?m)^\s*@(?<target>[A-Za-z_]\w*)\.(?:get|post|put|delete|patch|options|head|trace|api_route)\s*\('
        )

    foreach ($match in $matches) {

        $name =
            $match.Groups['target'].Value

        if (
            -not $targets.Contains(
                $name
            )
        ) {
            [void]$targets.Add(
                $name
            )
        }
    }

    return $targets
}

function Find-ExistingAssistantRoute {
    param(
        [string]$Text
    )

    $match =
        [regex]::Match(
            $Text,
            '(?s)@\s*(?<target>[A-Za-z_]\w*)\s*\.\s*(?:post|api_route)\s*\(\s*["'']\/api\/assistant\/respond["''].*?(?:^|\n)\s*(?:async\s+)?def\s+(?<fn>[A-Za-z_]\w*)'
    )

    if ($match.Success) {

        return [PSCustomObject]@{
            Target =
                $match.Groups['target'].Value

            Function =
                $match.Groups['fn'].Value
        }
    }

    return $null
}

function Find-BackendCandidateFiles {
    param(
        [string]$Directory
    )

    $files =
        Get-ChildItem `
            -LiteralPath $Directory `
            -Recurse `
            -File `
            -Filter '*.py' |
        Where-Object {
            $_.FullName -notmatch '\\__pycache__\\'
        }

    $results =
        New-Object `
            System.Collections.Generic.List[object]

    foreach ($file in $files) {

        try {

            $text =
                [System.IO.File]::ReadAllText(
                    $file.FullName,
                    [System.Text.Encoding]::UTF8
                )

            if (
                $text -match '\bFastAPI\s*\(' -or
                $text -match '\bAPIRouter\s*\(' -or
                $text -match '@[A-Za-z_]\w*\.(?:get|post|put|delete|patch|api_route)\s*\('
            ) {

                $score = 0

                if (
                    $text -match '\bFastAPI\s*\('
                ) {
                    $score += 1000
                }

                if (
                    $text -match '\bAPIRouter\s*\('
                ) {
                    $score += 500
                }

                if (
                    $text -match '/api/tasks'
                ) {
                    $score += 300
                }

                if (
                    $text -match '/api/assistant'
                ) {
                    $score += 300
                }

                if (
                    $text -match 'TaskResponse'
                ) {
                    $score += 100
                }

                [void]$results.Add(
                    [PSCustomObject]@{
                        Path = $file.FullName
                        Score = $score
                    }
                )
            }
        }
        catch {
            # Okunamayan dosyayı discovery dışında bırak.
        }
    }

    return (
        $results |
        Sort-Object `
            -Property Score `
            -Descending
    )
}

function Find-MainFastApiFile {
    param(
        [string]$Directory
    )

    $candidates =
        Find-BackendCandidateFiles `
            -Directory $Directory

    foreach ($candidate in $candidates) {

        $text =
            Read-Utf8Text `
                $candidate.Path

        $app =
            Find-FastApiInstance `
                $text

        if ($null -ne $app) {

            return [PSCustomObject]@{
                Path = $candidate.Path
                Instance = $app
            }
        }
    }

    return $null
}

# ============================================================
# PYTHON IMPORTS
# ============================================================

function Ensure-PythonImport {
    param(
        [string]$Text,
        [string]$Line
    )

    if (
        [regex]::IsMatch(
            $Text,
            '(?m)^' +
            [regex]::Escape($Line) +
            '\s*$'
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

# ============================================================
# ASSISTANT ROUTE
# ============================================================

function Build-AssistantRoute {
    param(
        [string]$Target
    )

    $route = @'
# AURA_JARVIS_ASSISTANT_API_V653_START

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
                "ince ironik ol. Kullanıcının direktifini tekrar "
                "etme. Ham JSON, UUID, URL, tool trace veya "
                "teknik log okuma. Araştırma verisini analiz et "
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
                "Bu veriyi analiz et ve doğal, konuşmaya uygun "
                "bir AURA yanıtı üret."
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


@TARGET.post(
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

    except Exception:

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

# AURA_JARVIS_ASSISTANT_API_V653_END
'@

    return (
        $route.Replace(
            '@TARGET',
            '@' + $Target
        )
    )
}

function Add-AssistantRouteToModule {
    param(
        [string]$Text,
        [string]$Target
    )

    $existing =
        Find-ExistingAssistantRoute `
            -Text $Text

    if ($null -ne $existing) {

        return [PSCustomObject]@{
            Text = $Text
            Added = $false
            Target = $existing.Target
            Function = $existing.Function
        }
    }

    $Text =
        Remove-GeneratedBlock `
            -Text $Text `
            -StartMarker 'AURA_JARVIS_ASSISTANT_API_V652_START' `
            -EndMarker 'AURA_JARVIS_ASSISTANT_API_V652_END'

    $Text =
        Remove-GeneratedBlock `
            -Text $Text `
            -StartMarker 'AURA_JARVIS_ASSISTANT_API_V651_START' `
            -EndMarker 'AURA_JARVIS_ASSISTANT_API_V651_END'

    $Text =
        Remove-GeneratedBlock `
            -Text $Text `
            -StartMarker 'AURA_JARVIS_ASSISTANT_API_V65_START' `
            -EndMarker 'AURA_JARVIS_ASSISTANT_API_V65_END'

    $route =
        Build-AssistantRoute `
            -Target $Target

    return [PSCustomObject]@{
        Text =
            $Text.TrimEnd() +
            "`r`n`r`n" +
            $route.Trim() +
            "`r`n"

        Added = $true
        Target = $Target
        Function = 'aura_assistant_respond'
    }
}

# ============================================================
# ROUTER INCLUDE DISCOVERY
# ============================================================

function Ensure-RouterIncludedInApp {
    param(
        [string]$AppText,
        [string]$RouterName,
        [string]$ModuleImport
    )

    $includePattern =
        '(?m)^\s*' +
        [regex]::Escape($AppText) +
        '\.include_router'

    if (
        $AppText.IndexOf(
            '.include_router(',
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        return $AppText
    }

    #
    # Burada yeni include_router tahmini yapılmıyor.
    # Mevcut main app'te include_router mekanizması yoksa,
    # module-level APIRouter'ın otomatik olarak yayınlanacağını
    # varsaymak güvenli değildir.
    #
    # Bunun yerine çağıran fonksiyon bunu explicit olarak raporlar.
    #

    return $AppText
}

# ============================================================
# BACKEND ROUTE STRATEGY
# ============================================================

function Patch-Backend {
    param(
        [string]$PreferredApiPath
    )

    $apiText =
        Read-Utf8Text `
            $PreferredApiPath

    #
    # 1. Zaten assistant route varsa onu kullan.
    #

    $existing =
        Find-ExistingAssistantRoute `
            -Text $apiText

    if ($null -ne $existing) {

        Write-Host (
            '    Mevcut assistant route bulundu: @' +
            $existing.Target
        )

        $apiText =
            Remove-GeneratedBlock `
                -Text $apiText `
                -StartMarker 'AURA_JARVIS_ASSISTANT_API_V652_START' `
                -EndMarker 'AURA_JARVIS_ASSISTANT_API_V653_END'

        #
        # Mevcut route'u bozma.
        # Yalnızca gerçekten V6 generated ise yeniden üret.
        #
        if (
            $apiText.IndexOf(
                'AURA_JARVIS_ASSISTANT_API_V652_START',
                [System.StringComparison]::Ordinal
            ) -ge 0
        ) {

            $apiText =
                Remove-GeneratedBlock `
                    -Text $apiText `
                    -StartMarker 'AURA_JARVIS_ASSISTANT_API_V652_START' `
                    -EndMarker 'AURA_JARVIS_ASSISTANT_API_V652_END'

            $result =
                Add-AssistantRouteToModule `
                    -Text $apiText `
                    -Target $existing.Target

            Write-Utf8Text `
                -Path $PreferredApiPath `
                -Text $result.Text

            return [PSCustomObject]@{
                Path = $PreferredApiPath
                Target = $result.Target
                Added = $result.Added
            }
        }

        #
        # Kullanıcının mevcut route'u varsa duplicate oluşturma.
        #
        Write-Host '    Mevcut /api/assistant/respond korunuyor.'

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $existing.Target
            Added = $false
        }
    }

    #
    # 2. api.py içinde FastAPI instance.
    #

    $fastApi =
        Find-FastApiInstance `
            -Text $apiText

    if ($null -ne $fastApi) {

        Write-Host (
            '    FastAPI instance bulundu: ' +
            $fastApi
        )

        $result =
            Add-AssistantRouteToModule `
                -Text $apiText `
                -Target $fastApi

        Write-Utf8Text `
            -Path $PreferredApiPath `
            -Text $result.Text

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $fastApi
            Added = $result.Added
        }
    }

    #
    # 3. api.py içinde APIRouter.
    #

    $router =
        Find-ApiRouterInstance `
            -Text $apiText

    if ($null -ne $router) {

        Write-Host (
            '    APIRouter instance bulundu: ' +
            $router
        )

        $result =
            Add-AssistantRouteToModule `
                -Text $apiText `
                -Target $router

        Write-Utf8Text `
            -Path $PreferredApiPath `
            -Text $result.Text

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $router
            Added = $result.Added
        }
    }

    #
    # 4. api.py içindeki mevcut decorator target.
    #
    # Örn:
    # @api.post(...)
    # @tasks_router.post(...)
    #

    $targets =
        Find-DecoratorTargets `
            -Text $apiText

    if ($targets.Count -gt 0) {

        $selected =
            $targets[0]

        Write-Host (
            '    Decorator target bulundu: ' +
            $selected
        )

        $result =
            Add-AssistantRouteToModule `
                -Text $apiText `
                -Target $selected

        Write-Utf8Text `
            -Path $PreferredApiPath `
            -Text $result.Text

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $selected
            Added = $result.Added
        }
    }

    #
    # 5. api.py uygun değil.
    # Main FastAPI modülünü otomatik keşfet.
    #

    Write-Host '    api.py FastAPI target içermiyor; backend discovery başlıyor...'

    $main =
        Find-MainFastApiFile `
            -Directory $CoreSrc

    if ($null -eq $main) {

        Fail (
            'FastAPI instance, APIRouter veya mevcut decorator target ' +
            'hiçbir backend modülünde bulunamadı. ' +
            'Dosya tahminiyle route eklenmedi.'
        )
    }

    Write-Host (
        '    Ana FastAPI modülü: ' +
        $main.Path
    )

    $mainText =
        Read-Utf8Text `
            $main.Path

    $mainResult =
        Add-AssistantRouteToModule `
            -Text $mainText `
            -Target $main.Instance

    Write-Utf8Text `
        -Path $main.Path `
        -Text $mainResult.Text

    return [PSCustomObject]@{
        Path = $main.Path
        Target = $main.Instance
        Added = $mainResult.Added
    }
}

# ============================================================
# START
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.3 JARVIS / ROBUST FASTAPI PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/12] Proje kontrol ediliyor...'

Assert-Directory $Root 'AURA root'
Assert-Directory $UiRoot 'aura-ui'
Assert-Directory $CoreRoot 'core'
Assert-Directory $CoreSrc 'core src'

Assert-File $AppPath 'App.tsx'
Assert-File $ApiPath 'api.py'

# ============================================================

Write-Host '[2/12] Güvenli backup oluşturuluyor...'

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

# ============================================================

Write-Host '[3/12] App.tsx okunuyor...'

$app =
    Read-Utf8Text `
        $AppPath

# ============================================================

Write-Host '[4/12] Eski V6 generated blokları temizleniyor...'

foreach (
    $pair in @(
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
            'AURA_RESEARCH_CONVERSATIONAL_V63_START',
            'AURA_RESEARCH_CONVERSATIONAL_V63_END'
        )
    )
) {

    $app =
        Remove-GeneratedBlock `
            -Text $app `
            -StartMarker $pair[0] `
            -EndMarker $pair[1]
}

#
# Eski hardcoded helper.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\bfunction\s+buildAssistantReply\s*\([^)]*\)\s*\{.*?\n\}',
        ''
    )

#
# Statik persona kalıntıları.
#

$app =
    [regex]::Replace(
        $app,
        'Elbette[,.]?\s*Araştırmayı tamamladım\.?',
        ''
    )

$app =
    [regex]::Replace(
        $app,
        'Araştırmayı tamamladım\.?',
        ''
    )

# ============================================================

Write-Host '[5/12] React importleri ve state hazırlanıyor...'

$app =
    Ensure-ReactImports `
        $app

$appOpen =
    Find-AppOpenBrace `
        $app

if ($appOpen -lt 0) {
    Fail 'export default function App(...) bulunamadı.'
}

$app =
    Ensure-ResearchState `
        -Text $app `
        -AppOpenBrace $appOpen

$appOpen =
    Find-AppOpenBrace `
        $app

$directiveState =
    Find-StateSetter `
        -Text $app `
        -Names @(
            'directive',
            'command',
            'input',
            'query',
            'userInput',
            'prompt',
            'text'
        )

if ($null -eq $directiveState) {
    Fail 'Directive state otomatik bulunamadı.'
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

Write-Host (
    '    Directive state : ' +
    $directiveState.Value
)

Write-Host (
    '    Research state  : ' +
    $researchState.Value
)

# ============================================================

Write-Host '[6/12] AuraJarvisBridge oluşturuluyor...'

$bridge = @'
/* AURA_JARVIS_LLM_V652_START */

import {
    useEffect,
    useRef,
    useState,
} from "react";

type Props = {
    directive?: unknown;
    researchOutput?: unknown;
};

type AssistantResponse = {
    assistant_reply?: unknown;
    model?: unknown;
    provider?: unknown;
};

function cleanReply(
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

async function requestAssistantReply(
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
        ) as AssistantResponse;

    return cleanReply(
        data.assistant_reply
    );
}

function speakAssistantReply(
    reply: string
): void {

    const text =
        cleanReply(reply);

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
                (chunk) => chunk.trim()
            )
            .filter(Boolean)
            ?? [];

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

            const utterance =
                queue.shift();

            if (!utterance) {
                return;
            }

            utterance.onend =
                speakNext;

            utterance.onerror =
                speakNext;

            window.speechSynthesis.speak(
                utterance
            );
        };

    speakNext();
}

export default function AuraJarvisBridge(
    {
        directive,
        researchOutput,
    }: Props
) {

    const [
        reply,
        setReply,
    ] = useState<string>("");

    const [
        thinking,
        setThinking,
    ] = useState<boolean>(false);

    const generation =
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

            const id =
                generation.current + 1;

            generation.current =
                id;

            let cancelled =
                false;

            setThinking(true);

            requestAssistantReply(
                directive,
                researchOutput
            )
                .then(
                    (assistantReply) => {

                        if (
                            cancelled ||
                            generation.current !== id
                        ) {
                            return;
                        }

                        const clean =
                            cleanReply(
                                assistantReply
                            );

                        setReply(
                            clean
                        );

                        /*
                         * TTS yalnızca LLM'in
                         * assistant_reply değerini alır.
                         *
                         * researchOutput -> TTS YOK
                         * directive      -> TTS YOK
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
                                "AURA JARVIS bridge:",
                                error
                            );

                            setReply(
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
        !reply
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
                        : reply
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

Write-Host '[7/12] AuraJarvisBridge App JSX içine ekleniyor...'

$import =
    'import AuraJarvisBridge from "./AuraJarvisBridge";'

if (
    $app.IndexOf(
        $import,
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $app =
        $import +
        "`r`n" +
        $app
}

$appOpen =
    Find-AppOpenBrace `
        $app

$returnParen =
    Find-AppReturnOpenParen `
        -Text $app `
        -AppOpenBrace $appOpen

if ($returnParen -lt 0) {
    Fail 'App return(...) bulunamadı.'
}

$jsx =
    Find-JsxFirstToken `
        -Text $app `
        -Start ($returnParen + 1)

if ($jsx -lt 0) {
    Fail 'App return(...) içinde JSX root bulunamadı.'
}

if (
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $nextTwo =
        $app.Substring(
            $jsx,
            [Math]::Min(
                2,
                $app.Length - $jsx
            )
        )

    if ($nextTwo -eq '<>') {

        $position =
            $jsx + 2
    }
    else {

        $rootEnd =
            $app.IndexOf(
                '>',
                $jsx
            )

        if ($rootEnd -lt 0) {
            Fail 'JSX root açılış etiketi tamamlanamadı.'
        }

        if (
            $app[$rootEnd - 1] -eq '/'
        ) {
            Fail 'JSX root self-closing olduğu için injection güvenli değil.'
        }

        $position =
            $rootEnd + 1
    }

    $bridgeMarkup =
        @"
        <AuraJarvisBridge
            directive={$($directiveState.Value)}
            researchOutput={$($researchState.Value)}
        />
"@

    $app =
        $app.Insert(
            $position,
            "`r`n" +
            $bridgeMarkup.TrimEnd() +
            "`r`n"
        )
}

# ============================================================

Write-Host '[8/12] App.tsx yazılıyor...'

Write-Utf8Text `
    -Path $AppPath `
    -Text $app

# ============================================================

Write-Host '[9/12] CSS hazırlanıyor...'

$cssPath = $null

foreach (
    $candidate in @(
        (Join-Path $UiRoot 'src\App.css'),
        (Join-Path $UiRoot 'src\index.css')
    )
) {

    if (
        Test-Path `
            -LiteralPath $candidate `
            -PathType Leaf
    ) {

        $cssPath =
            $candidate

        break
    }
}

if ($null -eq $cssPath) {

    $cssPath =
        Join-Path `
            $UiRoot `
            'src\App.css'

    Write-Utf8Text `
        -Path $cssPath `
        -Text ''
}

$css =
    Read-Utf8Text `
        $cssPath

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
    display: block;
    margin: 0 0 7px 0;
    padding: 0;
    font-size: 10px;
    line-height: 1.2;
    letter-spacing: 0.18em;
    font-weight: 700;
    white-space: nowrap;
}

.aura-jarvis-response-text {
    display: block;
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
    -Path $cssPath `
    -Text $css

# ============================================================

Write-Host '[10/12] FastAPI target dinamik olarak keşfediliyor...'

$backendResult =
    Patch-Backend `
        -PreferredApiPath $ApiPath

Write-Host (
    '    Backend module: ' +
    $backendResult.Path
)

Write-Host (
    '    Route target: @' +
    $backendResult.Target
)

if ($backendResult.Added) {
    Write-Host '    /api/assistant/respond: ADDED'
}
else {
    Write-Host '    /api/assistant/respond: EXISTING'
}

# ============================================================

Write-Host '[11/12] Python structural validation...'

$finalBackend =
    Read-Utf8Text `
        $backendResult.Path

if (
    $finalBackend.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail '/api/assistant/respond route final backend dosyasında bulunamadı.'
}

if (
    $finalBackend.IndexOf(
        'local-offline',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Ollama local-offline fallback bulunamadı.'
}

if (
    $finalBackend.IndexOf(
        'LLM çekirdeğime şu an ulaşamıyorum',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Ollama graceful fallback metni bulunamadı.'
}

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
    $backendResult.Path

if ($LASTEXITCODE -ne 0) {
    Fail 'Python compile başarısız.'
}

# ============================================================

Write-Host '[12/12] TypeScript / Vite build...'

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

$buildCode =
    $LASTEXITCODE

Pop-Location

if ($buildCode -ne 0) {

    Write-Host ''
    Write-Host 'BUILD FAILED - rollback başlatılıyor.' -ForegroundColor Red

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

    $backendBackup =
        Join-Path `
            $BackupDir `
            'core\src\aura_core\application\api.py'

    if (
        Test-Path `
            -LiteralPath $backendBackup `
            -PathType Leaf
    ) {

        Copy-Item `
            -LiteralPath $backendBackup `
            -Destination $ApiPath `
            -Force
    }

    Fail 'npm run build başarısız; App.tsx ve api.py rollback edildi.'
}

# ============================================================
# FINAL CHECKS
# ============================================================

$finalApp =
    Read-Utf8Text `
        $AppPath

$finalBridge =
    Read-Utf8Text `
        $BridgePath

$finalAppOpen =
    Find-AppOpenBrace `
        $finalApp

if ($finalAppOpen -lt 0) {
    Fail 'Final App() bulunamadı.'
}

$finalReturn =
    Find-AppReturnOpenParen `
        -Text $finalApp `
        -AppOpenBrace $finalAppOpen

if ($finalReturn -lt 0) {
    Fail 'Final App return(...) bulunamadı.'
}

$finalJsx =
    Find-JsxFirstToken `
        -Text $finalApp `
        -Start ($finalReturn + 1)

if ($finalJsx -lt 0) {
    Fail 'Final JSX root bulunamadı.'
}

if (
    $finalApp.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge JSX invocation bulunamadı.'
}

if (
    $finalBridge.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Frontend assistant bridge endpoint bulunamadı.'
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
# Direktif veya research verisini TTS'e doğrudan bağlayan
# bilinen kalıpları reddet.
#

foreach (
    $forbidden in @(
        'speakAssistantReply(directive)',
        'speakAssistantReply(researchOutput)',
        'speakAssistantReply(step.result)',
        'speechSynthesis.speak(researchOutput)',
        'speechSynthesis.speak(step.result)',
        'speechSynthesis.speak(directive)'
    )
) {

    if (
        $finalBridge.IndexOf(
            $forbidden,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        Fail (
            'Doğrudan TTS bağlantısı bulundu: ' +
            $forbidden
        )
    }
}

if (
    $finalApp.IndexOf(
        'Elbette. Araştırmayı tamamladım.',
        [System.StringComparison]::OrdinalIgnoreCase
    ) -ge 0
) {
    Fail 'Eski hardcoded assistant reply App.tsx içinde kaldı.'
}

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.3 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App() detection             : PASS'
Write-Host 'return(...) detection       : PASS'
Write-Host 'JSX lexer root              : PASS'
Write-Host 'JARVIS bridge               : PASS'
Write-Host 'Raw research -> TTS         : BLOCKED'
Write-Host 'Directive -> TTS            : BLOCKED'
Write-Host 'FastAPI target discovery    : PASS'
Write-Host 'Assistant endpoint          : PASS'
Write-Host 'Ollama offline fallback     : PASS'
Write-Host 'Python compile              : PASS'
Write-Host 'npm run build               : PASS'
Write-Host ''
Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''