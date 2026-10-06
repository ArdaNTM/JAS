# ============================================================
# AURA V6.5.5
# JARVIS / SAFE BALANCED RETURN() JSX PATCH
#
# V6.5.5 değişiklikleri:
#   - JSX lexer/parser YOK
#   - JSX root discovery YOK
#   - return(...) balanced-parenthesis taraması kullanılır
#   - return içeriği güvenli Fragment ile sarılır
#   - AuraJarvisBridge Fragment içine, return kapanışından önce eklenir
#   - FastAPI mevcut route varsa korunur
#   - FastAPI target dinamik bulunur
#   - Ollama offline graceful degradation korunur
#   - Build fail -> otomatik rollback
# ============================================================

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root      = 'D:\AURA\JAS'
$UiRoot    = Join-Path $Root 'aura-ui'
$CoreRoot  = Join-Path $Root 'core'
$CoreSrc   = Join-Path $CoreRoot 'src'

$AppPath   = Join-Path $UiRoot 'src\App.tsx'
$BridgePath = Join-Path $UiRoot 'src\AuraJarvisBridge.tsx'
$ApiPath   = Join-Path $CoreSrc 'aura_core\application\api.py'

$BackupRoot = Join-Path $Root '.aura-backups'
$Stamp      = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir  = Join-Path $BackupRoot "research-v655-$Stamp"

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.5 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Read-Utf8 {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "Dosya bulunamadı: $Path"
    }

    $text = [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.Encoding]::UTF8
    )

    if ([string]::IsNullOrWhiteSpace($text)) {
        Fail "Dosya boş: $Path"
    }

    return $text
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Text
    )

    $parent = Split-Path $Path -Parent

    New-Item `
        -ItemType Directory `
        -Path $parent `
        -Force |
        Out-Null

    $enc = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $enc
    )
}

function Backup-File {
    param(
        [string]$Source,
        [string]$Relative
    )

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
        [string]$Backup,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Backup -PathType Leaf) {
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
            Fail "Generated block END bulunamadı: $EndMarker"
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
# APP() DISCOVERY
# ============================================================

function Find-AppFunction {
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

# ============================================================
# BALANCED JAVASCRIPT PARENTHESIS SCANNER
#
# JSX AST çözümlemez.
# Sadece return( ... ) içindeki JavaScript parantezlerini
# dengeli şekilde takip eder.
#
# String/comment/template içindeki parantezleri saymaz.
# ============================================================

function Find-MatchingParen {
    param(
        [string]$Text,
        [int]$OpenIndex
    )

    if (
        $OpenIndex -lt 0 -or
        $OpenIndex -ge $Text.Length -or
        $Text[$OpenIndex] -ne '('
    ) {
        return -1
    }

    $depth = 0
    $mode = 'code'
    $i = $OpenIndex

    while ($i -lt $Text.Length) {

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
                $i++
                continue
            }

            #
            # Template literal içindeki ${...}
            # expression'larını ayrı parse etmek yerine burada
            # template'i tamamen string olarak kabul ediyoruz.
            #

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

        # CODE MODE

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

            if ($Text[$i + 1] -eq '/') {
                $mode = 'linecomment'
                $i += 2
                continue
            }

            if ($Text[$i + 1] -eq '*') {
                $mode = 'blockcomment'
                $i += 2
                continue
            }
        }

        if ($c -eq '(') {
            $depth++
            $i++
            continue
        }

        if ($c -eq ')') {

            $depth--

            if ($depth -eq 0) {
                return $i
            }

            if ($depth -lt 0) {
                return -1
            }

            $i++
            continue
        }

        $i++
    }

    return -1
}

function Find-AppReturn {
    param(
        [string]$Text,
        [int]$AppBrace
    )

    if ($AppBrace -lt 0) {
        return $null
    }

    $tail = $Text.Substring(
        $AppBrace + 1
    )

    #
    # return (
    # return(
    # return    (
    #
    $m = [regex]::Match(
        $tail,
        '(?s)\breturn\s*\('
    )

    if (-not $m.Success) {
        return $null
    }

    $relativeOpen =
        $m.Index +
        $m.Value.LastIndexOf('(')

    $openIndex =
        $AppBrace +
        1 +
        $relativeOpen

    $closeIndex =
        Find-MatchingParen `
            -Text $Text `
            -OpenIndex $openIndex

    if ($closeIndex -lt 0) {
        return $null
    }

    return [PSCustomObject]@{
        Open  = $openIndex
        Close = $closeIndex
    }
}

# ============================================================
# STATE DISCOVERY
# ============================================================

function Find-State {
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
                Value  = $name
                Setter = $m.Groups['setter'].Value
            }
        }
    }

    return $null
}

function Ensure-ReactHooks {
    param([string]$Text)

    $m = [regex]::Match(
        $Text,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
    )

    $required = @(
        'useEffect',
        'useRef',
        'useState'
    )

    if ($m.Success) {

        $items = @()

        foreach ($item in $m.Groups['body'].Value -split ',') {

            $v = $item.Trim()

            if (
                $v.Length -gt 0 -and
                $items -notcontains $v
            ) {
                $items += $v
            }
        }

        foreach ($required in $required) {

            if ($items -notcontains $required) {
                $items += $required
            }
        }

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

    return (
        'import { useEffect, useRef, useState } from "react";' +
        "`r`n" +
        $Text
    )
}

# ============================================================
# FASTAPI DISCOVERY
# ============================================================

function Find-FastApiTarget {
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*FastAPI\s*=\s*FastAPI\s*\('
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

    $routerPatterns = @(
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*APIRouter\s*=\s*APIRouter\s*\('
    )

    foreach ($pattern in $routerPatterns) {

        $m = [regex]::Match(
            $Text,
            $pattern
        )

        if ($m.Success) {
            return $m.Groups['name'].Value
        }
    }

    $decorator =
        [regex]::Match(
            $Text,
            '(?m)^\s*@(?<name>[A-Za-z_]\w*)\.(?:get|post|put|delete|patch|api_route)\s*\('
        )

    if ($decorator.Success) {
        return $decorator.Groups['name'].Value
    }

    return $null
}

function Has-AssistantRoute {
    param([string]$Text)

    return (
        $Text -match
        '(?s)/api/assistant/respond'
    )
}

# ============================================================
# BACKEND ROUTE
# ============================================================

function Build-AssistantRoute {
    param([string]$Target)

    $route = @'
# AURA_JARVIS_ASSISTANT_V655_START

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
                "Türkçe konuşan kişisel yapay zekâ asistanısın. "
                "Analitik, sakin, kendinden emin ve gerektiğinde "
                "ince ironik ol. Kullanıcının direktifini papağan "
                "gibi tekrar etme. Ham JSON, UUID, URL, tool trace "
                "ve teknik log okuma. Araştırma verisini analiz et "
                "ve kendi cümlelerinle kısa, doğal bir konuşma "
                "yanıtı oluştur. En fazla dört kısa cümle kullan. "
                "Markdown kullanma. Veride olmayan bilgi uydurma."
            ),
        },
        {
            "role": "user",
            "content": (
                "Direktif:\n"
                + directive[:1200]
                + "\n\nAraştırma:\n"
                + research[:14000]
                + "\n\n"
                "Araştırmayı analiz ederek doğal bir asistan "
                "yanıtı üret."
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
                "yerel zekâ katmanı yeniden çevrimiçi "
                "olduğunda onu yorumlayabilirim."
            ),
            model=os.environ.get(
                "AURA_LLM_MODEL",
                "qwen3",
            ),
            provider="local-offline",
        )

    if not reply:

        reply = (
            "Araştırma verisini aldım; fakat şu anda "
            "bundan anlamlı bir konuşma yanıtı üretemedim."
        )

    return AuraAssistantResponse(
        assistant_reply=reply,
        model=model,
        provider="ollama",
    )

# AURA_JARVIS_ASSISTANT_V655_END
'@

    return $route.Replace(
        '@TARGET',
        '@' + $Target
    )
}

function Patch-Backend {
    param([string]$Path)

    $api = Read-Utf8 $Path

    if (Has-AssistantRoute $api) {

        Write-Host '    /api/assistant/respond: EXISTING'

        return [PSCustomObject]@{
            Text   = $api
            Target = Find-FastApiTarget $api
            Added  = $false
        }
    }

    $target = Find-FastApiTarget $api

    if ($null -eq $target) {
        Fail 'FastAPI / APIRouter / route decorator target bulunamadı.'
    }

    Write-Host "    Route target: @$target"

    $route = Build-AssistantRoute $target

    $newText =
        $api.TrimEnd() +
        "`r`n`r`n" +
        $route.Trim() +
        "`r`n"

    Write-Utf8 `
        -Path $Path `
        -Text $newText

    return [PSCustomObject]@{
        Text   = $newText
        Target = $target
        Added  = $true
    }
}

# ============================================================
# BRIDGE COMPONENT
# ============================================================

$Bridge = @'
/* AURA_JARVIS_LLM_V655_START */

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

    if (typeof value !== "string") {
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

    if (typeof value === "string") {

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
                (x) => x.trim()
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

    const next =
        (): void => {

            const utterance =
                queue.shift();

            if (!utterance) {
                return;
            }

            utterance.onend = next;
            utterance.onerror = next;

            window.speechSynthesis.speak(
                utterance
            );
        };

    next();
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
                         * TTS SINIRI:
                         *
                         * directive       -> YOK
                         * researchOutput  -> YOK
                         * step.result     -> YOK
                         * assistant_reply  -> VAR
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

/* AURA_JARVIS_LLM_V655_END */
'@

# ============================================================
# START
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.5 JARVIS / BALANCED RETURN PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/11] Proje kontrol ediliyor...'

foreach ($path in @(
    $Root,
    $UiRoot,
    $CoreRoot,
    $CoreSrc
)) {

    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        Fail "Directory bulunamadı: $path"
    }
}

foreach ($path in @(
    $AppPath,
    $ApiPath
)) {

    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        Fail "Dosya bulunamadı: $path"
    }
}

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

if (Test-Path -LiteralPath $BridgePath -PathType Leaf) {

    Backup-File `
        -Source $BridgePath `
        -Relative 'aura-ui\src\AuraJarvisBridge.tsx'
}

# ============================================================

Write-Host '[3/11] App.tsx okunuyor...'

$app = Read-Utf8 $AppPath

# ============================================================

Write-Host '[4/11] Eski V6.x generated blokları temizleniyor...'

$blocks = @(
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

foreach ($block in $blocks) {

    $app =
        Remove-MarkerBlock `
            -Text $app `
            -StartMarker $block[0] `
            -EndMarker $block[1]
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
# Eski sabit persona cümleleri.
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

#
# Önceki bridge invocation.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\s*<AuraJarvisBridge\b.*?\/>',
        ''
    )

# ============================================================

Write-Host '[5/11] React hooks + state keşfi...'

$app =
    Ensure-ReactHooks `
        $app

$appBrace =
    Find-AppFunction `
        $app

if ($appBrace -lt 0) {
    Fail 'App() fonksiyonu bulunamadı.'
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

if ($null -eq $directiveState) {
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

if ($null -eq $researchState) {

    $stateCode =
        "`r`n    const [researchOutput, setResearchOutput] = useState<unknown>(null);`r`n"

    $app =
        $app.Insert(
            $appBrace + 1,
            $stateCode
        )

    $researchState =
        [PSCustomObject]@{
            Value  = 'researchOutput'
            Setter = 'setResearchOutput'
        }
}

Write-Host "    Directive state : $($directiveState.Value)"
Write-Host "    Research state  : $($researchState.Value)"

# ============================================================

Write-Host '[6/11] AuraJarvisBridge modülü yazılıyor...'

Write-Utf8 `
    -Path $BridgePath `
    -Text $Bridge

# ============================================================

Write-Host '[7/11] return(...) balanced-parenthesis sınırı bulunuyor...'

$appBrace =
    Find-AppFunction `
        $app

$return =
    Find-AppReturn `
        -Text $app `
        -AppBrace $appBrace

if ($null -eq $return) {
    Fail 'App return(...) balanced sınırları bulunamadı.'
}

Write-Host "    return( : $($return.Open)"
Write-Host "    return) : $($return.Close)"

#
# Import.
#

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
# return(...) sınırları import sonrasında değişmiş olabileceği için
# TEKRAR hesaplanır.
#

$appBrace =
    Find-AppFunction `
        $app

$return =
    Find-AppReturn `
        -Text $app `
        -AppBrace $appBrace

if ($null -eq $return) {
    Fail 'Import sonrası return(...) yeniden bulunamadı.'
}

#
# Bridge markup.
#

$bridgeMarkup = @"
        <AuraJarvisBridge
            directive={$($directiveState.Value)}
            researchOutput={$($researchState.Value)}
        />
"@

#
# return(
#
#   <>
#
#      EXISTING JSX
#
#      BRIDGE
#
#   </>
#
# )
#
# şeklinde sarılır.
#
# Kritik nokta:
# Bridge hiçbir JSX root'un "içine" parser ile sokulmuyor.
# return expression'ın tamamı Fragment içine alınıyor.
#

$before =
    $app.Substring(
        0,
        $return.Open + 1
    )

$body =
    $app.Substring(
        $return.Open + 1,
        $return.Close - $return.Open - 1
    )

$after =
    $app.Substring(
        $return.Close
    )

#
# Önce body'nin zaten bizim bridge'i içermediğini doğrula.
#

if (
    $body.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -ge 0
) {

    $body =
        [regex]::Replace(
            $body,
            '(?s)\s*<AuraJarvisBridge\b.*?\/>\s*',
            "`r`n"
        )
}

$newBody =
    "`r`n        <>`r`n" +
    $body.Trim() +
    "`r`n`r`n" +
    $bridgeMarkup.TrimEnd() +
    "`r`n        </>`r`n    "

$app =
    $before +
    $newBody +
    $after

# ============================================================

Write-Host '[8/11] App.tsx balanced return validation...'

$appBrace =
    Find-AppFunction `
        $app

if ($appBrace -lt 0) {
    Fail 'Patched App() bulunamadı.'
}

$returnCheck =
    Find-AppReturn `
        -Text $app `
        -AppBrace $appBrace

if ($null -eq $returnCheck) {
    Fail 'Patched return(...) dengesi bozuk.'
}

$bridgeIndex =
    $app.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if ($bridgeIndex -lt 0) {
    Fail 'AuraJarvisBridge invocation bulunamadı.'
}

if (
    $bridgeIndex -le $returnCheck.Open -or
    $bridgeIndex -ge $returnCheck.Close
) {
    Fail 'AuraJarvisBridge return(...) dışında.'
}

$fragmentOpen =
    $app.IndexOf(
        '<>',
        $returnCheck.Open
    )

$fragmentClose =
    $app.LastIndexOf(
        '</>',
        $returnCheck.Close
    )

if (
    $fragmentOpen -lt 0 -or
    $fragmentOpen -gt $bridgeIndex
) {
    Fail 'Fragment opening bulunamadı.'
}

if (
    $fragmentClose -lt $bridgeIndex -or
    $fragmentClose -ge $returnCheck.Close
) {
    Fail 'Fragment closing bulunamadı.'
}

#
# Eski hardcoded cümle kontrolü.
#

if (
    $app.IndexOf(
        'Elbette. Araştırmayı tamamladım.',
        [System.StringComparison]::OrdinalIgnoreCase
    ) -ge 0
) {
    Fail 'Eski hardcoded assistant reply kaldı.'
}

Write-Host '    return(...) balanced       : PASS'
Write-Host '    Fragment wrapper           : PASS'
Write-Host '    AuraJarvisBridge position  : PASS'

# ============================================================

Write-Host '[9/11] App.tsx + Bridge yazılıyor...'

Write-Utf8 `
    -Path $AppPath `
    -Text $app

# ============================================================

Write-Host '[10/11] FastAPI backend target + graceful Ollama...'

try {

    $backend =
        Patch-Backend `
            -Path $ApiPath

    Write-Host "    Backend target : @$($backend.Target)"

}
catch {

    Write-Host ''
    Write-Host 'Backend patch başarısız - frontend rollback...' -ForegroundColor Red

    Restore-File `
        -Backup (
            Join-Path `
                $BackupDir `
                'aura-ui\src\App.tsx'
        ) `
        -Destination $AppPath

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
    else {

        if (Test-Path -LiteralPath $BridgePath) {
            Remove-Item `
                -LiteralPath $BridgePath `
                -Force
        }
    }

    throw
}

# ============================================================

Write-Host '[11/11] Python + TypeScript/Vite validation...'

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

Push-Location $UiRoot

try {

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
        throw 'npm bulunamadı.'
    }

    & $npm.Source run build

    $buildCode =
        $LASTEXITCODE

}
catch {

    $buildCode = 1
    Write-Host $_.Exception.Message -ForegroundColor Red

}
finally {

    Pop-Location
}

if ($buildCode -ne 0) {

    Write-Host ''
    Write-Host 'BUILD FAILED - rollback...' -ForegroundColor Red

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

    Fail 'npm run build başarısız; değişiklikler rollback edildi.'
}

# ============================================================
# FINAL VALIDATION
# ============================================================

$finalApp =
    Read-Utf8 $AppPath

$finalBridge =
    Read-Utf8 $BridgePath

$finalBrace =
    Find-AppFunction `
        $finalApp

$finalReturn =
    Find-AppReturn `
        -Text $finalApp `
        -AppBrace $finalBrace

if ($null -eq $finalReturn) {
    Fail 'Final return(...) validation başarısız.'
}

$finalBridgeIndex =
    $finalApp.IndexOf(
        '<AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    )

if (
    $finalBridgeIndex -le $finalReturn.Open -or
    $finalBridgeIndex -ge $finalReturn.Close
) {
    Fail 'Final AuraJarvisBridge return(...) içinde değil.'
}

if (
    $finalBridge.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Frontend -> assistant endpoint bağlantısı bulunamadı.'
}

if (
    $finalBridge.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS queue bulunamadı.'
}

foreach ($forbidden in @(
    'speakAssistantReply(directive)',
    'speakAssistantReply(researchOutput)',
    'speakAssistantReply(step.result)',
    'speechSynthesis.speak(directive)',
    'speechSynthesis.speak(researchOutput)',
    'speechSynthesis.speak(step.result)'
)) {

    if (
        $finalBridge.IndexOf(
            $forbidden,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        Fail "Ham veri TTS bağlantısı bulundu: $forbidden"
    }
}

$apiFinal =
    Read-Utf8 $ApiPath

if (
    $apiFinal -notmatch
    '/api/assistant/respond'
) {
    Fail 'Backend /api/assistant/respond bulunamadı.'
}

if (
    $apiFinal -notmatch
    'local-offline'
) {
    Fail 'Ollama graceful-degradation branch bulunamadı.'
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.5 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App() discovery              : PASS'
Write-Host 'return(...) balanced scan    : PASS'
Write-Host 'Fragment wrapping            : PASS'
Write-Host 'AuraJarvisBridge placement   : PASS'
Write-Host 'Hardcoded reply removal      : PASS'
Write-Host 'Raw step.result -> TTS       : BLOCKED'
Write-Host 'Directive -> TTS             : BLOCKED'
Write-Host 'Assistant reply -> TTS       : PASS'
Write-Host 'FastAPI target discovery     : PASS'
Write-Host 'Assistant endpoint           : PASS'
Write-Host 'Ollama offline fallback      : PASS'
Write-Host 'Python compile               : PASS'
Write-Host 'npm run build                : PASS'
Write-Host ''
Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''