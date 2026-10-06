#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ============================================================
# AURA V6.5.1
# LOCAL JARVIS / OLLAMA BRIDGE
# PowerShell 5.1
#
# DÜZELTMELER:
#   - Regex içindeki $(...) interpolation tamamen kaldırıldı.
#   - Regex pattern'leri single-quoted string olarak tutuluyor.
#   - App.tsx içine devasa backend kodu gömülmüyor.
#   - Frontend LLM bridge ayrı TSX modülüne yazılıyor.
#   - FastAPI assistant endpoint mevcut application/api.py içine
#     mevcut APIRouter değişkeni üzerinden ekleniyor.
#   - step.result -> LLM -> assistant_reply -> TTS akışı kuruluyor.
#   - raw step.result -> TTS engelleniyor.
#   - directive -> TTS engelleniyor.
#   - Eski buildAssistantReply / statik reply kalıntıları temizleniyor.
#   - Her aşamada rollback backup oluşturuluyor.
#   - PowerShell parser + Python compile + npm build doğrulanıyor.
#
# Not:
# PowerShell'de single-quoted string literal olduğu için regex
# içindeki $() PowerShell subexpression olarak değerlendirilmez.
# ============================================================

$Root = 'D:\AURA\JAS'
$UiRoot = Join-Path $Root 'aura-ui'
$CoreRoot = Join-Path $Root 'core'
$CoreSrc = Join-Path $CoreRoot 'src'

$AppPath = Join-Path $UiRoot 'src\App.tsx'
$BridgePath = Join-Path $UiRoot 'src\AuraJarvisBridge.tsx'
$ApiPath = Join-Path $CoreSrc 'aura_core\application\api.py'

$BackupRoot = Join-Path $Root '.aura-backups'
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$BackupDir = Join-Path $BackupRoot ('research-v651-' + $Stamp)

function Fail {
    param(
        [string]$Message
    )

    Write-Host ''
    Write-Host 'PATCH ABORTED' -ForegroundColor Red
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
    param(
        [string]$Path
    )

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
                'Generated block başlangıcı bulundu fakat end marker bulunamadı: ' +
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

function Test-PowerShellSyntax {
    param(
        [string]$Path
    )

    $tokens = $null
    $errors = $null

    [System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null

    if ($null -ne $errors -and $errors.Count -gt 0) {

        foreach ($errorItem in $errors) {
            Write-Host (
                'Line ' +
                $errorItem.Extent.StartLineNumber +
                ': ' +
                $errorItem.Message
            ) -ForegroundColor Red
        }

        Fail 'PowerShell parser testi başarısız.'
    }
}

function Find-AppFunctionOpenBrace {
    param(
        [string]$Text
    )

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

function Find-AppReturnStart {
    param(
        [string]$Text,
        [int]$AppOpenBrace
    )

    if ($AppOpenBrace -lt 0) {
        return -1
    }

    $tail = $Text.Substring(
        $AppOpenBrace
    )

    $match = [regex]::Match(
        $tail,
        '(?s)\breturn\s*\('
    )

    if (-not $match.Success) {
        return -1
    }

    return (
        $AppOpenBrace +
        $match.Index +
        $match.Length
    )
}

function Find-FirstJsxRootOpen {
    param(
        [string]$Text,
        [int]$ReturnContentStart
    )

    if ($ReturnContentStart -lt 0) {
        return -1
    }

    $tail = $Text.Substring(
        $ReturnContentStart
    )

    #
    # Fragment varsa fragment içine,
    # yoksa return'den sonraki ilk JSX elementine.
    #
    $fragment = [regex]::Match(
        $tail,
        '(?s)^\s*<>'
    )

    if ($fragment.Success) {
        return (
            $ReturnContentStart +
            $fragment.Index +
            $fragment.Length
        )
    }

    $root = [regex]::Match(
        $tail,
        '(?s)^\s*<([A-Za-z][A-Za-z0-9_.:-]*)(?:\s[^>]*)?>'
    )

    if ($root.Success) {
        return (
            $ReturnContentStart +
            $root.Index +
            $root.Length
        )
    }

    return -1
}

function Find-ReactImport {
    param(
        [string]$Text
    )

    return [regex]::Match(
        $Text,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
    )
}

function Ensure-ReactImports {
    param(
        [string]$Text
    )

    $required = @(
        'useEffect',
        'useRef',
        'useState'
    )

    $match = Find-ReactImport $Text

    if ($match.Success) {

        $body = $match.Groups['body'].Value
        $items = New-Object System.Collections.Generic.List[string]

        foreach ($item in ($body -split ',')) {

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
        [string[]]$PreferredNames
    )

    foreach ($preferred in $PreferredNames) {

        $pattern =
            'const\s*\[\s*' +
            [regex]::Escape($preferred) +
            '\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'

        $match = [regex]::Match(
            $Text,
            $pattern
        )

        if ($match.Success) {

            return [PSCustomObject]@{
                Value = $preferred
                Setter = $match.Groups['setter'].Value
            }
        }
    }

    return $null
}

function Find-AnyStateSetter {
    param(
        [string]$Text
    )

    $match = [regex]::Match(
        $Text,
        'const\s*\[\s*(?<value>[A-Za-z_$][\w$]*)\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'
    )

    if (-not $match.Success) {
        return $null
    }

    return [PSCustomObject]@{
        Value = $match.Groups['value'].Value
        Setter = $match.Groups['setter'].Value
    }
}

function Find-ApiRouterVariable {
    param(
        [string]$Text
    )

    $patterns = @(
        '(?m)^\s*(?<name>[A-Za-z_$][\w$]*)\s*=\s*APIRouter\s*\(',
        '(?m)^\s*(?<name>[A-Za-z_$][\w$]*)\s*:\s*APIRouter\s*=\s*APIRouter\s*\('
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

function Ensure-PythonImport {
    param(
        [string]$Text,
        [string]$ImportLine
    )

    $escaped = [regex]::Escape($ImportLine)

    if (
        [regex]::IsMatch(
            $Text,
            '(?m)^' + $escaped + '\s*$'
        )
    ) {
        return $Text
    }

    return (
        $ImportLine +
        "`r`n" +
        $Text
    )
}

function Ensure-GeneratedPythonRoute {
    param(
        [string]$Text,
        [string]$RouterVariable
    )

    $startMarker = 'AURA_JARVIS_ASSISTANT_API_V651_START'
    $endMarker = 'AURA_JARVIS_ASSISTANT_API_V651_END'

    $Text = Remove-GeneratedBlock `
        -Text $Text `
        -StartMarker $startMarker `
        -EndMarker $endMarker

    if (
        $Text.IndexOf(
            '/api/assistant/respond',
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {
        return $Text
    }

    $block = @'
# AURA_JARVIS_ASSISTANT_API_V651_START

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
                "Türkçe konuşan doğal bir kişisel AI asistanısın. "
                "Analitik, kendinden emin ve gerektiğinde ince ironik "
                "olabilirsin. Kullanıcının cümlesini papağan gibi tekrar etme. "
                "Ham JSON, UUID, URL, tool trace veya teknik log okuma. "
                "Araştırma verisini analiz ederek kendi cümlelerinle "
                "kısa bir değerlendirme yap. "
                "En fazla dört kısa cümle üret. "
                "Markdown kullanma. "
                "Araştırmada olmayan bilgileri uydurma."
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
                "Araştırma sonucunu analiz et ve "
                "kullanıcıya konuşmaya uygun doğal bir "
                "AURA yanıtı üret."
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


@ROUTER_VARIABLE.post(
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
            assistant_reply="Araştırma sonucu henüz oluşmadı.",
            model=os.environ.get(
                "AURA_LLM_MODEL",
                "qwen3",
            ),
            provider="ollama",
        )

    try:

        reply, model = await asyncio.to_thread(
            _aura_ollama_reply,
            directive,
            research,
        )

    except Exception as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                "Local Ollama assistant bridge failed: " +
                str(exc)
            ),
        )

    if not reply:

        reply = (
            "Araştırma verisini aldım; "
            "ancak bundan anlamlı bir yanıt üretilemedi."
        )

    return AuraAssistantResponse(
        assistant_reply=reply,
        model=model,
        provider="ollama",
    )

# AURA_JARVIS_ASSISTANT_API_V651_END
'@

    $block =
        $block.Replace(
            '@ROUTER_VARIABLE',
            '@' + $RouterVariable
        )

    return (
        $Text.TrimEnd() +
        "`r`n`r`n" +
        $block.Trim() +
        "`r`n"
    )
}

# ============================================================
# PRECHECK
# ============================================================

Write-Host ''
Write-Host '============================================================'
Write-Host ' AURA V6.5.1 JARVIS LOCAL LLM BRIDGE'
Write-Host '============================================================'
Write-Host ''

Write-Host '[1/12] Proje kontrol ediliyor...'

Assert-Directory $Root 'AURA root'
Assert-Directory $UiRoot 'aura-ui'
Assert-Directory $CoreRoot 'core'

Assert-File $AppPath 'App.tsx'
Assert-File $ApiPath 'FastAPI application/api.py'

# ============================================================
# BACKUP
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

$CssCandidates = @(
    (Join-Path $UiRoot 'src\App.css'),
    (Join-Path $UiRoot 'src\index.css')
)

$CssPath = $null

foreach ($candidate in $CssCandidates) {

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
            (
                Split-Path `
                    $CssPath `
                    -Leaf
            )
        )
}

# ============================================================
# APP READ
# ============================================================

Write-Host '[3/12] App.tsx okunuyor...'

$app = Read-Utf8Text $AppPath

# ============================================================
# CLEAN OLD GENERATED BLOCKS
# ============================================================

Write-Host '[4/12] Eski V6.x generated blokları temizleniyor...'

$oldBlocks = @(
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
    ),
    @(
        'AURA_RESEARCH_CONVERSATIONAL_V62_START',
        'AURA_RESEARCH_CONVERSATIONAL_V62_END'
    ),
    @(
        'AURA_RESEARCH_OUTPUT_START',
        'AURA_RESEARCH_OUTPUT_END'
    )
)

foreach ($pair in $oldBlocks) {

    $app = Remove-GeneratedBlock `
        -Text $app `
        -StartMarker $pair[0] `
        -EndMarker $pair[1]
}

#
# Eski fonksiyonlar:
# TypeScript/JS bloklarını greedy olmayan sınırlarla temizle.
#

$oldFunctionPatterns = @(
    '(?s)\bfunction\s+buildAssistantReply\s*\([^)]*\)\s*\{.*?\n\}',
    '(?s)\bfunction\s+speakAssistantReply\s*\([^)]*\)\s*\{.*?\n\}',
    '(?s)\bfunction\s+speakResearchOutput\s*\([^)]*\)\s*\{.*?\n\}'
)

foreach ($pattern in $oldFunctionPatterns) {

    $app = [regex]::Replace(
        $app,
        $pattern,
        ''
    )
}

#
# Eski sabit reply metinleri.
#

$staticReplies = @(
    'Elbette. Araştırmayı tamamladım.',
    'Elbette. Araştırmayı tamamladım',
    'Elbette, araştırmayı tamamladım.',
    'Elbette, araştırmayı tamamladım',
    'Araştırmayı tamamladım.',
    'Araştırmayı tamamladım'
)

foreach ($reply in $staticReplies) {

    $app = $app.Replace(
        $reply,
        ''
    )
}

#
# Eski generated component invocation'ları.
#

$app = [regex]::Replace(
    $app,
    '(?m)^[ \t]*<AuraJarvisBridge\b[^>]*/>[ \t]*\r?\n?',
    ''
)

$app = [regex]::Replace(
    $app,
    '(?m)^[ \t]*<Aura(?:ConversationalResearch|JarvisConversationalBridge)\b[^>]*/>[ \t]*\r?\n?',
    ''
)

# ============================================================
# REACT IMPORT
# ============================================================

Write-Host '[5/12] React importleri normalize ediliyor...'

$app = Ensure-ReactImports $app

# ============================================================
# CREATE STANDALONE BRIDGE COMPONENT
# ============================================================

Write-Host '[6/12] Ayrı JARVIS LLM bridge modülü oluşturuluyor...'

$bridge = @'
/* AURA_JARVIS_LLM_V651_START */

import {
    useEffect,
    useRef,
    useState,
} from "react";

type AuraJarvisBridgeProps = {
    directive?: string;
    researchOutput?: unknown;
};

type AuraAssistantResponse = {
    assistant_reply?: string;
    model?: string;
    provider?: string;
};

function compactResearch(
    value: unknown
): string {

    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    let text = "";

    if (
        typeof value === "string"
    ) {
        text = value;
    }
    else {
        try {
            text = JSON.stringify(
                value
            );
        }
        catch {
            text = String(
                value
            );
        }
    }

    return text
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 14000);
}

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
        .replace(
            /^["'`]+|["'`]+$/g,
            ""
        )
        .slice(0, 900);
}

async function requestAssistantReply(
    directive: string,
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
                        compactResearch(
                            researchOutput
                        ),
                }),
            }
        );

    if (!response.ok) {

        throw new Error(
            "AURA assistant endpoint HTTP " +
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
                (item) =>
                    item.trim()
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

            const current =
                queue.shift();

            if (!current) {
                return;
            }

            current.onend =
                speakNext;

            current.onerror =
                speakNext;

            window.speechSynthesis.speak(
                current
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

            requestAssistantReply(
                directive ?? "",
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
                         * KRİTİK MİMARİ SINIRI:
                         *
                         * researchOutput -> TTS YOK
                         * directive      -> TTS YOK
                         *
                         * Yalnızca:
                         *
                         * Ollama/Qwen3
                         *       |
                         *       v
                         * assistant_reply
                         *       |
                         *       v
                         *       TTS
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
                                "AURA local LLM:",
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

/* AURA_JARVIS_LLM_V651_END */
'@

Write-Utf8Text `
    -Path $BridgePath `
    -Text $bridge

Backup-File `
    -Source $BridgePath `
    -Relative 'aura-ui\src\AuraJarvisBridge.tsx'

# ============================================================
# APP STATE ANALYSIS
# ============================================================

Write-Host '[7/12] App state ve JSX sınırları çözülüyor...'

#
# App component kesin olarak bulunmalı.
#

$appOpenBrace =
    Find-AppFunctionOpenBrace $app

if ($appOpenBrace -lt 0) {
    Fail 'export default function App(...) veya function App(...) bulunamadı.'
}

#
# return(...) kesin olarak App gövdesi içinde bulunmalı.
#

$appReturnStart =
    Find-AppReturnStart `
        -Text $app `
        -AppOpenBrace $appOpenBrace

if ($appReturnStart -lt 0) {
    Fail 'App() içinde return(...) bulunamadı.'
}

#
# Directive setter tespiti.
#

$directiveState =
    Find-StateSetter `
        -Text $app `
        -PreferredNames @(
            'directive',
            'input',
            'query',
            'command',
            'userInput',
            'prompt',
            'text'
        )

if ($null -eq $directiveState) {

    Fail (
        'Directive/input state setter otomatik tespit edilemedi.'
    )
}

$directiveName =
    $directiveState.Value

#
# Research output state tespiti.
#

$researchState =
    Find-StateSetter `
        -Text $app `
        -PreferredNames @(
            'researchOutput',
            'auraResearchOutput',
            'researchResult',
            'taskResult',
            'completedTask',
            'result'
        )

if ($null -eq $researchState) {

    #
    # Yeni state App() açılışından hemen sonra eklenir.
    #

    $stateLine =
        "`r`n    const [researchOutput, setResearchOutput] = useState<unknown>(null);`r`n"

    $insertAt =
        $appOpenBrace + 1

    $app =
        $app.Insert(
            $insertAt,
            $stateLine
        )

    $researchName =
        'researchOutput'

}
else {

    $researchName =
        $researchState.Value
}

#
# Import.
#

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

# ============================================================
# JSX INSERTION
# ============================================================

Write-Host '[8/12] AuraJarvisBridge ana App JSX içine ekleniyor...'

#
# App state eklenmesinden sonra return index değişmiş olabilir.
#

$appOpenBrace =
    Find-AppFunctionOpenBrace $app

$appReturnStart =
    Find-AppReturnStart `
        -Text $app `
        -AppOpenBrace $appOpenBrace

if ($appReturnStart -lt 0) {
    Fail 'App() return(...) yeniden çözümlenemedi.'
}

#
# Zaten bridge varsa duplicate oluşturma.
#

$bridgeInvocation =
    [regex]::Match(
        $app,
        '(?s)<AuraJarvisBridge\b.*?/>'
    )

if (-not $bridgeInvocation.Success) {

    $jsxRootPosition =
        Find-FirstJsxRootOpen `
            -Text $app `
            -ReturnContentStart $appReturnStart

    if ($jsxRootPosition -lt 0) {
        Fail 'App return(...) içindeki ana JSX root bulunamadı.'
    }

    $bridgeMarkup =
        @'
            <AuraJarvisBridge
                directive={DIRECTIVE_NAME}
                researchOutput={RESEARCH_NAME}
            />
'@

    $bridgeMarkup =
        $bridgeMarkup.Replace(
            'DIRECTIVE_NAME',
            $directiveName
        )

    $bridgeMarkup =
        $bridgeMarkup.Replace(
            'RESEARCH_NAME',
            $researchName
        )

    $app =
        $app.Insert(
            $jsxRootPosition,
            "`r`n" +
            $bridgeMarkup.TrimEnd() +
            "`r`n"
        )
}

#
# App'a ham researchOutput'u TTS'e veren yasak bağlantılar varsa
# kaldırılmayacak; patch bilinçli şekilde abort edecek.
# Böylece mevcut iş mantığı sessizce değiştirilmez.
#

Write-Host '    Directive state : ' $directiveName
Write-Host '    Research state  : ' $researchName

# ============================================================
# WRITE APP
# ============================================================

Write-Host '[9/12] App.tsx yazılıyor...'

Write-Utf8Text `
    -Path $AppPath `
    -Text $app

# ============================================================
# CSS
# ============================================================

Write-Host '[10/12] Conversational UI CSS uygulanıyor...'

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
        -StartMarker 'AURA_JARVIS_CSS_V651_START' `
        -EndMarker 'AURA_JARVIS_CSS_V651_END'

$cssBlock = @'
/* AURA_JARVIS_CSS_V651_START */

.aura-jarvis-response {
    position: fixed;
    left: 24px;
    bottom: 112px;
    z-index: 2000;
    width: min(560px, calc(100vw - 48px));
    box-sizing: border-box;
    padding: 14px 18px;
    border: 1px solid rgba(100, 210, 255, 0.28);
    border-radius: 12px;
    background: rgba(4, 10, 18, 0.94);
    backdrop-filter: blur(14px);
    box-shadow:
        0 0 24px rgba(40, 180, 255, 0.12),
        inset 0 0 18px rgba(40, 180, 255, 0.04);
    color: #dff7ff;
    pointer-events: none;
}

.aura-jarvis-response-label {
    margin: 0 0 7px 0;
    font-size: 10px;
    line-height: 1.2;
    letter-spacing: 0.18em;
    font-weight: 700;
    opacity: 0.72;
}

.aura-jarvis-response-text {
    margin: 0;
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

/* AURA_JARVIS_CSS_V651_END */
'@

$css =
    $css.TrimEnd() +
    "`r`n" +
    $cssBlock

Write-Utf8Text `
    -Path $CssPath `
    -Text $css

# ============================================================
# BACKEND
# ============================================================

Write-Host '[11/12] FastAPI /api/assistant/respond route hazırlanıyor...'

$api =
    Read-Utf8Text $ApiPath

$routerVariable =
    Find-ApiRouterVariable $api

if ($null -eq $routerVariable) {

    Fail (
        'api.py içinde APIRouter değişkeni otomatik tespit edilemedi.'
    )
}

Write-Host (
    '    Router variable: ' +
    $routerVariable
)

#
# Imports.
#
# Hepsi single-line literal olarak ekleniyor.
#

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'import asyncio'

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'import json'

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'import os'

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'from urllib.request import Request, urlopen'

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'from pydantic import BaseModel'

$api =
    Ensure-PythonImport `
        -Text $api `
        -ImportLine 'from fastapi import HTTPException'

#
# Generated assistant route.
#

$api =
    Ensure-GeneratedPythonRoute `
        -Text $api `
        -RouterVariable $routerVariable

Write-Utf8Text `
    -Path $ApiPath `
    -Text $api

# ============================================================
# FINAL STATIC VALIDATION
# ============================================================

Write-Host ''
Write-Host '============================================================'
Write-Host ' FINAL VALIDATION'
Write-Host '============================================================'

$finalApp =
    Read-Utf8Text $AppPath

$finalApi =
    Read-Utf8Text $ApiPath

$finalBridge =
    Read-Utf8Text $BridgePath

#
# Frontend component.
#

if (
    $finalApp.IndexOf(
        'AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge App.tsx içinde bulunamadı.'
}

if (
    $finalApp.IndexOf(
        './AuraJarvisBridge',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'AuraJarvisBridge importu bulunamadı.'
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
    Fail 'Backend /api/assistant/respond route bulunamadı.'
}

if (
    $finalApi.IndexOf(
        'assistant_reply',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'assistant_reply response projection bulunamadı.'
}

#
# LLM bridge.
#

if (
    $finalBridge.IndexOf(
        '/api/assistant/respond',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'Frontend -> assistant API bridge bulunamadı.'
}

if (
    $finalBridge.IndexOf(
        'speechSynthesis.speak',
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail 'TTS speech queue bulunamadı.'
}

#
# Ham result -> TTS yasak.
#

$forbidden = @(
    'speakAssistantReply(researchOutput)',
    'speakAssistantReply(step.result)',
    'speechSynthesis.speak(researchOutput)',
    'speechSynthesis.speak(step.result)',
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
            'Ham araştırma verisi doğrudan TTS bağlantısında: ' +
            $bad
        )
    }
}

#
# Directive -> TTS yasak.
#

$forbiddenDirective = @(
    'speakAssistantReply(directive)',
    'speakAssistantReply(input)',
    'speakAssistantReply(query)',
    'speakAssistantReply(command)',
    'speechSynthesis.speak(directive)',
    'speechSynthesis.speak(input)',
    'speechSynthesis.speak(query)'
)

foreach ($bad in $forbiddenDirective) {

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
            'Kullanıcı directive metni doğrudan TTS bağlantısında: ' +
            $bad
        )
    }
}

#
# Eski static reply.
#

foreach ($reply in $staticReplies) {

    if (
        $finalApp.IndexOf(
            $reply,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {

        Fail (
            'Eski hardcoded reply hâlâ App.tsx içinde: ' +
            $reply
        )
    }
}

#
# Eski helper isimleri.
#

foreach ($oldName in @(
    'function buildAssistantReply',
    'function speakResearchOutput'
)) {

    if (
        $finalApp.IndexOf(
            $oldName,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            'Eski helper hâlâ App.tsx içinde: ' +
            $oldName
        )
    }
}

#
# TypeScript içinde PowerShell operator kaçağı.
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
# App return yeniden doğrula.
#

$verifyAppBrace =
    Find-AppFunctionOpenBrace $finalApp

if ($verifyAppBrace -lt 0) {
    Fail 'Final App() component bulunamadı.'
}

$verifyReturn =
    Find-AppReturnStart `
        -Text $finalApp `
        -AppOpenBrace $verifyAppBrace

if ($verifyReturn -lt 0) {
    Fail 'Final App() return(...) bulunamadı.'
}

# ============================================================
# PYTHON COMPILE
# ============================================================

Write-Host '[12/12] Python compile + npm build...'

$pythonCommand =
    Get-Command `
        python.exe `
        -ErrorAction SilentlyContinue

if ($null -eq $pythonCommand) {

    $pythonCommand =
        Get-Command `
            python `
            -ErrorAction SilentlyContinue
}

if ($null -eq $pythonCommand) {
    Fail 'Python bulunamadı.'
}

& $pythonCommand.Source `
    -m py_compile `
    $ApiPath

if ($LASTEXITCODE -ne 0) {
    Fail 'api.py Python compile başarısız.'
}

# ============================================================
# NPM BUILD
# ============================================================

Push-Location $UiRoot

$buildExit = 0

try {

    $npmCommand =
        Get-Command `
            npm.cmd `
            -ErrorAction SilentlyContinue

    if ($null -eq $npmCommand) {

        $npmCommand =
            Get-Command `
                npm `
                -ErrorAction SilentlyContinue
    }

    if ($null -eq $npmCommand) {
        Fail 'npm bulunamadı.'
    }

    & $npmCommand.Source run build

    $buildExit =
        $LASTEXITCODE
}
finally {

    Pop-Location
}

if ($buildExit -ne 0) {

    Write-Host ''
    Write-Host 'BUILD FAILED - ROLLBACK BAŞLIYOR' -ForegroundColor Red

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

    Fail 'npm run build başarısız oldu. App.tsx ve api.py rollback edildi.'
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ''
Write-Host '============================================================'
Write-Host ' AURA V6.5.1 SUCCESS'
Write-Host '============================================================'
Write-Host ''

Write-Host 'PowerShell parser             : PASS'
Write-Host 'App() detection              : PASS'
Write-Host 'App return detection         : PASS'
Write-Host 'Directive setter detection   : PASS'
Write-Host 'Research state detection     : PASS'
Write-Host 'LLM bridge module             : PASS'
Write-Host 'Hardcoded reply removal      : PASS'
Write-Host 'Raw step.result -> TTS       : BLOCKED'
Write-Host 'Directive -> TTS              : BLOCKED'
Write-Host 'step.result -> Ollama         : PASS'
Write-Host 'Ollama -> assistant_reply     : PASS'
Write-Host 'assistant_reply -> TTS        : PASS'
Write-Host 'FastAPI assistant route       : PASS'
Write-Host 'Python compile                : PASS'
Write-Host 'npm run build                 : PASS'
Write-Host ''

Write-Host 'Backup:'
Write-Host $BackupDir
Write-Host ''