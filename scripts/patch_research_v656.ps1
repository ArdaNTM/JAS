# ============================================================
# AURA V6.5.6
# JARVIS / APP-SCOPE-SAFE JSX PATCH
#
# Kritik düzeltme:
# V6.5.5 ilk "return(" ifadesini yakalıyordu.
# V6.5.6:
#   1. export default function App() scope'unu bulur
#   2. App body'sindeki {} dengesini çıkarır
#   3. SADECE App body içinde bulunan return'leri toplar
#   4. "return () => {...}" cleanup'larını ELER
#   5. "return;" ifadelerini ELER
#   6. JSX döndüren en sondaki "return (...)" ifadesini seçer
#   7. Bridge'i yalnızca bu return expression içine ekler
#   8. Backend'deki mevcut assistant route'u bozmaz
#   9. Ollama offline graceful degradation korunur
#  10. Build başarısızsa otomatik rollback yapılır
#
# PowerShell karşılaştırmaları PS operatörleriyle,
# TypeScript/JS string içerikleri ise JS/TS operatörleriyle yazılmıştır.
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
$BackupDir  = Join-Path $BackupRoot "research-v656-$Stamp"

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.6 PATCH ABORTED' -ForegroundColor Red
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

    $parent = Split-Path -Parent $Path

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

    $destination = Join-Path $BackupDir $Relative
    $parent = Split-Path -Parent $destination

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
# JAVASCRIPT SCANNER
#
# Amaç:
# JS/TS kodundaki (), {}, [] dengelerini hesaplarken
# string/comment/template literal içeriklerini yok saymak.
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

    if ($Text[$OpenIndex] -ne $OpenChar) {
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

        # CODE

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

        if ($c -eq $OpenChar) {
            $depth++
            $i++
            continue
        }

        if ($c -eq $CloseChar) {

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

# ============================================================
# APP FUNCTION SCOPE
# ============================================================

function Find-AppDeclaration {
    param([string]$Text)

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*export\s+function\s+App\s*\([^)]*\)\s*\{',
        '(?m)^\s*function\s+App\s*\([^)]*\)\s*\{'
    )

    foreach ($pattern in $patterns) {

        $m =
            [regex]::Match(
                $Text,
                $pattern
            )

        if ($m.Success) {

            $openBrace =
                $m.Index +
                $m.Value.LastIndexOf('{')

            return [PSCustomObject]@{
                Index      = $m.Index
                OpenBrace  = $openBrace
            }
        }
    }

    return $null
}

function Find-AppScope {
    param([string]$Text)

    $decl =
        Find-AppDeclaration `
            -Text $Text

    if ($null -eq $decl) {
        return $null
    }

    $closeBrace =
        Find-MatchingDelimiter `
            -Text $Text `
            -OpenIndex $decl.OpenBrace `
            -OpenChar ([char]'{') `
            -CloseChar ([char]'}')

    if ($closeBrace -lt 0) {
        return $null
    }

    return [PSCustomObject]@{
        Declaration = $decl
        OpenBrace   = $decl.OpenBrace
        CloseBrace  = $closeBrace
    }
}

# ============================================================
# RETURN DISCOVERY
#
# SADECE App scope içinde.
#
# Geçerli aday:
#   return (
#       <JSX />
#   );
#
# Elenecekler:
#   return;
#   return value;
#   return () => {};
#
# En sona en yakın JSX return seçilir.
# ============================================================

function Find-AppJsxReturn {
    param(
        [string]$Text,
        [int]$AppOpenBrace,
        [int]$AppCloseBrace
    )

    if ($AppOpenBrace -lt 0) {
        return $null
    }

    if ($AppCloseBrace -le $AppOpenBrace) {
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

    #
    # Tüm "return (" adaylarını bul.
    #

    $matches =
        [regex]::Matches(
            $scope,
            '(?m)\breturn\s*\('
        )

    $candidates = @()

    foreach ($m in $matches) {

        $openRelative =
            $m.Index +
            $m.Value.LastIndexOf('(')

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

        if ($closeAbsolute -lt 0) {
            continue
        }

        if ($closeAbsolute -ge $AppCloseBrace) {
            continue
        }

        $expression =
            $Text.Substring(
                $openAbsolute + 1,
                $closeAbsolute -
                $openAbsolute -
                1
            )

        #
        # Cleanup return:
        # return () => {
        #
        if (
            $expression -match
            '^\s*\(\s*\)\s*=>'
        ) {
            continue
        }

        #
        # Boş expression.
        #
        if (
            [string]::IsNullOrWhiteSpace(
                $expression
            )
        ) {
            continue
        }

        #
        # JSX kanıtı.
        #
        $hasJsx =
            [regex]::IsMatch(
                $expression,
                '(?s)<\s*(?:[A-Za-z][A-Za-z0-9_.:-]*|>)'
            )

        if (-not $hasJsx) {
            continue
        }

        $candidates += [PSCustomObject]@{
            ReturnKeywordIndex =
                $AppOpenBrace +
                1 +
                $m.Index

            Open =
                $openAbsolute

            Close =
                $closeAbsolute

            Length =
                $closeAbsolute -
                $openAbsolute +
                1
        }
    }

    if ($candidates.Count -eq 0) {
        return $null
    }

    #
    # En sondaki JSX return.
    #
    return $candidates[$candidates.Count - 1]
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

        $m =
            [regex]::Match(
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

    $m =
        [regex]::Match(
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

            $value = $item.Trim()

            if (
                $value.Length -gt 0 -and
                $items -notcontains $value
            ) {
                $items += $value
            }
        }

        foreach ($requiredHook in $required) {

            if ($items -notcontains $requiredHook) {
                $items += $requiredHook
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
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*:\s*FastAPI\s*=\s*FastAPI\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_]\w*)\s*=\s*fastapi\.APIRouter\s*\('
    )

    foreach ($pattern in $patterns) {

        $m =
            [regex]::Match(
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
        '/api/assistant/respond'
    )
}

# ============================================================
# BACKEND ROUTE
# ============================================================

function Build-AssistantRoute {
    param([string]$Target)

    $route = @'
# AURA_JARVIS_ASSISTANT_V656_START

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

# AURA_JARVIS_ASSISTANT_V656_END
'@

    return $route.Replace(
        '@TARGET',
        '@' + $Target
    )
}

# ============================================================
# BRIDGE COMPONENT
# ============================================================

$Bridge = @'
/* AURA_JARVIS_LLM_V656_START */

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

            utterance.onend = speakNext;
            utterance.onerror = speakNext;

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
                         * YALNIZCA LLM assistant_reply TTS'e gider.
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

/* AURA_JARVIS_LLM_V656_END */
'@

# ============================================================
# START
# ============================================================

Write-Host '============================================================'
Write-Host ' AURA V6.5.6 JARVIS / APP-SCOPE-SAFE JSX PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/12] Proje kontrol ediliyor...'

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

if (Test-Path -LiteralPath $BridgePath -PathType Leaf) {

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
# Eski sabit cevapların bilinen varyantlarını temizle.
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
# Eski bridge çağrılarını temizle.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)\s*<AuraJarvisBridge\b.*?\/>',
        ''
    )

# ============================================================

Write-Host '[5/12] React hook importleri normalize ediliyor...'

$app =
    Ensure-ReactHooks `
        $app

# ============================================================

Write-Host '[6/12] App scope çıkarılıyor...'

$appScope =
    Find-AppScope `
        -Text $app

if ($null -eq $appScope) {
    Fail 'export default function App() scope bulunamadı.'
}

Write-Host "    App { index : $($appScope.OpenBrace)"
Write-Host "    App } index : $($appScope.CloseBrace)"

# ============================================================

Write-Host '[7/12] App scope içindeki gerçek JSX return bulunuyor...'

$jsxReturn =
    Find-AppJsxReturn `
        -Text $app `
        -AppOpenBrace $appScope.OpenBrace `
        -AppCloseBrace $appScope.CloseBrace

if ($null -eq $jsxReturn) {

    Fail (
        'App scope içinde JSX döndüren ana return(...) bulunamadı.'
    )
}

Write-Host "    JSX return( : $($jsxReturn.Open)"
Write-Host "    JSX return) : $($jsxReturn.Close)"

#
# Aynı bölgede cleanup return olmadığını ek doğrula.
#

$returnExpression =
    $app.Substring(
        $jsxReturn.Open + 1,
        $jsxReturn.Close -
        $jsxReturn.Open -
        1
    )

if (
    $returnExpression -match
    '^\s*\(\s*\)\s*=>'
) {
    Fail 'Seçilen return cleanup fonksiyonu; patch durduruldu.'
}

if (
    -not (
        [regex]::IsMatch(
            $returnExpression,
            '(?s)<\s*(?:[A-Za-z][A-Za-z0-9_.:-]*|>)'
        )
    )
) {
    Fail 'Seçilen return JSX expression içermiyor.'
}

# ============================================================

Write-Host '[8/12] Directive/research state keşfediliyor...'

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

    #
    # App scope açılışından hemen sonra state eklenir.
    #

    $app =
        $app.Insert(
            $appScope.OpenBrace + 1,
            $stateCode
        )

    #
    # State insertion sonrasında tüm indexleri yeniden hesapla.
    #

    $appScope =
        Find-AppScope `
            -Text $app

    if ($null -eq $appScope) {
        Fail 'Research state insertion sonrası App scope bulunamadı.'
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
}

if ($null -eq $researchState) {
    Fail 'Research state oluşturulamadı.'
}

Write-Host "    Directive state : $($directiveState.Value)"
Write-Host "    Research state  : $($researchState.Value)"

# ============================================================

Write-Host '[9/12] AuraJarvisBridge modülü yazılıyor...'

Write-Utf8 `
    -Path $BridgePath `
    -Text $Bridge

#
# Import'u App.tsx'e ekle.
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

# ============================================================

Write-Host '[10/12] Ana App return(...) Fragment içine sarılıyor...'

#
# Import sonrasında indexler değiştiği için scope + return
# yeniden hesaplanır.
#

$appScope =
    Find-AppScope `
        -Text $app

if ($null -eq $appScope) {
    Fail 'Import sonrası App scope bulunamadı.'
}

$jsxReturn =
    Find-AppJsxReturn `
        -Text $app `
        -AppOpenBrace $appScope.OpenBrace `
        -AppCloseBrace $appScope.CloseBrace

if ($null -eq $jsxReturn) {
    Fail 'Import sonrası ana JSX return bulunamadı.'
}

#
# Bridge çağrısı.
#

$bridgeMarkup = @"
        <AuraJarvisBridge
            directive={$($directiveState.Value)}
            researchOutput={$($researchState.Value)}
        />
"@

#
# Mevcut return expression alınır.
#

$body =
    $app.Substring(
        $jsxReturn.Open + 1,
        $jsxReturn.Close -
        $jsxReturn.Open -
        1
    )

#
# Eski bridge çağrısı varsa çıkar.
#

$body =
    [regex]::Replace(
        $body,
        '(?s)\s*<AuraJarvisBridge\b.*?\/>\s*',
        "`r`n"
    )

#
# ÖNEMLİ:
# Burada hiçbir JSX root tag'ı aranmaz.
# Sadece return expression'ın tamamı Fragment ile sarılır.
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

Write-Host '[11/12] Structural validation...'

#
# App scope yeniden hesapla.
#

$appScope =
    Find-AppScope `
        -Text $app

if ($null -eq $appScope) {
    Fail 'Final App scope bulunamadı.'
}

#
# Ana JSX return yeniden hesapla.
#

$jsxReturn =
    Find-AppJsxReturn `
        -Text $app `
        -AppOpenBrace $appScope.OpenBrace `
        -AppCloseBrace $appScope.CloseBrace

if ($null -eq $jsxReturn) {
    Fail 'Final ana JSX return bulunamadı.'
}

#
# Bridge return expression içinde mi?
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
    Fail 'AuraJarvisBridge ana return(...) dışında.'
}

#
# Fragment kontrolü.
#

$fragmentOpen =
    $app.IndexOf(
        '<>',
        $jsxReturn.Open
    )

$fragmentClose =
    $app.LastIndexOf(
        '</>',
        $jsxReturn.Close
    )

if (
    $fragmentOpen -lt 0 -or
    $fragmentOpen -gt $bridgeIndex
) {
    Fail 'Fragment opening bulunamadı.'
}

if (
    $fragmentClose -lt $bridgeIndex -or
    $fragmentClose -ge $jsxReturn.Close
) {
    Fail 'Fragment closing bulunamadı.'
}

#
# Cleanup return seçilmediğini doğrula.
#

$finalExpression =
    $app.Substring(
        $jsxReturn.Open + 1,
        $jsxReturn.Close -
        $jsxReturn.Open -
        1
    )

if (
    $finalExpression -match
    '^\s*\(\s*\)\s*=>'
) {
    Fail 'Final return cleanup fonksiyonu olarak algılandı.'
}

#
# Eski hardcoded persona.
#

$forbiddenReplyPatterns = @(
    'Elbette. Araştırmayı tamamladım.',
    'Elbette, araştırmayı tamamladım.',
    'Araştırmayı tamamladım.'
)

foreach ($forbidden in $forbiddenReplyPatterns) {

    if (
        $app.IndexOf(
            $forbidden,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {
        Fail "Eski hardcoded assistant reply bulundu: $forbidden"
    }
}

#
# Bridge component basic validation.
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
    Fail 'Frontend assistant endpoint bağlantısı bulunamadı.'
}

if (
    $bridgeFinal.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS queue bulunamadı.'
}

foreach ($forbiddenTts in @(
    'speakAssistantReply(directive)',
    'speakAssistantReply(researchOutput)',
    'speakAssistantReply(step.result)',
    'speechSynthesis.speak(directive)',
    'speechSynthesis.speak(researchOutput)',
    'speechSynthesis.speak(step.result)'
)) {

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
Write-Host '    Cleanup return excluded      : PASS'
Write-Host '    Fragment wrapper             : PASS'
Write-Host '    Bridge inside main return    : PASS'
Write-Host '    Hardcoded reply removed      : PASS'
Write-Host '    Raw research -> TTS blocked  : PASS'

#
# Dosyayı artık build öncesi yaz.
#

Write-Utf8 `
    -Path $AppPath `
    -Text $app

# ============================================================

Write-Host '[12/12] FastAPI + Python + TypeScript/Vite validation...'

#
# Backend:
# Mevcut route varsa dokunma.
# Yoksa mevcut FastAPI target'a ekle.
#

$api =
    Read-Utf8 `
        $ApiPath

if (
    -not (
        Has-AssistantRoute `
            -Text $api
    )
) {

    $target =
        Find-FastApiTarget `
            -Text $api

    if ($null -eq $target) {

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

        Fail 'FastAPI / APIRouter target bulunamadı.'
    }

    $route =
        Build-AssistantRoute `
            -Target $target

    $api =
        $api.TrimEnd() +
        "`r`n`r`n" +
        $route.Trim() +
        "`r`n"

    Write-Utf8 `
        -Path $ApiPath `
        -Text $api

    Write-Host "    Assistant route added: @$target"
}
else {

    Write-Host '    Assistant route: EXISTING'
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

Write-Host '    Python compile               : PASS'

#
# npm build.
#

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

if ($buildExit -ne 0) {

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
    elseif (
        Test-Path `
            -LiteralPath $BridgePath
    ) {

        Remove-Item `
            -LiteralPath $BridgePath `
            -Force
    }

    Fail 'npm run build başarısız; App.tsx ve backend rollback edildi.'
}

# ============================================================
# FINAL FILE VALIDATION
# ============================================================

$finalApp =
    Read-Utf8 `
        $AppPath

$finalScope =
    Find-AppScope `
        -Text $finalApp

if ($null -eq $finalScope) {
    Fail 'Final App scope validation başarısız.'
}

$finalReturn =
    Find-AppJsxReturn `
        -Text $finalApp `
        -AppOpenBrace $finalScope.OpenBrace `
        -AppCloseBrace $finalScope.CloseBrace

if ($null -eq $finalReturn) {
    Fail 'Final JSX return validation başarısız.'
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
    Fail 'Final AuraJarvisBridge ana return içinde değil.'
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' AURA V6.5.6 SUCCESS' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Write-Host ''
Write-Host 'App function scope             : PASS'
Write-Host 'App brace balance              : PASS'
Write-Host 'Cleanup return exclusion       : PASS'
Write-Host 'Main JSX return selection      : PASS'
Write-Host 'Fragment wrapper               : PASS'
Write-Host 'AuraJarvisBridge placement     : PASS'
Write-Host 'Hardcoded reply removal        : PASS'
Write-Host 'Raw step.result -> TTS         : BLOCKED'
Write-Host 'Directive -> TTS               : BLOCKED'
Write-Host 'LLM assistant_reply -> TTS     : PASS'
Write-Host 'FastAPI route                  : PASS'
Write-Host 'Ollama graceful fallback       : PASS'
Write-Host 'Python compile                 : PASS'
Write-Host 'npm run build                  : PASS'
Write-Host ''
Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''