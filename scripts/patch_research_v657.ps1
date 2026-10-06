# ============================================================
# AURA V6.5.7
# JARVIS / TYPESCRIPT CLEANUP PATCH
#
# V6.5.6 scope-safe JSX injection korunur.
#
# Ek düzeltmeler:
#   1. App.tsx içindeki kullanılmayan useRef importu kaldırılır.
#   2. setResearchOutput kullanılmıyorsa state:
#        [researchOutput, setResearchOutput]
#      yerine:
#        [researchOutput]
#      yapılır.
#   3. Eski AuraConversationalResearch JSX çağrıları tamamen kaldırılır.
#   4. Eski AuraConversationalResearch importları kaldırılır.
#   5. Eski generated V6.x blokları temizlenir.
#   6. Ana App() scope + JSX return keşfi V6.5.6 mantığıyla korunur.
#   7. AuraJarvisBridge yalnızca ana App return(...) içine eklenir.
#   8. Backend mevcut /api/assistant/respond route'unu korur.
#   9. Route yoksa mevcut FastAPI/APIRouter target dinamik bulunur.
#  10. Ollama offline graceful degradation korunur.
#  11. Python compile + npm build zorunludur.
#  12. Build başarısızsa otomatik rollback yapılır.
# ============================================================

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root       = 'D:\AURA\JAS'
$UiRoot     = Join-Path $Root 'aura-ui'
$CoreRoot   = Join-Path $Root 'core'
$CoreSrc    = Join-Path $CoreRoot 'src'

$AppPath    = Join-Path $UiRoot 'src\App.tsx'
$BridgePath = Join-Path $UiRoot 'src\AuraJarvisBridge.tsx'
$ApiPath    = Join-Path $CoreSrc 'aura_core\application\api.py'

$BackupRoot = Join-Path $Root '.aura-backups'
$Stamp      = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir  = Join-Path $BackupRoot "research-v657-$Stamp"

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param(
        [string]$Message
    )

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.7 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red

    throw $Message
}

function Read-Utf8 {
    param(
        [string]$Path
    )

    if (
        -not (
            Test-Path `
                -LiteralPath $Path `
                -PathType Leaf
        )
    ) {
        Fail "Dosya bulunamadı: $Path"
    }

    $text =
        [System.IO.File]::ReadAllText(
            $Path,
            [System.Text.Encoding]::UTF8
        )

    if (
        [string]::IsNullOrWhiteSpace(
            $text
        )
    ) {
        Fail "Dosya boş: $Path"
    }

    return $text
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Text
    )

    $parent =
        Split-Path `
            -Parent `
            $Path

    New-Item `
        -ItemType Directory `
        -Path $parent `
        -Force |
        Out-Null

    $encoding =
        New-Object System.Text.UTF8Encoding(
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

    $destination =
        Join-Path `
            $BackupDir `
            $Relative

    $parent =
        Split-Path `
            -Parent `
            $destination

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
        [string]$Backup,
        [string]$Destination
    )

    if (
        Test-Path `
            -LiteralPath $Backup `
            -PathType Leaf
    ) {
        Copy-Item `
            -LiteralPath $Backup `
            -Destination $Destination `
            -Force
    }
}

function Remove-MarkerBlock {
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
            Fail "Generated block END bulunamadı: $EndMarker"
        }

        $end += $EndMarker.Length

        $Text =
            $Text.Remove(
                $start,
                $end - $start
            )
    }

    return $Text
}

# ============================================================
# JS / TS DELIMITER SCANNER
# ============================================================

function Find-MatchingDelimiter {
    param(
        [string]$Text,
        [int]$OpenIndex,
        [char]$OpenChar,
        [char]$CloseChar
    )

    if (
        $OpenIndex -lt 0 -or
        $OpenIndex -ge $Text.Length
    ) {
        return -1
    }

    if (
        $Text[$OpenIndex] -ne $OpenChar
    ) {
        return -1
    }

    $depth = 0
    $mode = 'code'
    $i = $OpenIndex

    while (
        $i -lt $Text.Length
    ) {

        $c = $Text[$i]

        if ($mode -eq 'single') {

            if ($c -eq '\') {
                $i += 2
                continue
            }

            if ($c -eq "'") {
                $mode = 'code'
            }

            $i++
            continue
        }

        if ($mode -eq 'double') {

            if ($c -eq '\') {
                $i += 2
                continue
            }

            if ($c -eq '"') {
                $mode = 'code'
            }

            $i++
            continue
        }

        if ($mode -eq 'template') {

            if ($c -eq '\') {
                $i += 2
                continue
            }

            if ($c -eq '`') {
                $mode = 'code'
            }

            $i++
            continue
        }

        if ($mode -eq 'linecomment') {

            if (
                $c -eq "`r" -or
                $c -eq "`n"
            ) {
                $mode = 'code'
            }

            $i++
            continue
        }

        if ($mode -eq 'blockcomment') {

            if (
                $c -eq '*' -and
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq '/'
            ) {
                $mode = 'code'
                $i += 2
                continue
            }

            $i++
            continue
        }

        if ($c -eq "'") {
            $mode = 'single'
            $i++
            continue
        }

        if ($c -eq '"') {
            $mode = 'double'
            $i++
            continue
        }

        if ($c -eq '`') {
            $mode = 'template'
            $i++
            continue
        }

        if (
            $c -eq '/' -and
            ($i + 1) -lt $Text.Length
        ) {

            if (
                $Text[$i + 1] -eq '/'
            ) {
                $mode = 'linecomment'
                $i += 2
                continue
            }

            if (
                $Text[$i + 1] -eq '*'
            ) {
                $mode = 'blockcomment'
                $i += 2
                continue
            }
        }

        if (
            $c -eq $OpenChar
        ) {
            $depth++
            $i++
            continue
        }

        if (
            $c -eq $CloseChar
        ) {

            $depth--

            if (
                $depth -eq 0
            ) {
                return $i
            }

            if (
                $depth -lt 0
            ) {
                return -1
            }
        }

        $i++
    }

    return -1
}

# ============================================================
# APP SCOPE
# ============================================================

function Find-AppDeclaration {
    param(
        [string]$Text
    )

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*export\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*function\s+App\s*\([^)]*\)\s*\{'
    )

    foreach (
        $pattern in $patterns
    ) {

        $m =
            [regex]::Match(
                $Text,
                $pattern
            )

        if (
            $m.Success
        ) {

            $openBrace =
                $m.Index +
                $m.Value.LastIndexOf(
                    '{'
                )

            return [PSCustomObject]@{
                Index     = $m.Index
                OpenBrace = $openBrace
            }
        }
    }

    return $null
}

function Find-AppScope {
    param(
        [string]$Text
    )

    $decl =
        Find-AppDeclaration `
            -Text $Text

    if (
        $null -eq $decl
    ) {
        return $null
    }

    $closeBrace =
        Find-MatchingDelimiter `
            -Text $Text `
            -OpenIndex $decl.OpenBrace `
            -OpenChar ([char]'{') `
            -CloseChar ([char]'}')

    if (
        $closeBrace -lt 0
    ) {
        return $null
    }

    return [PSCustomObject]@{
        Declaration = $decl
        OpenBrace   = $decl.OpenBrace
        CloseBrace  = $closeBrace
    }
}

# ============================================================
# MAIN JSX RETURN DISCOVERY
# ============================================================

function Find-AppJsxReturn {
    param(
        [string]$Text,
        [int]$AppOpenBrace,
        [int]$AppCloseBrace
    )

    if (
        $AppCloseBrace -le $AppOpenBrace
    ) {
        return $null
    }

    $scopeLength =
        $AppCloseBrace -
        $AppOpenBrace -
        1

    $scope =
        $Text.Substring(
            $AppOpenBrace + 1,
            $scopeLength
        )

    $matches =
        [regex]::Matches(
            $scope,
            '(?m)\breturn\s*\('
        )

    $candidates = @()

    foreach (
        $m in $matches
    ) {

        $openRelative =
            $m.Index +
            $m.Value.LastIndexOf(
                '('
            )

        $openAbsolute =
            $AppOpenBrace +
            1 +
            $openRelative

        $closeAbsolute =
            Find-MatchingDelimiter `
                -Text $Text `
                -OpenIndex $openAbsolute `
                -OpenChar ([char]'(') `
                -CloseChar ([char]')')

        if (
            $closeAbsolute -lt 0 -or
            $closeAbsolute -ge $AppCloseBrace
        ) {
            continue
        }

        $expression =
            $Text.Substring(
                $openAbsolute + 1,
                $closeAbsolute -
                $openAbsolute -
                1
            )

        # Cleanup:
        # return () => { ... }
        if (
            $expression -match
            '^\s*\(\s*\)\s*=>'
        ) {
            continue
        }

        if (
            [string]::IsNullOrWhiteSpace(
                $expression
            )
        ) {
            continue
        }

        $hasJsx =
            [regex]::IsMatch(
                $expression,
                '(?s)<\s*(?:[A-Za-z][A-Za-z0-9_.:-]*|>)'
            )

        if (
            -not $hasJsx
        ) {
            continue
        }

        $candidates +=
            [PSCustomObject]@{
                Open =
                    $openAbsolute

                Close =
                    $closeAbsolute
            }
    }

    if (
        $candidates.Count -eq 0
    ) {
        return $null
    }

    return $candidates[
        $candidates.Count - 1
    ]
}

# ============================================================
# STATE DISCOVERY
# ============================================================

function Find-State {
    param(
        [string]$Text,
        [string[]]$Names
    )

    foreach (
        $name in $Names
    ) {

        $pattern =
            'const\s*\[\s*' +
            [regex]::Escape(
                $name
            ) +
            '\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'

        $m =
            [regex]::Match(
                $Text,
                $pattern
            )

        if (
            $m.Success
        ) {

            return [PSCustomObject]@{
                Value  = $name
                Setter = $m.Groups[
                    'setter'
                ].Value
            }
        }
    }

    return $null
}

# ============================================================
# REACT IMPORT CLEANUP
# ============================================================

function Normalize-ReactImport {
    param(
        [string]$Text
    )

    $m =
        [regex]::Match(
            $Text,
            '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
        )

    if (
        -not $m.Success
    ) {
        return $Text
    }

    $items = @()

    foreach (
        $item in
        $m.Groups['body'].Value -split ','
    ) {

        $name =
            $item.Trim()

        if (
            $name.Length -gt 0 -and
            $items -notcontains $name
        ) {
            $items += $name
        }
    }

    #
    # V6.5.7 App.tsx'te useRef KULLANILMAYACAK.
    # useEffect/useState gerekiyorsa korunur.
    #

    $items =
        @(
            $items |
            Where-Object {
                $_ -ne 'useRef'
            }
        )

    #
    # Bridge App.tsx state/logic için bunları gerektiriyor olabilir.
    # Kullanılmayan hook eklemiyoruz.
    #

    $newImport =
        'import { ' +
        ($items -join ', ') +
        ' } from "react";'

    return (
        $Text.Remove(
            $m.Index,
            $m.Length
        ).Insert(
            $m.Index,
            $newImport
        )
    )
}

# ============================================================
# FASTAPI DISCOVERY
# ============================================================

function Find-FastApiTarget {
    param(
        [string]$Text
    )

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*FastAPI\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.APIRouter\s*\('
    )

    foreach (
        $pattern in $patterns
    ) {

        $m =
            [regex]::Match(
                $Text,
                $pattern
            )

        if (
            $m.Success
        ) {
            return $m.Groups[
                'name'
            ].Value
        }
    }

    $decorator =
        [regex]::Match(
            $Text,
            '(?m)^\s*@(?<name>[A-Za-z_]\w*)\.(?:get|post|put|delete|patch|api_route)\s*\('
        )

    if (
        $decorator.Success
    ) {
        return $decorator.Groups[
            'name'
        ].Value
    }

    return $null
}

# ============================================================
# MAIN
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.7 JARVIS / TYPESCRIPT CLEANUP PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/12] Proje kontrol ediliyor...'

foreach (
    $path in @(
        $Root,
        $UiRoot,
        $CoreRoot,
        $CoreSrc
    )
) {

    if (
        -not (
            Test-Path `
                -LiteralPath $path `
                -PathType Container
        )
    ) {
        Fail "Directory bulunamadı: $path"
    }
}

foreach (
    $path in @(
        $AppPath,
        $ApiPath
    )
) {

    if (
        -not (
            Test-Path `
                -LiteralPath $path `
                -PathType Leaf
        )
    ) {
        Fail "Dosya bulunamadı: $path"
    }
}

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

if (
    Test-Path `
        -LiteralPath $BridgePath `
        -PathType Leaf
) {

    Backup-File `
        -Source $BridgePath `
        -Relative 'aura-ui\src\AuraJarvisBridge.tsx'
}

# ============================================================

Write-Host '[3/12] App.tsx okunuyor...'

$app =
    Read-Utf8 `
        $AppPath

# ============================================================

Write-Host '[4/12] Eski V6.x generated blokları temizleniyor...'

$blocks = @(
    @(
        'AURA_JARVIS_LLM_V656_START',
        'AURA_JARVIS_LLM_V656_END'
    ),
    @(
        'AURA_JARVIS_LLM_V655_START',
        'AURA_JARVIS_LLM_V655_END'
    ),
    @(
        'AURA_JARVIS_LLM_V654_START',
        'AURA_JARVIS_LLM_V654_END'
    ),
    @(
        'AURA_JARVIS_LLM_V653_START',
        'AURA_JARVIS_LLM_V653_END'
    ),
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

foreach (
    $block in $blocks
) {

    $app =
        Remove-MarkerBlock `
            -Text $app `
            -StartMarker $block[0] `
            -EndMarker $block[1]
}

# ============================================================
# ESKİ AURA CONVERSATIONAL RESEARCH TAM TEMİZLİĞİ
# ============================================================

Write-Host '    AuraConversationalResearch JSX temizleniyor...'

#
# JSX self-closing:
# <AuraConversationalResearch />
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\s*<AuraConversationalResearch\b[^>]*/>\s*',
        "`r`n"
    )

#
# JSX normal opening/closing:
# <AuraConversationalResearch ...>
#     ...
# </AuraConversationalResearch>
#
# Bu component eski/generated olduğu için
# tamamı kaldırılır.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\s*<AuraConversationalResearch\b[^>]*>.*?</AuraConversationalResearch>\s*',
        "`r`n"
    )

#
# Import varyantları:
#
# import AuraConversationalResearch from "...";
# import { AuraConversationalResearch } from "...";
# import { ..., AuraConversationalResearch, ... } from "...";
#

$app =
    [regex]::Replace(
        $app,
        '(?m)^\s*import\s+AuraConversationalResearch\s+from\s+["''][^"'']+["''];?\s*\r?\n',
        ''
    )

$app =
    [regex]::Replace(
        $app,
        '(?m)^\s*import\s*\{\s*AuraConversationalResearch\s*\}\s*from\s+["''][^"'']+["''];?\s*\r?\n',
        ''
    )

$app =
    [regex]::Replace(
        $app,
        '(?m)^([ \t]*import\s*\{)([^}]*?)\bAuraConversationalResearch\b\s*,?\s*([^}]*)(\}\s*from\s+["''][^"'']+["''];?)',
        {
            param($m)

            $left =
                $m.Groups[1].Value

            $before =
                $m.Groups[2].Value

            $after =
                $m.Groups[3].Value

            $right =
                $m.Groups[4].Value

            $items =
                @(
                    (
                        $before +
                        ',' +
                        $after
                    ) -split ','
                ) |
                ForEach-Object {
                    $_.Trim()
                } |
                Where-Object {
                    $_ -and
                    $_ -ne 'AuraConversationalResearch'
                }

            if (
                $items.Count -eq 0
            ) {
                return ''
            }

            return (
                $left +
                ' ' +
                ($items -join ', ') +
                ' ' +
                $right
            )
        }
    )

#
# Component adı başka bir yerde kaldıysa,
# yalnızca JSX identifier referansını kaldır.
#

$app =
    [regex]::Replace(
        $app,
        '(?m)^[ \t]*<AuraConversationalResearch\b[^>]*\/>[ \t]*\r?\n?',
        ''
    )

# ============================================================

Write-Host '[5/12] React importleri temizleniyor...'

$app =
    Normalize-ReactImport `
        -Text $app

#
# V6.5.6'in yanlışlıkla bıraktığı useRef importu:
#

$app =
    [regex]::Replace(
        $app,
        '(?m)^(\s*import\s*\{)([^}]*?)\buseRef\b\s*,?\s*([^}]*)(\}\s*from\s+["'']react["''];?)',
        {
            param($m)

            $before =
                $m.Groups[2].Value

            $after =
                $m.Groups[3].Value

            $items =
                @(
                    (
                        $before +
                        ',' +
                        $after
                    ) -split ','
                ) |
                ForEach-Object {
                    $_.Trim()
                } |
                Where-Object {
                    $_ -and
                    $_ -ne 'useRef'
                }

            if (
                $items.Count -eq 0
            ) {
                return ''
            }

            return (
                $m.Groups[1].Value +
                ' ' +
                ($items -join ', ') +
                ' ' +
                $m.Groups[4].Value
            )
        }
    )

# ============================================================

Write-Host '[6/12] App scope ve state temizliği hazırlanıyor...'

$appScope =
    Find-AppScope `
        -Text $app

if (
    $null -eq $appScope
) {
    Fail 'App() scope bulunamadı.'
}

$directiveState =
    Find-State `
        -Text $app `
        -Names @(
            'command',
            'directive',
            'input',
            'query',
            'userInput',
            'prompt',
            'text'
        )

if (
    $null -eq $directiveState
) {
    Fail 'Directive/command state bulunamadı.'
}

$researchState =
    Find-State `
        -Text $app `
        -Names @(
            'researchOutput',
            'auraResearchOutput',
            'researchResult',
            'taskResult',
            'completedTask'
        )

if (
    $null -eq $researchState
) {
    Fail 'researchOutput state bulunamadı.'
}

#
# setResearchOutput kullanılmıyor.
# Setter'ı kaldır.
#

$setterPattern =
    '\bconst\s*\[\s*' +
    [regex]::Escape(
        $researchState.Value
    ) +
    '\s*,\s*' +
    [regex]::Escape(
        $researchState.Setter
    ) +
    '\s*\]\s*=\s*useState'

if (
    [regex]::IsMatch(
        $app,
        $setterPattern
    )
) {

    $app =
        [regex]::Replace(
            $app,
            $setterPattern,
            (
                'const [' +
                $researchState.Value +
                '] = useState'
            ),
            1
        )
}

#
# Eğer önceki generated code setter'a referans bırakmışsa
# bunu tespit et. Kullanılmayan setter hatasını önlemek için
# state declaration artık setter içermiyor.
#

$researchState =
    Find-State `
        -Text $app `
        -Names @(
            'researchOutput',
            'auraResearchOutput',
            'researchResult',
            'taskResult',
            'completedTask'
        )

if (
    $null -eq $researchState
) {

    #
    # Find-State sadece [value,setter] biçimini aradığı için
    # setter kaldırıldıktan sonra null olması beklenen durumdur.
    #

    $researchStateName =
        'researchOutput'
}
else {

    $researchStateName =
        $researchState.Value
}

Write-Host "    Directive state : $($directiveState.Value)"
Write-Host "    Research state  : $researchStateName"
Write-Host '    setResearchOutput : REMOVED'

# ============================================================

Write-Host '[7/12] AuraJarvisBridge modülü hazırlanıyor...'

$Bridge = @'
/* AURA_JARVIS_LLM_V657_START */

import {
    useEffect,
    useRef,
    useState,
} from "react";

type AuraJarvisProps = {
    directive?: unknown;
    researchOutput?: unknown;
};

type AssistantResponse = {
    assistant_reply?: unknown;
};

function normalizeReply(
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

function researchToText(
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

        return JSON.stringify(value)
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

async function getAssistantReply(
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
                        researchToText(
                            researchOutput
                        ),
                }),
            }
        );

    if (
        !response.ok
    ) {
        throw new Error(
            "Assistant endpoint HTTP " +
            response.status
        );
    }

    const data =
        (
            await response.json()
        ) as AssistantResponse;

    return normalizeReply(
        data.assistant_reply
    );
}

function speakAssistantReply(
    reply: string
): void {

    const text =
        normalizeReply(reply);

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
    }: AuraJarvisProps
) {

    const [
        reply,
        setReply,
    ] = useState("");

    const [
        busy,
        setBusy,
    ] = useState(false);

    const generation =
        useRef(0);

    useEffect(
        () => {

            if (
                researchOutput === null ||
                researchOutput === undefined ||
                researchOutput === ""
            ) {
                return;
            }

            const current =
                generation.current + 1;

            generation.current =
                current;

            let cancelled = false;

            setBusy(true);

            getAssistantReply(
                directive,
                researchOutput
            )
                .then(
                    (assistantReply) => {

                        if (
                            cancelled ||
                            generation.current !== current
                        ) {
                            return;
                        }

                        const clean =
                            normalizeReply(
                                assistantReply
                            );

                        setReply(clean);

                        /*
                         * YALNIZCA LLM tarafından üretilen
                         * assistant_reply TTS'e gönderilir.
                         *
                         * directive       -> TTS YOK
                         * researchOutput  -> TTS YOK
                         * step.result     -> TTS YOK
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
                                "AURA JARVIS:",
                                error
                            );

                            setReply("");
                        }
                    }
                )
                .finally(
                    () => {

                        if (!cancelled) {
                            setBusy(false);
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
        !busy &&
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
                    busy
                        ? "Verileri değerlendiriyorum..."
                        : reply
                }
            </div>
        </div>
    );
}

/* AURA_JARVIS_LLM_V657_END */
'@

Write-Utf8 `
    -Path $BridgePath `
    -Text $Bridge

# ============================================================

Write-Host '[8/12] AuraJarvisBridge importu ve JSX placement...'

$bridgeImport =
    'import AuraJarvisBridge from "./AuraJarvisBridge";'

if (
    $app.IndexOf(
        $bridgeImport,
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $app =
        $bridgeImport +
        "`r`n" +
        $app
}

#
# Import eklenince indexleri yeniden hesapla.
#

$appScope =
    Find-AppScope `
        -Text $app

if (
    $null -eq $appScope
) {
    Fail 'Import sonrası App scope bulunamadı.'
}

$jsxReturn =
    Find-AppJsxReturn `
        -Text $app `
        -AppOpenBrace $appScope.OpenBrace `
        -AppCloseBrace $appScope.CloseBrace

if (
    $null -eq $jsxReturn
) {
    Fail 'Import sonrası ana JSX return bulunamadı.'
}

$body =
    $app.Substring(
        $jsxReturn.Open + 1,
        $jsxReturn.Close -
        $jsxReturn.Open -
        1
    )

#
# Eski Bridge çağrısı varsa kaldır.
#

$body =
    [regex]::Replace(
        $body,
        '(?s)\s*<AuraJarvisBridge\b.*?\/>\s*',
        "`r`n"
    )

$bridgeMarkup = @"
        <AuraJarvisBridge
            directive={$($directiveState.Value)}
            researchOutput={$researchStateName}
        />
"@

#
# Tüm mevcut JSX expression'ı Fragment'e al.
#

$fragmentedBody =
    "`r`n" +
    "        <>`r`n" +
    $body.Trim() +
    "`r`n`r`n" +
    $bridgeMarkup.TrimEnd() +
    "`r`n" +
    "        </>`r`n    "

$prefix =
    $app.Substring(
        0,
        $jsxReturn.Open + 1
    )

$suffix =
    $app.Substring(
        $jsxReturn.Close
    )

$app =
    $prefix +
    $fragmentedBody +
    $suffix

# ============================================================

Write-Host '[9/12] Eski component referansları final cleanup...'

#
# AuraConversationalResearch artık hiçbir yerde kalmamalı.
#

$remainingOldComponent =
    [regex]::Matches(
        $app,
        '\bAuraConversationalResearch\b'
    ).Count

if (
    $remainingOldComponent -gt 0
) {

    #
    # Güvenli identifier temizliği:
    # Import/JSX zaten temizlendi.
    # Eğer comment/string içinde kalmışsa da kaldır.
    #

    $app =
        [regex]::Replace(
            $app,
            '\bAuraConversationalResearch\b',
            ''
        )
}

#
# V6.3/V6.4 hardcoded reply kalıntıları.
#

foreach (
    $oldReply in @(
        'Elbette. Araştırmayı tamamladım.',
        'Elbette, araştırmayı tamamladım.',
        'Araştırmayı tamamladım.'
    )
) {

    if (
        $app.IndexOf(
            $oldReply,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {

        $app =
            $app.Replace(
                $oldReply,
                ''
            )
    }
}

#
# useRef App.tsx'te kalmamalı.
#

$app =
    [regex]::Replace(
        $app,
        '(?m)^(\s*import\s*\{)([^}]*?)\buseRef\b\s*,?\s*([^}]*)(\}\s*from\s+["'']react["''];?)',
        {
            param($m)

            $items =
                @(
                    (
                        $m.Groups[2].Value +
                        ',' +
                        $m.Groups[3].Value
                    ) -split ','
                ) |
                ForEach-Object {
                    $_.Trim()
                } |
                Where-Object {
                    $_ -and
                    $_ -ne 'useRef'
                }

            if (
                $items.Count -eq 0
            ) {
                return ''
            }

            return (
                $m.Groups[1].Value +
                ' ' +
                ($items -join ', ') +
                ' ' +
                $m.Groups[4].Value
            )
        }
    )

# ============================================================

Write-Host '[10/12] Structural validation...'

#
# App scope.
#

$appScope =
    Find-AppScope `
        -Text $app

if (
    $null -eq $appScope
) {
    Fail 'Final App scope bulunamadı.'
}

#
# Main JSX return.
#

$jsxReturn =
    Find-AppJsxReturn `
        -Text $app `
        -AppOpenBrace $appScope.OpenBrace `
        -AppCloseBrace $appScope.CloseBrace

if (
    $null -eq $jsxReturn
) {
    Fail 'Final ana JSX return bulunamadı.'
}

#
# Bridge inside main return.
#

$bridgeIndex =
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if (
    $bridgeIndex -le $jsxReturn.Open -or
    $bridgeIndex -ge $jsxReturn.Close
) {
    Fail 'AuraJarvisBridge ana JSX return dışında.'
}

#
# Old component MUST be gone.
#

if (
    [regex]::IsMatch(
        $app,
        '\bAuraConversationalResearch\b'
    )
) {
    Fail 'AuraConversationalResearch referansı hâlâ mevcut.'
}

#
# useRef import MUST be gone from App.tsx.
#

$reactImport =
    [regex]::Match(
        $app,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']'
    )

if (
    $reactImport.Success -and
    $reactImport.Groups[
        'body'
    ].Value -match '\buseRef\b'
) {
    Fail 'App.tsx içinde kullanılmayan useRef importu kaldı.'
}

#
# setResearchOutput MUST NOT exist.
#

if (
    [regex]::IsMatch(
        $app,
        '\bsetResearchOutput\b'
    )
) {
    Fail 'setResearchOutput referansı hâlâ App.tsx içinde.'
}

#
# Hardcoded assistant reply MUST NOT exist.
#

foreach (
    $oldReply in @(
        'Elbette. Araştırmayı tamamladım.',
        'Elbette, araştırmayı tamamladım.',
        'Araştırmayı tamamladım.'
    )
) {

    if (
        $app.IndexOf(
            $oldReply,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {
        Fail "Hardcoded assistant reply kaldı: $oldReply"
    }
}

#
# Bridge module.
#

$bridgeFinal =
    Read-Utf8 `
        $BridgePath

if (
    $bridgeFinal.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Assistant endpoint bridge bağlantısı bulunamadı.'
}

if (
    $bridgeFinal.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS queue bulunamadı.'
}

#
# Raw data direct TTS yasak.
#

foreach (
    $forbiddenTts in @(
        'speakAssistantReply(directive)',
        'speakAssistantReply(researchOutput)',
        'speakAssistantReply(step.result)',
        'speechSynthesis.speak(directive)',
        'speechSynthesis.speak(researchOutput)',
        'speechSynthesis.speak(step.result)'
    )
) {

    if (
        $bridgeFinal.IndexOf(
            $forbiddenTts,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        Fail "Ham veri TTS'e bağlanmış: $forbiddenTts"
    }
}

Write-Host '    App scope                    : PASS'
Write-Host '    Main JSX return              : PASS'
Write-Host '    Fragment wrapper             : PASS'
Write-Host '    Bridge inside main return    : PASS'
Write-Host '    AuraConversationalResearch   : REMOVED'
Write-Host '    useRef App import            : REMOVED'
Write-Host '    setResearchOutput            : REMOVED'
Write-Host '    Hardcoded reply              : REMOVED'
Write-Host '    Raw research -> TTS          : BLOCKED'

#
# App yaz.
#

Write-Utf8 `
    -Path $AppPath `
    -Text $app

# ============================================================

Write-Host '[11/12] FastAPI target + Python validation...'

$api =
    Read-Utf8 `
        $ApiPath

$hasRoute =
    $api -match
    '/api/assistant/respond'

if (
    -not $hasRoute
) {

    $target =
        Find-FastApiTarget `
            -Text $api

    if (
        $null -eq $target
    ) {

        Restore-File `
            -Backup (
                Join-Path `
                    $BackupDir `
                    'aura-ui\src\App.tsx'
            ) `
            -Destination $AppPath

        Restore-File `
            -Backup (
                Join-Path `
                    $BackupDir `
                    'core\src\aura_core\application\api.py'
            ) `
            -Destination $ApiPath

        Fail 'FastAPI/APIRouter target bulunamadı.'
    }

    #
    # Route zaten V6.5.x backend patchinden gelmesi bekleniyor.
    # Burada mimariyi değiştirmemek için yalnızca mevcut route'u
    # doğruluyoruz; yeni backend implementation enjekte etmiyoruz.
    #

    Fail (
        "Backend route bulunamadı: /api/assistant/respond. " +
        "V6.5.x backend patch'i uygulanmadan frontend bridge " +
        "eklenmeyecektir."
    )
}

Write-Host '    /api/assistant/respond        : FOUND'

$python =
    Get-Command `
        python.exe `
        -ErrorAction SilentlyContinue

if (
    $null -eq $python
) {

    $python =
        Get-Command `
            python `
            -ErrorAction SilentlyContinue
}

if (
    $null -eq $python
) {

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'aura-ui\src\App.tsx'
        ) `
        -Destination $AppPath

    Fail 'Python bulunamadı.'
}

& $python.Source `
    -m py_compile `
    $ApiPath

if (
    $LASTEXITCODE -ne 0
) {

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'aura-ui\src\App.tsx'
        ) `
        -Destination $AppPath

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'core\src\aura_core\application\api.py'
        ) `
        -Destination $ApiPath

    Fail 'Python compile başarısız.'
}

Write-Host '    Python compile               : PASS'

# ============================================================

Write-Host '[12/12] TypeScript / Vite build...'

Push-Location $UiRoot

try {

    $npm =
        Get-Command `
            npm.cmd `
            -ErrorAction SilentlyContinue

    if (
        $null -eq $npm
    ) {

        $npm =
            Get-Command `
                npm `
                -ErrorAction SilentlyContinue
    }

    if (
        $null -eq $npm
    ) {
        throw 'npm bulunamadı.'
    }

    & $npm.Source run build

    $buildExit =
        $LASTEXITCODE
}
catch {

    Write-Host $_.Exception.Message -ForegroundColor Red
    $buildExit = 1
}
finally {

    Pop-Location
}

if (
    $buildExit -ne 0
) {

    Write-Host ''
    Write-Host 'BUILD FAILED - rollback başlatılıyor...' -ForegroundColor Red

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'aura-ui\src\App.tsx'
        ) `
        -Destination $AppPath

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'core\src\aura_core\application\api.py'
        ) `
        -Destination $ApiPath

    if (
        Test-Path `
            -LiteralPath (
                Join-Path `
                    $BackupDir `
                    'aura-ui\src\AuraJarvisBridge.tsx'
            )
    ) {

        Restore-File `
            -Backup (
                Join-Path `
                    $BackupDir `
                    'aura-ui\src\AuraJarvisBridge.tsx'
            ) `
            -Destination $BridgePath
    }

    Fail 'npm run build başarısız; tüm patch değişiklikleri rollback edildi.'
}

# ============================================================
# FINAL ASSERTIONS
# ============================================================

$finalApp =
    Read-Utf8 `
        $AppPath

if (
    [regex]::IsMatch(
        $finalApp,
        '\bAuraConversationalResearch\b'
    )
) {
    Fail 'FINAL: AuraConversationalResearch hâlâ mevcut.'
}

if (
    [regex]::IsMatch(
        $finalApp,
        '\bsetResearchOutput\b'
    )
) {
    Fail 'FINAL: setResearchOutput hâlâ mevcut.'
}

$finalReactImport =
    [regex]::Match(
        $finalApp,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']'
    )

if (
    $finalReactImport.Success -and
    $finalReactImport.Groups[
        'body'
    ].Value -match '\buseRef\b'
) {
    Fail 'FINAL: useRef hâlâ App.tsx React importunda.'
}

$finalScope =
    Find-AppScope `
        -Text $finalApp

if (
    $null -eq $finalScope
) {
    Fail 'FINAL: App scope bulunamadı.'
}

$finalReturn =
    Find-AppJsxReturn `
        -Text $finalApp `
        -AppOpenBrace $finalScope.OpenBrace `
        -AppCloseBrace $finalScope.CloseBrace

if (
    $null -eq $finalReturn
) {
    Fail 'FINAL: JSX return bulunamadı.'
}

$finalBridge =
    $finalApp.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if (
    $finalBridge -le $finalReturn.Open -or
    $finalBridge -ge $finalReturn.Close
) {
    Fail 'FINAL: AuraJarvisBridge ana return içinde değil.'
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.7 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App scope                     : PASS'
Write-Host 'Main JSX return               : PASS'
Write-Host 'Fragment wrapper              : PASS'
Write-Host 'AuraJarvisBridge              : PASS'
Write-Host 'AuraConversationalResearch    : REMOVED'
Write-Host 'useRef unused import          : REMOVED'
Write-Host 'setResearchOutput unused var  : REMOVED'
Write-Host 'Hardcoded assistant reply     : REMOVED'
Write-Host 'Raw step.result -> TTS        : BLOCKED'
Write-Host 'LLM assistant_reply -> TTS    : PASS'
Write-Host 'Assistant endpoint            : FOUND'
Write-Host 'Python compile                : PASS'
Write-Host 'npm run build                 : PASS'
Write-Host ''
Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''