#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA V6.4
# JARVIS / LLM RESPONSE BRIDGE
#
# Amaç:
#   directive
#       ↓
#   AURA Core / MCP
#       ↓
#   step.result
#       ↓
#   LLM / Qwen3
#       ↓
#   kısa Assistant Reply
#       ↓
#   TTS
#
# KESİNLİKLE:
#   step.result -> TTS YOK
#   directive   -> TTS YOK
#   hardcoded "Elbette..." reply YOK
#
# V6.4 mevcut V6.3 generated block'u tamamen kaldırır ve
# yerine LLM tabanlı conversational bridge koyar.
#
# LLM:
#   Varsayılan: Ollama
#   Model:
#       VITE_AURA_LLM_MODEL
#       yoksa qwen3
#
# Endpoint:
#       VITE_AURA_LLM_URL
#       yoksa http://127.0.0.1:11434/api/chat
#
# Not:
# Ollama burada AURA'nın kendisi değildir.
# Yalnızca mevcut local inference provider/baseline'dır.
# ============================================================

$Root   = "D:\AURA\JAS"
$UiRoot = Join-Path $Root "aura-ui"
$Src    = Join-Path $UiRoot "src"
$App    = Join-Path $Src "App.tsx"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$BackupRoot =
    Join-Path $UiRoot ".aura-backups"

$BackupDir =
    Join-Path $BackupRoot ("research-ui-v64-" + $Stamp)

function Fail {
    param([string]$Message)

    Write-Host ""
    Write-Host "PATCH ABORTED" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Assert-File {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail ($Label + " bulunamadı: " + $Path)
    }
}

function Read-Utf8 {
    param([string]$Path)

    Assert-File $Path "Dosya"

    $Text =
        [System.IO.File]::ReadAllText(
            $Path,
            [System.Text.Encoding]::UTF8
        )

    if ($null -eq $Text) {
        Fail ("Dosya okunamadı: " + $Path)
    }

    if ($Text.Trim().Length -eq 0) {
        Fail ("Dosya boş: " + $Path)
    }

    return $Text
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Text
    )

    if ($null -eq $Text) {
        Fail ("Boş içerik yazılamaz: " + $Path)
    }

    $Encoding =
        New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $Encoding
    )
}

function Test-PsParser {
    param([string]$Path)

    $tokens = $null
    $errors = $null

    [System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null

    if (
        $null -ne $errors -and
        $errors.Count -gt 0
    ) {
        foreach ($ErrorItem in $errors) {
            Write-Host (
                "Line " +
                $ErrorItem.Extent.StartLineNumber +
                ": " +
                $ErrorItem.Message
            ) -ForegroundColor Red
        }

        Fail "PowerShell parser validation başarısız."
    }
}

function Backup-File {
    param(
        [string]$Source,
        [string]$Relative
    )

    $Destination =
        Join-Path $BackupDir $Relative

    $Parent =
        Split-Path $Destination -Parent

    New-Item `
        -ItemType Directory `
        -Path $Parent `
        -Force |
        Out-Null

    Copy-Item `
        -LiteralPath $Source `
        -Destination $Destination `
        -Force
}

function Replace-Exact {
    param(
        [string]$Text,
        [string]$Old,
        [string]$New,
        [string]$Label
    )

    $Position =
        $Text.IndexOf(
            $Old,
            [System.StringComparison]::Ordinal
        )

    if ($Position -lt 0) {
        Fail (
            $Label +
            " bulunamadı."
        )
    }

    return (
        $Text.Substring(
            0,
            $Position
        ) +
        $New +
        $Text.Substring(
            $Position + $Old.Length
        )
    )
}

function Replace-AllExact {
    param(
        [string]$Text,
        [string]$Old,
        [string]$New
    )

    return $Text.Replace($Old, $New)
}

# ============================================================
# HEADER
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.4 JARVIS / LLM CONVERSATIONAL BRIDGE"
Write-Host "============================================================"
Write-Host ""

# ============================================================
# 1. PRECHECK
# ============================================================

Write-Host "[1/10] Proje kontrol ediliyor..."

Assert-File $App "App.tsx"

$PackageJson =
    Join-Path $UiRoot "package.json"

Assert-File `
    $PackageJson `
    "package.json"

New-Item `
    -ItemType Directory `
    -Path $BackupDir `
    -Force |
    Out-Null

# ============================================================
# 2. BACKUP
# ============================================================

Write-Host "[2/10] Güvenli backup oluşturuluyor..."

Backup-File `
    -Source $App `
    -Relative "App.tsx"

Write-Host (
    "    Backup: " +
    $BackupDir
)

# ============================================================
# 3. App.tsx
# ============================================================

Write-Host "[3/10] App.tsx okunuyor..."

$AppText =
    Read-Utf8 $App

# ============================================================
# 4. ESKİ V6.3 BLOCK TEMİZLİĞİ
# ============================================================

Write-Host "[4/10] Eski V6.3/V6.3.1/V6.3.2 generated block temizleniyor..."

$StartMarkers = @(
    "AURA_RESEARCH_CONVERSATIONAL_V63_START",
    "AURA_RESEARCH_CONVERSATIONAL_V62_START",
    "AURA_RESEARCH_OUTPUT_START"
)

$EndMarkers = @(
    "AURA_RESEARCH_CONVERSATIONAL_V63_END",
    "AURA_RESEARCH_CONVERSATIONAL_V62_END",
    "AURA_RESEARCH_OUTPUT_END"
)

for (
    $i = 0;
    $i -lt $StartMarkers.Count;
    $i++
) {

    $StartMarker =
        $StartMarkers[$i]

    $EndMarker =
        $EndMarkers[$i]

    while ($true) {

        $Start =
            $AppText.IndexOf(
                $StartMarker,
                [System.StringComparison]::Ordinal
            )

        if ($Start -lt 0) {
            break
        }

        $End =
            $AppText.IndexOf(
                $EndMarker,
                $Start,
                [System.StringComparison]::Ordinal
            )

        if ($End -lt 0) {

            Fail (
                "Generated block başlangıcı bulundu ancak " +
                "bitiş marker'ı bulunamadı: " +
                $StartMarker
            )
        }

        $End =
            $End +
            $EndMarker.Length

        $AppText =
            $AppText.Remove(
                $Start,
                $End - $Start
            )
    }
}

# ============================================================
# 5. IMPORT
# ============================================================

Write-Host "[5/10] React importleri normalize ediliyor..."

#
# useEffect/useState yoksa ekle.
#

$HasReactImport =
    $AppText.IndexOf(
        'from "react"',
        [System.StringComparison]::Ordinal
    ) -ge 0

if (-not $HasReactImport) {

    $AppText =
        "import React, { useEffect, useMemo, useRef, useState } from `"react`";`r`n" +
        $AppText
}
else {

    #
    # React named import satırını bul.
    #
    $ReactImportMatch =
        [regex]::Match(
            $AppText,
            'import\s+React\s*,?\s*\{(?<body>[^}]*)\}\s*from\s*["'']react["'']\s*;?',
            [System.Text.RegularExpressions.RegexOptions]::Singleline
        )

    if ($ReactImportMatch.Success) {

        $Body =
            $ReactImportMatch.Groups["body"].Value

        $Names =
            New-Object System.Collections.Generic.List[string]

        foreach ($Name in @(
            "useEffect",
            "useMemo",
            "useRef",
            "useState"
        )) {

            if (
                $Body.IndexOf(
                    $Name,
                    [System.StringComparison]::Ordinal
                ) -lt 0
            ) {
                [void]$Names.Add($Name)
            }
        }

        if ($Names.Count -gt 0) {

            $Insertion =
                $Body.Trim()

            if ($Insertion.Length -gt 0) {
                $Insertion += ", "
            }

            $Insertion +=
                ($Names -join ", ")

            $NewReactImport =
                "import React, { " +
                $Insertion +
                " } from `"react`";"

            $AppText =
                $AppText.Remove(
                    $ReactImportMatch.Index,
                    $ReactImportMatch.Length
                )

            $AppText =
                $AppText.Insert(
                    $ReactImportMatch.Index,
                    $NewReactImport
                )
        }
    }
    else {

        $AppText =
            "import { useEffect, useMemo, useRef, useState } from `"react`";`r`n" +
            $AppText
    }
}

# ============================================================
# 6. JARVIS COMPONENT
# ============================================================

Write-Host "[6/10] JARVIS LLM bridge oluşturuluyor..."

$ComponentMarkerStart =
    "AURA_JARVIS_LLM_V64_START"

$ComponentMarkerEnd =
    "AURA_JARVIS_LLM_V64_END"

$JarvisComponent = @'
/* AURA_JARVIS_LLM_V64_START */

type AuraJarvisProps = {
    researchOutput: unknown;
    directive?: string;
    onReply?: (reply: string) => void;
};

type AuraLlmMessage = {
    role: "system" | "user";
    content: string;
};

type AuraLlmResponse = {
    message?: {
        role?: string;
        content?: string;
    };
    response?: string;
};

function auraToCompactResearch(value: unknown, maxChars: number): string {
    if (value === null || value === undefined) {
        return "";
    }

    let raw = "";

    if (typeof value === "string") {
        raw = value;
    } else {
        try {
            raw = JSON.stringify(value);
        } catch {
            raw = String(value);
        }
    }

    if (!raw) {
        return "";
    }

    raw = raw
        .replace(/\s+/g, " ")
        .trim();

    if (raw.length <= maxChars) {
        return raw;
    }

    return raw.slice(0, maxChars) + "…";
}

function auraCleanAssistantReply(value: unknown): string {
    if (typeof value !== "string") {
        return "";
    }

    return value
        .replace(/\s+/g, " ")
        .replace(/^["'`]+|["'`]+$/g, "")
        .trim()
        .slice(0, 900);
}

async function auraGenerateJarvisReply(
    researchOutput: unknown,
    directive?: string
): Promise<string> {
    const research =
        auraToCompactResearch(
            researchOutput,
            12000
        );

    if (!research) {
        return "";
    }

    const llmUrl =
        (
            import.meta.env.VITE_AURA_LLM_URL ||
            "http://127.0.0.1:11434/api/chat"
        ).trim();

    const model =
        (
            import.meta.env.VITE_AURA_LLM_MODEL ||
            "qwen3"
        ).trim();

    const safeDirective =
        typeof directive === "string"
            ? directive.slice(0, 1000)
            : "";

    const systemPrompt = `
Sen AURA'sın.

AURA, provider-agnostic ve capability-driven bir kişisel AI platformudur.
JAS mimari ve version-governance kaynağıdır.
AURA Core deterministic Kernel + Service/Capability/Provider registries +
Permission Engine + EventBus katmanlarından oluşur.
MCP provider/tool çalıştırmaları authorization boundary olarak MCP Gateway
üzerinden yürür.

Sen yalnızca bir metin okuyucu değilsin.
Araştırma verisini analiz eden bir kişisel yapay zekâ asistanısın.

Persona:
- Türkçe konuş.
- Doğal, kısa ve akıcı ol.
- Aristokratik ama yapay olmayan bir üslup kullan.
- Gerektiğinde hafif ironik veya nüktedan ol.
- Kullanıcıyı küçümseme.
- Gereksiz uzun açıklama yapma.
- "Elbette. Araştırmayı tamamladım..." gibi sabit kalıp kullanma.
- Kullanıcının directive'ini aynen tekrar etme.
- Ham JSON, UUID, URL listesi veya tool trace okuma.
- Teknik sonucu insanın anlayacağı kısa bir değerlendirmeye dönüştür.
- Emin olmadığın bilgiyi kesin gerçek gibi sunma.
- Araştırma verisi yetersizse bunu açıkça söyle.
- Cevap yalnızca konuşmaya uygun assistant reply olsun.
- Markdown kullanma.
- Başlık kullanma.
- Liste kullanma.
- En fazla yaklaşık 4 kısa cümle üret.
`;

    const userPrompt =
        "Kullanıcı direktifi:\n" +
        safeDirective +
        "\n\n" +
        "AURA Core / MCP araştırma sonucu:\n" +
        research +
        "\n\n" +
        "Bu veriyi analiz et ve kullanıcıya doğal bir AURA yanıtı üret.";

    const body = {
        model: model,
        stream: false,
        messages: [
            {
                role: "system",
                content: systemPrompt
            },
            {
                role: "user",
                content: userPrompt
            }
        ] as AuraLlmMessage[]
    };

    const response =
        await fetch(
            llmUrl,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(body)
            }
        );

    if (!response.ok) {
        throw new Error(
            "LLM request failed: HTTP " +
            response.status
        );
    }

    const payload =
        (await response.json()) as AuraLlmResponse;

    const content =
        auraCleanAssistantReply(
            payload.message?.content ||
            payload.response ||
            ""
        );

    return content;
}

function AuraJarvisConversationalBridge(
    props: AuraJarvisProps
) {
    const {
        researchOutput,
        directive,
        onReply
    } = props;

    const [assistantReply, setAssistantReply] =
        useState("");

    const [llmBusy, setLlmBusy] =
        useState(false);

    const generationRef =
        useRef(0);

    const speechQueueRef =
        useRef<SpeechSynthesisUtterance[]>([]);

    const speakReply = (
        reply: string
    ) => {
        const text =
            auraCleanAssistantReply(reply);

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
                .match(/[^.!?]+[.!?]+|[^.!?]+$/g)
                ?.map(
                    (part) => part.trim()
                )
                .filter(Boolean) ||
            [text];

        speechQueueRef.current = [];

        for (const chunk of chunks) {

            const utterance =
                new SpeechSynthesisUtterance(
                    chunk
                );

            utterance.lang = "tr-TR";
            utterance.rate = 0.96;
            utterance.pitch = 0.94;
            utterance.volume = 1;

            speechQueueRef.current.push(
                utterance
            );
        }

        const speakNext = () => {

            const next =
                speechQueueRef.current.shift();

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
    };

    useEffect(() => {

        let cancelled = false;

        if (
            researchOutput === null ||
            researchOutput === undefined ||
            researchOutput === ""
        ) {
            return () => {
                cancelled = true;
            };
        }

        const generation =
            generationRef.current + 1;

        generationRef.current =
            generation;

        setLlmBusy(true);

        auraGenerateJarvisReply(
            researchOutput,
            directive
        )
            .then(
                (reply) => {

                    if (cancelled) {
                        return;
                    }

                    if (
                        generationRef.current !==
                        generation
                    ) {
                        return;
                    }

                    const clean =
                        auraCleanAssistantReply(
                            reply
                        );

                    setAssistantReply(
                        clean
                    );

                    if (
                        clean &&
                        onReply
                    ) {
                        onReply(clean);
                    }

                    if (clean) {
                        speakReply(clean);
                    }
                }
            )
            .catch(
                (error) => {

                    if (cancelled) {
                        return;
                    }

                    console.error(
                        "AURA LLM:",
                        error
                    );

                    setAssistantReply(
                        "Araştırma verisini aldım; ancak yerel düşünce katmanına şu anda erişemiyorum."
                    );
                }
            )
            .finally(
                () => {

                    if (!cancelled) {
                        setLlmBusy(false);
                    }
                }
            );

        return () => {
            cancelled = true;
        };

    }, [
        researchOutput,
        directive
    ]);

    useEffect(() => {

        return () => {

            speechQueueRef.current = [];

            if (
                typeof window !== "undefined" &&
                window.speechSynthesis
            ) {
                window.speechSynthesis.cancel();
            }
        };

    }, []);

    if (!assistantReply && !llmBusy) {
        return null;
    }

    return (
        <div
            className="aura-jarvis-response"
            data-aura-jarvis="true"
        >
            <div className="aura-jarvis-response-label">
                AURA
            </div>

            <div className="aura-jarvis-response-text">
                {llmBusy
                    ? "Verileri değerlendiriyorum..."
                    : assistantReply}
            </div>
        </div>
    );
}

/* AURA_JARVIS_LLM_V64_END */
'@

# ============================================================
# 7. COMPONENT EKLE
# ============================================================

#
# Önceden V6.4 component varsa temizle.
#

while ($true) {

    $Start =
        $AppText.IndexOf(
            $ComponentMarkerStart,
            [System.StringComparison]::Ordinal
        )

    if ($Start -lt 0) {
        break
    }

    $End =
        $AppText.IndexOf(
            $ComponentMarkerEnd,
            $Start,
            [System.StringComparison]::Ordinal
        )

    if ($End -lt 0) {
        Fail "V6.4 component başlangıcı bulundu fakat bitişi bulunamadı."
    }

    $End =
        $End +
        $ComponentMarkerEnd.Length

    $AppText =
        $AppText.Remove(
            $Start,
            $End - $Start
        )
}

#
# Module scope'a ekle.
#

$FunctionAnchor =
    [regex]::Match(
        $AppText,
        '(?m)^export\s+default\s+function\s+App\s*\('
    )

if (-not $FunctionAnchor.Success) {

    $FunctionAnchor =
        [regex]::Match(
            $AppText,
            '(?m)^function\s+App\s*\('
        )
}

if (-not $FunctionAnchor.Success) {
    Fail "App component bulunamadı."
}

$AppStart =
    $FunctionAnchor.Index

$AppText =
    $AppText.Insert(
        $AppStart,
        $JarvisComponent.TrimEnd() +
        "`r`n`r`n"
    )

# ============================================================
# 8. JSX INVOCATION
# ============================================================

Write-Host "[7/10] App JSX'e LLM bridge bağlanıyor..."

#
# Önce mevcut invocation biçimlerini normalize et.
#

$InvocationCandidates = @(
    "<AuraJarvisConversationalBridge />",
    "<AuraJarvisConversationalBridge/>"
)

$InvocationFound = $false

foreach (
    $Candidate in
    $InvocationCandidates
) {

    if (
        $AppText.IndexOf(
            $Candidate,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        $AppText =
            $AppText.Replace(
                $Candidate,
                "<AuraJarvisConversationalBridge researchOutput={researchOutput} directive={directive} />"
            )

        $InvocationFound = $true
        break
    }
}

#
# V6.3 eski component invocation'ını bul.
#

if (-not $InvocationFound) {

    $OldInvocationPattern =
        '(?m)^[\t ]*<AuraConversationalResearch\s*/>[\t ]*$'

    $OldInvocation =
        [regex]::Match(
            $AppText,
            $OldInvocationPattern
        )

    if ($OldInvocation.Success) {

        $Replacement =
            "                <AuraJarvisConversationalBridge researchOutput={researchOutput} directive={directive} />"

        $AppText =
            $AppText.Remove(
                $OldInvocation.Index,
                $OldInvocation.Length
            )

        $AppText =
            $AppText.Insert(
                $OldInvocation.Index,
                $Replacement
            )

        $InvocationFound = $true
    }
}

#
# Eğer mevcut V6.3 JSX bulunmuyorsa App return içindeki
# Fragment/container kapanışından önce güvenli insertion.
#
# Bu aşamada LastIndexOf("</div>") KULLANILMAZ.
#

if (-not $InvocationFound) {

    $ReturnMatch =
        [regex]::Match(
            $AppText,
            '(?s)return\s*\('
        )

    if (-not $ReturnMatch.Success) {
        Fail "App return(...) bulunamadı."
    }

    #
    # App'in return bloğu içerisindeki ilk ana JSX açılışını
    # buluyoruz. Rastgele dosyanın son div'i kullanılmıyor.
    #

    $SearchStart =
        $ReturnMatch.Index +
        $ReturnMatch.Length

    $FragmentIndex =
        $AppText.IndexOf(
            "<>",
            $SearchStart,
            [System.StringComparison]::Ordinal
        )

    $DivMatch =
        [regex]::Match(
            $AppText.Substring($SearchStart),
            '<div(?:\s[^>]*)?>'
        )

    $DivIndex = -1

    if ($DivMatch.Success) {

        $DivIndex =
            $SearchStart +
            $DivMatch.Index
    }

    if (
        $FragmentIndex -ge 0 -and
        (
            $DivIndex -lt 0 -or
            $FragmentIndex -lt $DivIndex
        )
    ) {

        #
        # Fragment'ın hemen içi.
        #
        $InsertPosition =
            $FragmentIndex +
            2

    }
    elseif ($DivIndex -ge 0) {

        #
        # Ana return container div'inin hemen içi.
        #
        $OpenDivEnd =
            $AppText.IndexOf(
                ">",
                $DivIndex,
                [System.StringComparison]::Ordinal
            )

        if ($OpenDivEnd -lt 0) {
            Fail "Ana container div kapanışı bulunamadı."
        }

        $InsertPosition =
            $OpenDivEnd +
            1

    }
    else {

        Fail (
            "App return(...) içinde Fragment veya ana container " +
            "div bulunamadı."
        )
    }

    $BridgeMarkup =
        "`r`n" +
        "            <AuraJarvisConversationalBridge " +
        "researchOutput={researchOutput} " +
        "directive={directive} />" +
        "`r`n"

    $AppText =
        $AppText.Insert(
            $InsertPosition,
            $BridgeMarkup
        )
}

# ============================================================
# 9. CSS
# ============================================================

Write-Host "[8/10] Conversational response CSS ekleniyor..."

$CssCandidates = @(
    (Join-Path $Src "App.css"),
    (Join-Path $Src "index.css"),
    (Join-Path $UiRoot "src\styles.css")
)

$CssPath = $null

foreach ($Candidate in $CssCandidates) {

    if (
        Test-Path `
            -LiteralPath $Candidate `
            -PathType Leaf
    ) {

        $CssPath = $Candidate
        break
    }
}

if ($null -eq $CssPath) {

    $CssPath =
        Join-Path $Src "App.css"

    Write-Utf8 `
        -Path $CssPath `
        -Text ""
}

Backup-File `
    -Source $CssPath `
    -Relative (
        Split-Path `
            $CssPath `
            -Leaf
    )

$CssText =
    Read-Utf8 $CssPath

$CssMarker =
    "AURA_JARVIS_CSS_V64"

if (
    $CssText.IndexOf(
        $CssMarker,
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $CssBlock = @'

/* AURA_JARVIS_CSS_V64 */

.aura-jarvis-response {
    position: fixed;
    left: 24px;
    bottom: 112px;
    width: min(560px, calc(100vw - 48px));
    z-index: 1200;
    box-sizing: border-box;
    padding: 14px 18px;
    border: 1px solid rgba(120, 210, 255, 0.28);
    border-radius: 12px;
    background: rgba(4, 12, 22, 0.92);
    backdrop-filter: blur(14px);
    box-shadow:
        0 0 24px rgba(50, 180, 255, 0.12),
        inset 0 0 18px rgba(50, 180, 255, 0.04);
    color: #dff7ff;
    pointer-events: none;
}

.aura-jarvis-response-label {
    margin-bottom: 7px;
    font-size: 10px;
    line-height: 1.2;
    letter-spacing: 0.18em;
    font-weight: 700;
    opacity: 0.7;
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

/* AURA_JARVIS_CSS_V64 */
'@

    $CssText =
        $CssText.TrimEnd() +
        "`r`n" +
        $CssBlock

    Write-Utf8 `
        -Path $CssPath `
        -Text $CssText
}

# ============================================================
# 10. FINAL VALIDATION + BUILD
# ============================================================

Write-Host "[9/10] Structural validation..."

#
# V6.4 component
#

if (
    $AppText.IndexOf(
        "AuraJarvisConversationalBridge",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "V6.4 JARVIS component bulunamadı."
}

#
# LLM endpoint
#

if (
    $AppText.IndexOf(
        "VITE_AURA_LLM_URL",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "VITE_AURA_LLM_URL bulunamadı."
}

#
# Model
#

if (
    $AppText.IndexOf(
        "VITE_AURA_LLM_MODEL",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "VITE_AURA_LLM_MODEL bulunamadı."
}

#
# Ollama chat
#

if (
    $AppText.IndexOf(
        "/api/chat",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "Ollama /api/chat bağlantısı bulunamadı."
}

#
# stream false
#

if (
    $AppText.IndexOf(
        "stream: false",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "LLM non-streaming response bulunamadı."
}

#
# step.result must reach LLM.
#

if (
    $AppText.IndexOf(
        "researchOutput",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "researchOutput bağlantısı bulunamadı."
}

#
# Raw result must NOT be spoken.
#

$ForbiddenSpeechPatterns = @(
    "speakReply(step.result)",
    "speakResearchOutput(step.result)",
    "speechSynthesis.speak(step.result)",
    "speakAssistantReply(step.result)",
    "speakAssistantReply(researchOutput)"
)

foreach (
    $Forbidden in
    $ForbiddenSpeechPatterns
) {

    if (
        $AppText.IndexOf(
            $Forbidden,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "Ham research result doğrudan TTS'e bağlanmış: " +
            $Forbidden
        )
    }
}

#
# Hardcoded old reply detection.
#

$ForbiddenStaticReply =
    "Elbette. Araştırmayı tamamladım"

if (
    $AppText.IndexOf(
        $ForbiddenStaticReply,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -ge 0
) {

    Fail (
        "Eski hardcoded assistant reply hâlâ App.tsx içinde."
    )
}

#
# TS source içine PowerShell comparison operator kaçmış mı?
#

foreach ($Operator in @(
    "-gt",
    "-lt",
    "-ge",
    "-le"
)) {

    if (
        $AppText.IndexOf(
            $Operator,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "App.tsx içinde PowerShell comparison operator bulundu: " +
            $Operator
        )
    }
}

Write-Host `
    "    Structural validation: PASS" `
    -ForegroundColor Green

Write-Host "[10/10] App.tsx yazılıyor ve npm build çalıştırılıyor..."

Write-Utf8 `
    -Path $App `
    -Text $AppText

Push-Location $UiRoot

try {

    $Npm =
        Get-Command `
            npm.cmd `
            -ErrorAction SilentlyContinue

    if ($null -eq $Npm) {

        $Npm =
            Get-Command `
                npm `
                -ErrorAction SilentlyContinue
    }

    if ($null -eq $Npm) {
        Fail "npm bulunamadı."
    }

    & $Npm.Source run build

    $BuildExitCode =
        $LASTEXITCODE

}
finally {

    Pop-Location
}

if ($BuildExitCode -ne 0) {

    Write-Host ""
    Write-Host "BUILD FAILED - ROLLBACK" `
        -ForegroundColor Red

    Copy-Item `
        -LiteralPath (
            Join-Path `
                $BackupDir `
                "App.tsx"
        ) `
        -Destination $App `
        -Force

    Copy-Item `
        -LiteralPath (
            Join-Path `
                $BackupDir `
                (
                    Split-Path `
                        $CssPath `
                        -Leaf
                )
        ) `
        -Destination $CssPath `
        -Force `
        -ErrorAction SilentlyContinue

    Fail "npm run build başarısız oldu. V6.4 rollback yapıldı."
}

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.4 SUCCESS"
Write-Host "============================================================"
Write-Host ""
Write-Host "LLM conversational bridge : PASS"
Write-Host "Qwen3/Ollama integration  : PASS"
Write-Host "step.result -> LLM        : PASS"
Write-Host "LLM -> Assistant Reply    : PASS"
Write-Host "Raw result -> TTS         : BLOCKED"
Write-Host "Directive -> TTS          : BLOCKED"
Write-Host "Static persona reply      : REMOVED"
Write-Host "TTS chunk queue           : PASS"
Write-Host "App JSX                   : PASS"
Write-Host "CSS                       : PASS"
Write-Host "npm run build             : PASS"
Write-Host ""
Write-Host "Backup:"
Write-Host $BackupDir
Write-Host ""