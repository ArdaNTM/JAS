# ============================================================
# AURA V6.5.4
# SAFE JSX FRAGMENT WRAPPER + ROBUST FASTAPI TARGET PATCH
#
# Amaç:
#   1. V6.x generated frontend bloklarını temizlemek
#   2. AuraJarvisBridge'i App() return(...) içine güvenli şekilde
#      Fragment wrapper üzerinden yerleştirmek
#   3. Mevcut JSX root'un içine "rastgele <" token'ı eklememek
#   4. FastAPI target discovery mantığını korumak
#   5. Ollama offline graceful-degradation route'unu korumak
#   6. Build başarısız olursa otomatik rollback yapmak
#
# Önemli:
#   - App.tsx'in mevcut JSX ağacı parse edilmeden ortasına insertion YOK.
#   - return (...) içeriği önce Fragment ile sarılır:
#
#       return (
#         <>
#           ...MEVCUT JSX...
#           <AuraJarvisBridge ... />
#         </>
#       );
#
#   - Mevcut root bir Fragment ise tekrar Fragment eklenmez.
#   - Mevcut root tek JSX elementi ise onun kapanışını bulup component
#     kapanıştan hemen önce eklenir.
#   - Bu yöntem React'in tek root / Fragment kurallarıyla uyumludur.
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
$BackupDir = Join-Path $BackupRoot ('research-v654-' + $Stamp)

# ============================================================
# GENERIC HELPERS
# ============================================================

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.4 PATCH ABORTED' -ForegroundColor Red
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
        Fail ('Yazılacak içerik null: ' + $Path)
    }

    $parent = Split-Path $Path -Parent

    New-Item `
        -ItemType Directory `
        -Path $parent `
        -Force |
        Out-Null

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

function Restore-File {
    param(
        [string]$BackupPath,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $BackupPath -PathType Leaf) {
        Copy-Item `
            -LiteralPath $BackupPath `
            -Destination $Destination `
            -Force
    }
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
                'Generated block END marker bulunamadı: ' +
                $EndMarker
            )
        }

        $end += $EndMarker.Length

        $Text = $Text.Remove(
            $start,
            $end - $start
        )
    }

    return $Text
}

# ============================================================
# APP COMPONENT DISCOVERY
# ============================================================

function Find-AppOpenBrace {
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*function\s+App\s*\([^)]*\)\s*\{'
    )

    foreach ($pattern in $patterns) {

        $match = [regex]::Match(
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

    $tail = $Text.Substring(
        $AppOpenBrace + 1
    )

    $match = [regex]::Match(
        $tail,
        '(?s)\breturn\b\s*(?:/\*.*?\*/\s*)*(?://[^\r\n]*\r?\n\s*)*\('
    )

    if (-not $match.Success) {
        return -1
    }

    $localParen = $match.Value.LastIndexOf('(')

    if ($localParen -lt 0) {
        return -1
    }

    return (
        $AppOpenBrace +
        1 +
        $match.Index +
        $localParen
    )
}

# ============================================================
# JS / JSX LEXICAL SCANNER
#
# Amaç:
#   JSX içinde:
#     strings
#     template literals
#     comments
#     JS expression braces
#     JSX tags
#
# ayrımını yaparak gerçek JSX root sınırlarını bulmak.
# ============================================================

function Skip-JsString {
    param(
        [string]$Text,
        [int]$Start,
        [char]$Quote
    )

    $i = $Start + 1

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if ($c -eq '\') {
            $i += 2
            continue
        }

        if ($c -eq $Quote) {
            return ($i + 1)
        }

        $i++
    }

    return $Text.Length
}

function Skip-LineComment {
    param(
        [string]$Text,
        [int]$Start
    )

    $i = $Start + 2

    while ($i -lt $Text.Length) {

        if (
            $Text[$i] -eq "`r" -or
            $Text[$i] -eq "`n"
        ) {
            return $i
        }

        $i++
    }

    return $Text.Length
}

function Skip-BlockComment {
    param(
        [string]$Text,
        [int]$Start
    )

    $i = $Start + 2

    while (
        ($i + 1) -lt $Text.Length
    ) {

        if (
            $Text[$i] -eq '*' -and
            $Text[$i + 1] -eq '/'
        ) {
            return ($i + 2)
        }

        $i++
    }

    return $Text.Length
}

function Find-JsxTagEnd {
    param(
        [string]$Text,
        [int]$Start
    )

    $i = $Start
    $braceDepth = 0

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if (
            $c -eq "'" -or
            $c -eq '"'
        ) {
            $i = Skip-JsString `
                -Text $Text `
                -Start $i `
                -Quote $c

            continue
        }

        if ($c -eq '`') {

            $i = Skip-JsString `
                -Text $Text `
                -Start $i `
                -Quote $c

            continue
        }

        if (
            $c -eq '/' -and
            ($i + 1) -lt $Text.Length
        ) {

            if ($Text[$i + 1] -eq '/') {

                $i = Skip-LineComment `
                    -Text $Text `
                    -Start $i

                continue
            }

            if ($Text[$i + 1] -eq '*') {

                $i = Skip-BlockComment `
                    -Text $Text `
                    -Start $i

                continue
            }
        }

        if ($c -eq '{') {
            $braceDepth++
            $i++
            continue
        }

        if ($c -eq '}') {

            if ($braceDepth -gt 0) {
                $braceDepth--
                $i++
                continue
            }
        }

        if (
            $c -eq '>' -and
            $braceDepth -eq 0
        ) {
            return $i
        }

        $i++
    }

    return -1
}

function Parse-JsxTag {
    param(
        [string]$Text,
        [int]$Start
    )

    if (
        $Start -lt 0 -or
        $Start -ge $Text.Length -or
        $Text[$Start] -ne '<'
    ) {
        return $null
    }

    #
    # Fragment opening <>
    #

    if (
        ($Start + 1) -lt $Text.Length -and
        $Text[$Start + 1] -eq '>'
    ) {

        return [PSCustomObject]@{
            Kind = 'FragmentOpen'
            Name = ''
            End = $Start + 1
            SelfClosing = $false
        }
    }

    #
    # Fragment closing </>
    #

    if (
        ($Start + 2) -lt $Text.Length -and
        $Text[$Start + 1] -eq '/' -and
        $Text[$Start + 2] -eq '>'
    ) {

        return [PSCustomObject]@{
            Kind = 'FragmentClose'
            Name = ''
            End = $Start + 2
            SelfClosing = $false
        }
    }

    $isClosing = $false
    $i = $Start + 1

    if (
        $i -lt $Text.Length -and
        $Text[$i] -eq '/'
    ) {

        $isClosing = $true
        $i++
    }

    while (
        $i -lt $Text.Length -and
        [char]::IsWhiteSpace($Text[$i])
    ) {
        $i++
    }

    if ($i -ge $Text.Length) {
        return $null
    }

    if (
        -not [char]::IsLetter($Text[$i]) -and
        $Text[$i] -ne '_' -and
        $Text[$i] -ne '$'
    ) {
        return $null
    }

    $nameStart = $i
    $i++

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if (
            [char]::IsLetterOrDigit($c) -or
            $c -eq '_' -or
            $c -eq '$' -or
            $c -eq '.' -or
            $c -eq ':'
        ) {
            $i++
            continue
        }

        break
    }

    $name = $Text.Substring(
        $nameStart,
        $i - $nameStart
    )

    $tagEnd = Find-JsxTagEnd `
        -Text $Text `
        -Start $i

    if ($tagEnd -lt 0) {
        return $null
    }

    $j = $tagEnd - 1

    while (
        $j -ge $Start -and
        [char]::IsWhiteSpace($Text[$j])
    ) {
        $j--
    }

    $selfClosing =
        (
            $j -ge $Start -and
            $Text[$j] -eq '/'
        )

    if ($isClosing) {

        return [PSCustomObject]@{
            Kind = 'Close'
            Name = $name
            End = $tagEnd
            SelfClosing = $false
        }
    }

    return [PSCustomObject]@{
        Kind = 'Open'
        Name = $name
        End = $tagEnd
        SelfClosing = $selfClosing
    }
}

function Find-JsxRootRange {
    param(
        [string]$Text,
        [int]$Start
    )

    $i = $Start

    while ($i -lt $Text.Length) {

        $c = $Text[$i]

        if (
            [char]::IsWhiteSpace($c)
        ) {
            $i++
            continue
        }

        if (
            $c -eq '/' -and
            ($i + 1) -lt $Text.Length
        ) {

            if ($Text[$i + 1] -eq '/') {

                $i = Skip-LineComment `
                    -Text $Text `
                    -Start $i

                continue
            }

            if ($Text[$i + 1] -eq '*') {

                $i = Skip-BlockComment `
                    -Text $Text `
                    -Start $i

                continue
            }
        }

        if ($c -ne '<') {
            $i++
            continue
        }

        $root = Parse-JsxTag `
            -Text $Text `
            -Start $i

        if ($null -eq $root) {
            $i++
            continue
        }

        if ($root.Kind -eq 'FragmentOpen') {

            $depth = 1
            $cursor = $root.End + 1

            while ($cursor -lt $Text.Length) {

                if ($Text[$cursor] -ne '<') {
                    $cursor++
                    continue
                }

                $tag = Parse-JsxTag `
                    -Text $Text `
                    -Start $cursor

                if ($null -eq $tag) {
                    $cursor++
                    continue
                }

                if ($tag.Kind -eq 'FragmentOpen') {

                    if (-not $tag.SelfClosing) {
                        $depth++
                    }

                    $cursor = $tag.End + 1
                    continue
                }

                if ($tag.Kind -eq 'FragmentClose') {

                    $depth--

                    if ($depth -eq 0) {

                        return [PSCustomObject]@{
                            OpenStart = $i
                            OpenEnd = $root.End
                            CloseStart = $cursor
                            CloseEnd = $tag.End
                            Kind = 'Fragment'
                            Name = ''
                        }
                    }

                    $cursor = $tag.End + 1
                    continue
                }

                $cursor = $tag.End + 1
            }

            return $null
        }

        if (
            $root.Kind -eq 'Open' -and
            $root.SelfClosing
        ) {

            return [PSCustomObject]@{
                OpenStart = $i
                OpenEnd = $root.End
                CloseStart = $i
                CloseEnd = $root.End
                Kind = 'SelfClosing'
                Name = $root.Name
            }
        }

        if ($root.Kind -ne 'Open') {
            return $null
        }

        $stack =
            New-Object `
                System.Collections.Generic.List[string]

        [void]$stack.Add(
            $root.Name
        )

        $cursor = $root.End + 1

        while ($cursor -lt $Text.Length) {

            if ($Text[$cursor] -ne '<') {
                $cursor++
                continue
            }

            $tag = Parse-JsxTag `
                -Text $Text `
                -Start $cursor

            if ($null -eq $tag) {
                $cursor++
                continue
            }

            if (
                $tag.Kind -eq 'Open' -and
                -not $tag.SelfClosing
            ) {

                [void]$stack.Add(
                    $tag.Name
                )

                $cursor =
                    $tag.End + 1

                continue
            }

            if ($tag.Kind -eq 'Close') {

                if ($stack.Count -eq 0) {
                    return $null
                }

                $expected =
                    $stack[$stack.Count - 1]

                if (
                    $expected -ne $tag.Name
                ) {
                    return $null
                }

                $stack.RemoveAt(
                    $stack.Count - 1
                )

                if ($stack.Count -eq 0) {

                    return [PSCustomObject]@{
                        OpenStart = $i
                        OpenEnd = $root.End
                        CloseStart = $cursor
                        CloseEnd = $tag.End
                        Kind = 'Element'
                        Name = $root.Name
                    }
                }
            }

            $cursor =
                $tag.End + 1
        }

        return $null
    }

    return $null
}

# ============================================================
# REACT IMPORT / STATE
# ============================================================

function Ensure-ReactImports {
    param([string]$Text)

    $match = [regex]::Match(
        $Text,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
    )

    $required = @(
        'useEffect',
        'useRef',
        'useState'
    )

    if ($match.Success) {

        $items =
            New-Object `
                System.Collections.Generic.List[string]

        foreach (
            $item in
            ($match.Groups['body'].Value -split ',')
        ) {

            $name = $item.Trim()

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

        $match = [regex]::Match(
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

    $state = @'
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
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*FastAPI\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.FastAPI\s*\('
    )

    foreach ($pattern in $patterns) {

        $match = [regex]::Match(
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
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*APIRouter\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.APIRouter\s*\('
    )

    foreach ($pattern in $patterns) {

        $match = [regex]::Match(
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
    param([string]$Text)

    $targets =
        New-Object `
            System.Collections.Generic.List[string]

    $matches = [regex]::Matches(
        $Text,
        '(?m)^\s*@(?<target>[A-Za-z_]\w*)\.(?:get|post|put|delete|patch|options|head|trace|api_route)\s*\('
    )

    foreach ($match in $matches) {

        $name =
            $match.Groups['target'].Value

        if (-not $targets.Contains($name)) {
            [void]$targets.Add($name)
        }
    }

    return $targets
}

function Find-ExistingAssistantRoute {
    param([string]$Text)

    $pattern = @'
(?s)@\s*(?<target>[A-Za-z_]\w*)\s*\.\s*(?:post|api_route)\s*\(\s*["'']/api/assistant/respond["''].*?(?:\r?\n)\s*(?:async\s+)?def\s+(?<fn>[A-Za-z_]\w*)
'@

    $match = [regex]::Match(
        $Text,
        $pattern
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
    param([string]$Directory)

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

                if ($text -match '\bFastAPI\s*\(') {
                    $score += 1000
                }

                if ($text -match '\bAPIRouter\s*\(') {
                    $score += 500
                }

                if ($text -match '/api/tasks') {
                    $score += 300
                }

                if ($text -match '/api/assistant') {
                    $score += 300
                }

                if ($text -match 'TaskResponse') {
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
            # Discovery dışı.
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
    param([string]$Directory)

    $candidates =
        Find-BackendCandidateFiles `
            -Directory $Directory

    foreach ($candidate in $candidates) {

        $text =
            Read-Utf8Text `
                $candidate.Path

        $app =
            Find-FastApiInstance `
                -Text $text

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
# FASTAPI ROUTE GENERATOR
# ============================================================

function Build-AssistantRoute {
    param([string]$Target)

    #
    # Burada PowerShell double-quoted regex/string yok.
    # Python kodu literal here-string olarak tutuluyor.
    #

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
        }
    }

    foreach (
        $version in @(
            'V651',
            'V652',
            'V653',
            'V654'
        )
    ) {

        $Text =
            Remove-GeneratedBlock `
                -Text $Text `
                -StartMarker (
                    'AURA_JARVIS_ASSISTANT_API_' +
                    $version +
                    '_START'
                ) `
                -EndMarker (
                    'AURA_JARVIS_ASSISTANT_API_' +
                    $version +
                    '_END'
                )
    }

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
    }
}

function Patch-Backend {
    param([string]$PreferredApiPath)

    $apiText =
        Read-Utf8Text `
            $PreferredApiPath

    $existing =
        Find-ExistingAssistantRoute `
            -Text $apiText

    if ($null -ne $existing) {

        Write-Host (
            '    Existing route: @' +
            $existing.Target
        )

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $existing.Target
            Added = $false
        }
    }

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
            Target = $result.Target
            Added = $result.Added
        }
    }

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
            Target = $result.Target
            Added = $result.Added
        }
    }

    $targets =
        Find-DecoratorTargets `
            -Text $apiText

    if ($targets.Count -gt 0) {

        $target =
            $targets[0]

        Write-Host (
            '    Decorator target bulundu: ' +
            $target
        )

        $result =
            Add-AssistantRouteToModule `
                -Text $apiText `
                -Target $target

        Write-Utf8Text `
            -Path $PreferredApiPath `
            -Text $result.Text

        return [PSCustomObject]@{
            Path = $PreferredApiPath
            Target = $target
            Added = $result.Added
        }
    }

    Write-Host (
        '    ' +
        $PreferredApiPath +
        ' uygun target içermiyor; backend discovery...'
    )

    $main =
        Find-MainFastApiFile `
            -Directory $CoreSrc

    if ($null -eq $main) {

        Fail (
            'Backend içinde FastAPI() / APIRouter() / route target bulunamadı.'
        )
    }

    Write-Host (
        '    Ana FastAPI module: ' +
        $main.Path
    )

    $mainText =
        Read-Utf8Text `
            $main.Path

    $result =
        Add-AssistantRouteToModule `
            -Text $mainText `
            -Target $main.Instance

    Write-Utf8Text `
        -Path $main.Path `
        -Text $result.Text

    return [PSCustomObject]@{
        Path = $main.Path
        Target = $result.Target
        Added = $result.Added
    }
}

# ============================================================
# START
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.4 JARVIS / SAFE JSX PATCH'
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

Write-Host '[4/12] Eski generated V6.x blokları temizleniyor...'

$generatedPairs = @(
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

foreach ($pair in $generatedPairs) {

    $app =
        Remove-GeneratedBlock `
            -Text $app `
            -StartMarker $pair[0] `
            -EndMarker $pair[1]
}

#
# Eski hardcoded helper'ı temizle.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\bfunction\s+buildAssistantReply\s*\([^)]*\)\s*\{.*?\n\}',
        ''
    )

#
# Bilinen V6 hardcoded persona metinlerini kaldır.
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
    Fail 'Directive state bulunamadı.'
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
    Fail 'Research output state bulunamadı.'
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
/* AURA_JARVIS_LLM_V654_START */

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

    } catch {

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

                utterance.lang = "tr-TR";
                utterance.rate = 0.96;
                utterance.pitch = 0.94;
                utterance.volume = 1;

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

                        setReply(clean);

                        /*
                         * Yalnızca LLM assistant_reply
                         * TTS'e gider.
                         *
                         * directive      -> TTS YOK
                         * researchOutput -> TTS YOK
                         * step.result    -> TTS YOK
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

                            setReply("");
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

/* AURA_JARVIS_LLM_V654_END */
'@

Write-Utf8Text `
    -Path $BridgePath `
    -Text $bridge

# ============================================================

Write-Host '[7/12] JSX return(...) Fragment wrapper hazırlanıyor...'

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

$root =
    Find-JsxRootRange `
        -Text $app `
        -Start ($returnParen + 1)

if ($null -eq $root) {
    Fail 'App return(...) içindeki gerçek JSX root parse edilemedi.'
}

Write-Host (
    '    JSX root kind : ' +
    $root.Kind
)

Write-Host (
    '    JSX root name : ' +
    $root.Name
)

#
# Önceki V6.5.x component invocation kalıntısı varsa
# tekrar ekleme.
#

if (
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $bridgeMarkup = @"
        <AuraJarvisBridge
            directive={$($directiveState.Value)}
            researchOutput={$($researchState.Value)}
        />
"@

    if ($root.Kind -eq 'Fragment') {

        #
        # Mevcut Fragment zaten tek root.
        # Kapanış </> öncesine component eklenir.
        #

        $insertAt =
            $root.CloseStart

        $app =
            $app.Insert(
                $insertAt,
                "`r`n" +
                $bridgeMarkup.TrimEnd() +
                "`r`n"
            )
    }
    elseif ($root.Kind -eq 'Element') {

        #
        # Mevcut root element korunur.
        # Component root elementin kapanışından önce eklenir.
        #

        $insertAt =
            $root.CloseStart

        $app =
            $app.Insert(
                $insertAt,
                "`r`n" +
                $bridgeMarkup.TrimEnd() +
                "`r`n"
            )
    }
    else {

        Fail (
            'JSX root self-closing. Güvenli child injection mümkün değil.'
        )
    }
}

# ============================================================

Write-Host '[8/12] App.tsx structural scan...'

#
# Yeniden parse et.
#

$checkAppOpen =
    Find-AppOpenBrace `
        $app

if ($checkAppOpen -lt 0) {
    Fail 'Patched App() bulunamadı.'
}

$checkReturn =
    Find-AppReturnOpenParen `
        -Text $app `
        -AppOpenBrace $checkAppOpen

if ($checkReturn -lt 0) {
    Fail 'Patched return(...) bulunamadı.'
}

$checkRoot =
    Find-JsxRootRange `
        -Text $app `
        -Start ($checkReturn + 1)

if ($null -eq $checkRoot) {
    Fail 'Patched JSX root parse edilemedi.'
}

if (
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge invocation bulunamadı.'
}

#
# Component'in root JSX range'inin içinde olması zorunlu.
#

$bridgeIndex =
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if (
    $bridgeIndex -lt $checkRoot.OpenEnd -or
    $bridgeIndex -gt $checkRoot.CloseStart
) {
    Fail (
        'AuraJarvisBridge JSX root sınırlarının dışında.'
    )
}

#
# Bridge import kontrolü.
#

if (
    $app.IndexOf(
        'import AuraJarvisBridge from "./AuraJarvisBridge";',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge import bulunamadı.'
}

# ============================================================

Write-Host '[9/12] App.tsx yazılıyor...'

Write-Utf8Text `
    -Path $AppPath `
    -Text $app

# ============================================================

Write-Host '[10/12] FastAPI target discovery + graceful degradation...'

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

$backendText =
    Read-Utf8Text `
        $backendResult.Path

if (
    $backendText.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail '/api/assistant/respond backend dosyasında bulunamadı.'
}

if (
    $backendText.IndexOf(
        'local-offline',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Ollama offline fallback bulunamadı.'
}

if (
    $backendText.IndexOf(
        'LLM çekirdeğime şu an ulaşamıyorum',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Graceful degradation mesajı bulunamadı.'
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

Write-Host '[12/12] npm run build...'

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
    Write-Host 'BUILD FAILED - otomatik rollback...' -ForegroundColor Red

    Restore-File `
        -BackupPath (
            Join-Path `
                $BackupDir `
                'aura-ui\src\App.tsx'
        ) `
        -Destination $AppPath

    Restore-File `
        -BackupPath (
            Join-Path `
                $BackupDir `
                'core\src\aura_core\application\api.py'
        ) `
        -Destination $ApiPath

    #
    # Bridge yeni oluşturulduysa kaldır.
    # Önceden mevcutsa backup yoksa dokunmamak yerine
    # mevcut bridge'i korumak daha güvenlidir.
    #

    Write-Host 'App.tsx ve api.py rollback edildi.' -ForegroundColor Yellow

    Fail 'npm run build başarısız.'
}

# ============================================================
# FINAL FRONTEND VALIDATION
# ============================================================

$finalApp =
    Read-Utf8Text `
        $AppPath

$finalBridge =
    Read-Utf8Text `
        $BridgePath

$finalOpen =
    Find-AppOpenBrace `
        $finalApp

$finalReturn =
    Find-AppReturnOpenParen `
        -Text $finalApp `
        -AppOpenBrace $finalOpen

$finalRoot =
    Find-JsxRootRange `
        -Text $finalApp `
        -Start ($finalReturn + 1)

if ($null -eq $finalRoot) {
    Fail 'Final JSX root doğrulanamadı.'
}

$finalBridgeIndex =
    $finalApp.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if (
    $finalBridgeIndex -lt $finalRoot.OpenEnd -or
    $finalBridgeIndex -gt $finalRoot.CloseStart
) {
    Fail 'Final AuraJarvisBridge root sınırları dışında.'
}

if (
    $finalBridge.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Frontend assistant endpoint bağlantısı yok.'
}

if (
    $finalBridge.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS queue bulunamadı.'
}

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
    Fail 'Eski hardcoded assistant reply kaldı.'
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.4 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App() detection             : PASS'
Write-Host 'return(...) detection       : PASS'
Write-Host 'JSX root lexical parse      : PASS'
Write-Host 'Fragment/root injection     : PASS'
Write-Host 'AuraJarvisBridge            : PASS'
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