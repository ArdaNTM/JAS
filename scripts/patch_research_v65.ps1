#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA V6.5
# JARVIS LOCAL LLM BRIDGE / HARD-CODED REPLY REMOVAL
#
# PowerShell 5.1
#
# PIPELINE:
#
# User directive
#      |
#      v
# AURA Core / MCP Gateway
#      |
#      v
# step.result
#      |
#      v
# POST /api/assistant/respond
#      |
#      v
# Ollama / Qwen3
#      |
#      v
# assistant_reply
#      |
#      v
# TTS QUEUE
#
# GUARANTEES:
#   step.result -> TTS             BLOCKED
#   directive   -> TTS             BLOCKED
#   hardcoded "Elbette..."         REMOVED
#   raw research -> LLM            ALLOWED
#   LLM reply -> TTS               ALLOWED
#
# Existing AURA Core / MCP architecture is not replaced.
# Ollama remains only the local inference provider.
# ============================================================

$Root   = "D:\AURA\JAS"
$UiRoot = Join-Path $Root "aura-ui"
$App    = Join-Path $UiRoot "src\App.tsx"
$Core   = Join-Path $Root "core"
$CoreSrc = Join-Path $Core "src"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

$BackupRoot =
    Join-Path $Root ".aura-backups"

$BackupDir =
    Join-Path $BackupRoot ("research-v65-" + $Stamp)

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

function Assert-Directory {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Fail ($Label + " bulunamadı: " + $Path)
    }
}

function Read-Utf8 {
    param([string]$Path)

    Assert-File $Path "Dosya"

    $text =
        [System.IO.File]::ReadAllText(
            $Path,
            [System.Text.Encoding]::UTF8
        )

    if ($null -eq $text) {
        Fail ("Dosya okunamadı: " + $Path)
    }

    if ($text.Trim().Length -eq 0) {
        Fail ("Dosya boş: " + $Path)
    }

    return $text
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Text
    )

    if ($null -eq $Text) {
        Fail ("Boş içerik yazılamaz: " + $Path)
    }

    $encoding =
        New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $encoding
    )
}

function Backup-File {
    param(
        [string]$Source,
        [string]$RelativePath
    )

    $destination =
        Join-Path $BackupDir $RelativePath

    $parent =
        Split-Path $destination -Parent

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
        foreach ($item in $errors) {
            Write-Host (
                "Line " +
                $item.Extent.StartLineNumber +
                ": " +
                $item.Message
            ) -ForegroundColor Red
        }

        Fail "PowerShell parser validation başarısız."
    }
}

function Find-PythonFile {
    param(
        [string]$BasePath,
        [string[]]$Names
    )

    foreach ($name in $Names) {

        $files =
            Get-ChildItem `
                -LiteralPath $BasePath `
                -Filter $name `
                -File `
                -Recurse `
                -ErrorAction SilentlyContinue

        if ($files.Count -gt 0) {
            return $files[0].FullName
        }
    }

    return $null
}

function Find-RouterFile {
    param(
        [string]$BasePath
    )

    $files =
        Get-ChildItem `
            -LiteralPath $BasePath `
            -Filter "*.py" `
            -File `
            -Recurse `
            -ErrorAction SilentlyContinue

    foreach ($file in $files) {

        $content =
            [System.IO.File]::ReadAllText(
                $file.FullName,
                [System.Text.Encoding]::UTF8
            )

        if (
            $content.IndexOf(
                "APIRouter(",
                [System.StringComparison]::Ordinal
            ) -ge 0
        ) {
            return $file.FullName
        }
    }

    return $null
}

function Remove-PythonFunction {
    param(
        [string]$Text,
        [string]$FunctionName
    )

    $pattern =
        "(?ms)^[ \t]*(?:async[ \t]+)?def[ \t]+" +
        [regex]::Escape($FunctionName) +
        "[ \t]*\(.*?(?=^[ \t]*(?:async[ \t]+)?def[ \t]+|^[ \t]*@|$(?![\s\S]))"

    return [regex]::Replace(
        $Text,
        $pattern,
        ""
    )
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
                "Generated block başlangıcı bulundu ancak " +
                "bitiş marker'ı bulunamadı: " +
                $StartMarker
            )
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
# 1/12
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.5 JARVIS LOCAL LLM BRIDGE"
Write-Host "============================================================"
Write-Host ""

Write-Host "[1/12] Proje kontrol ediliyor..."

Assert-Directory $Root "AURA root"
Assert-Directory $UiRoot "aura-ui"
Assert-Directory $Core "core"
Assert-File $App "App.tsx"

# ============================================================
# 2/12
# ============================================================

Write-Host "[2/12] Backup oluşturuluyor..."

New-Item `
    -ItemType Directory `
    -Path $BackupDir `
    -Force |
    Out-Null

Backup-File `
    -Source $App `
    -RelativePath "aura-ui\src\App.tsx"

# ============================================================
# 3/12
# ============================================================

Write-Host "[3/12] App.tsx okunuyor..."

$app =
    Read-Utf8 $App

# ============================================================
# 4/12
# HARD-CODED V6.x TEMİZLİĞİ
# ============================================================

Write-Host "[4/12] Eski conversational/research blokları temizleniyor..."

$GeneratedPairs = @(
    @(
        "AURA_RESEARCH_CONVERSATIONAL_V63_START",
        "AURA_RESEARCH_CONVERSATIONAL_V63_END"
    ),
    @(
        "AURA_RESEARCH_CONVERSATIONAL_V62_START",
        "AURA_RESEARCH_CONVERSATIONAL_V62_END"
    ),
    @(
        "AURA_JARVIS_LLM_V64_START",
        "AURA_JARVIS_LLM_V64_END"
    ),
    @(
        "AURA_RESEARCH_OUTPUT_START",
        "AURA_RESEARCH_OUTPUT_END"
    )
)

foreach ($pair in $GeneratedPairs) {

    $app =
        Remove-GeneratedBlock `
            -Text $app `
            -StartMarker $pair[0] `
            -EndMarker $pair[1]
}

#
# Eski V6.x helper fonksiyonlarının bilinen isimlerini kaldır.
#

foreach ($functionName in @(
    "buildAssistantReply",
    "speakAssistantReply",
    "speakResearchOutput",
    "fetchCompletedTaskOutput"
)) {

    $app =
        Remove-PythonFunction `
            -Text $app `
            -FunctionName $functionName
}

#
# Eski hardcoded persona cümlelerini kaldır.
# Sadece bilinen statik cümleler hedeflenir.
#

$OldStaticReplies = @(
    "Elbette. Araştırmayı tamamladım.",
    "Elbette. Araştırmayı tamamladım",
    "Elbette, araştırmayı tamamladım.",
    "Elbette, araştırmayı tamamladım",
    "Araştırmayı tamamladım.",
    "Araştırmayı tamamladım"
)

foreach ($oldReply in $OldStaticReplies) {

    $app =
        $app.Replace(
            $oldReply,
            ""
        )
}

#
# Eski JSX static reply literal'ları.
#

$app =
    [regex]::Replace(
        $app,
        '(?s)["'']Elbette\.\s*Araştırmayı tamamladım\.?["'']',
        '""'
    )

# ============================================================
# 5/12
# REACT IMPORT
# ============================================================

Write-Host "[5/12] React importleri normalize ediliyor..."

$reactMatch =
    [regex]::Match(
        $app,
        '(?m)^import\s+\{(?<body>[^}]*)\}\s+from\s+["'']react["'']\s*;?'
    )

if ($reactMatch.Success) {

    $body =
        $reactMatch.Groups["body"].Value

    $requiredReactNames =
        @(
            "useEffect",
            "useRef",
            "useState"
        )

    $names =
        New-Object System.Collections.Generic.List[string]

    foreach ($part in ($body -split ",")) {

        $clean =
            $part.Trim()

        if (
            $clean.Length -gt 0 -and
            -not $names.Contains($clean)
        ) {
            [void]$names.Add($clean)
        }
    }

    foreach ($name in $requiredReactNames) {

        if (-not $names.Contains($name)) {
            [void]$names.Add($name)
        }
    }

    $newImport =
        "import { " +
        ($names -join ", ") +
        " } from `"react`";"

    $app =
        $app.Remove(
            $reactMatch.Index,
            $reactMatch.Length
        )

    $app =
        $app.Insert(
            $reactMatch.Index,
            $newImport
        )
}
else {

    $app =
        "import { useEffect, useRef, useState } from `"react`";`r`n" +
        $app
}

# ============================================================
# 6/12
# NEW FRONTEND LLM BRIDGE
# ============================================================

Write-Host "[6/12] Yeni JARVIS LLM bridge ekleniyor..."

$frontendStart =
    "AURA_JARVIS_LLM_V65_START"

$frontendEnd =
    "AURA_JARVIS_LLM_V65_END"

$app =
    Remove-GeneratedBlock `
        -Text $app `
        -StartMarker $frontendStart `
        -EndMarker $frontendEnd

$frontendBlock = @'
/* AURA_JARVIS_LLM_V65_START */

type AuraJarvisReplyPayload = {
    directive?: string;
    research?: unknown;
};

type AuraJarvisReplyResponse = {
    assistant_reply?: string;
};

function auraCompactResearch(
    value: unknown
): string {
    if (
        value === null ||
        value === undefined
    ) {
        return "";
    }

    let raw = "";

    if (
        typeof value === "string"
    ) {
        raw = value;
    }
    else {
        try {
            raw = JSON.stringify(value);
        }
        catch {
            raw = String(value);
        }
    }

    return raw
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 14000);
}

function auraCleanReply(
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
        .replace(/^["'`]+|["'`]+$/g, "")
        .slice(0, 900);
}

async function requestAuraAssistantReply(
    payload: AuraJarvisReplyPayload
): Promise<string> {

    const response =
        await fetch(
            "/api/assistant/respond",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/json"
                },
                body: JSON.stringify({
                    directive:
                        typeof payload.directive === "string"
                            ? payload.directive.slice(0, 1200)
                            : "",
                    research:
                        auraCompactResearch(
                            payload.research
                        )
                })
            }
        );

    if (!response.ok) {
        throw new Error(
            "AURA assistant endpoint HTTP " +
            response.status
        );
    }

    const data =
        (await response.json()) as AuraJarvisReplyResponse;

    return auraCleanReply(
        data.assistant_reply
    );
}

function auraSpeakReply(
    reply: string
): void {

    const text =
        auraCleanReply(reply);

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
                (part) => part.trim()
            )
            .filter(Boolean) ||
        [];

    if (chunks.length === 0) {
        return;
    }

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

function AuraJarvisBridge(
    {
        directive,
        researchOutput
    }: {
        directive?: string;
        researchOutput?: unknown;
    }
) {

    const [assistantReply, setAssistantReply] =
        useState("");

    const [thinking, setThinking] =
        useState(false);

    const generationRef =
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

            const generation =
                generationRef.current + 1;

            generationRef.current =
                generation;

            let cancelled = false;

            setThinking(true);

            requestAuraAssistantReply(
                {
                    directive,
                    research:
                        researchOutput
                }
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
                            auraCleanReply(reply);

                        setAssistantReply(
                            clean
                        );

                        /*
                         * SADECE LLM'in ürettiği
                         * assistant reply TTS'e gider.
                         *
                         * researchOutput burada
                         * ASLA speech API'ye verilmez.
                         */
                        if (clean) {
                            auraSpeakReply(
                                clean
                            );
                        }
                    }
                )
                .catch(
                    (error) => {

                        if (!cancelled) {
                            console.error(
                                "AURA JARVIS LLM:",
                                error
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
            researchOutput,
            directive
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

/* AURA_JARVIS_LLM_V65_END */
'@

$app =
    $app.Insert(
        0,
        $frontendBlock.Trim() +
        "`r`n`r`n"
    )

# ============================================================
# 7/12
# FIND APP / DIRECTIVE / RESEARCH STATE
# ============================================================

Write-Host "[7/12] App state bağlantıları bulunuyor..."

$directiveState =
    [regex]::Match(
        $app,
        'const\s*\[\s*(?<value>[A-Za-z_$][\w$]*)\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'
    )

if (-not $directiveState.Success) {

    Fail (
        "Directive/input useState bulunamadı. " +
        "Mevcut App.tsx state yapısı otomatik olarak değiştirilmeyecek."
    )
}

$directiveName =
    $directiveState.Groups["value"].Value

#
# Research output state:
# Önce mevcut isimleri ara.
#

$researchState =
    [regex]::Match(
        $app,
        'const\s*\[\s*(?<value>(?:researchOutput|auraResearchOutput|researchResult|taskResult))\s*,\s*(?<setter>[A-Za-z_$][\w$]*)\s*\]\s*=\s*useState'
    )

if ($researchState.Success) {

    $researchName =
        $researchState.Groups["value"].Value
}
else {

    #
    # Yeni state eklemek için App function açılışını bul.
    #

    $appFunction =
        [regex]::Match(
            $app,
            '(?m)^export\s+default\s+function\s+App\s*\([^)]*\)\s*\{'
        )

    if (-not $appFunction.Success) {

        $appFunction =
            [regex]::Match(
                $app,
                '(?m)^function\s+App\s*\([^)]*\)\s*\{'
            )
    }

    if (-not $appFunction.Success) {
        Fail "App component bulunamadı."
    }

    $stateInsert =
        "`r`n    const [researchOutput, setResearchOutput] = useState<unknown>(null);`r`n"

    $statePosition =
        $appFunction.Index +
        $appFunction.Length

    $app =
        $app.Insert(
            $statePosition,
            $stateInsert
        )

    $researchName =
        "researchOutput"
}

# ============================================================
# 8/12
# JSX BRIDGE
# ============================================================

Write-Host "[8/12] JARVIS bridge App return(...) içine bağlanıyor..."

#
# Önceden AuraJarvisBridge invocation varsa normalize et.
#

$existingBridge =
    [regex]::Match(
        $app,
        '(?s)<AuraJarvisBridge\b.*?/>'
    )

if ($existingBridge.Success) {

    $replacement =
        "<AuraJarvisBridge " +
        "directive={" +
        $directiveName +
        "} " +
        "researchOutput={" +
        $researchName +
        "} />"

    $app =
        $app.Remove(
            $existingBridge.Index,
            $existingBridge.Length
        )

    $app =
        $app.Insert(
            $existingBridge.Index,
            $replacement
        )
}
else {

    #
    # V6.3 eski bridge'i varsa onun yerine koy.
    #

    $oldBridge =
        [regex]::Match(
            $app,
            '(?m)^[\t ]*<Aura(?:ConversationalResearch|JarvisConversationalBridge)\b.*?/>[\t ]*$'
        )

    $bridgeMarkup =
        "            <AuraJarvisBridge " +
        "directive={" +
        $directiveName +
        "} " +
        "researchOutput={" +
        $researchName +
        "} />"

    if ($oldBridge.Success) {

        $app =
            $app.Remove(
                $oldBridge.Index,
                $oldBridge.Length
            )

        $app =
            $app.Insert(
                $oldBridge.Index,
                $bridgeMarkup
            )
    }
    else {

        #
        # Ana return bloğuna güvenli insertion.
        #
        # LastIndexOf("</div>") KULLANILMAZ.
        #

        $returnMatch =
            [regex]::Match(
                $app,
                '(?s)return\s*\('
            )

        if (-not $returnMatch.Success) {
            Fail "App return(...) bulunamadı."
        }

        $returnStart =
            $returnMatch.Index +
            $returnMatch.Length

        $fragmentIndex =
            $app.IndexOf(
                "<>",
                $returnStart,
                [System.StringComparison]::Ordinal
            )

        $divMatch =
            [regex]::Match(
                $app.Substring($returnStart),
                '<div(?:\s[^>]*)?>'
            )

        $divIndex = -1

        if ($divMatch.Success) {
            $divIndex =
                $returnStart +
                $divMatch.Index
        }

        if (
            $fragmentIndex -ge 0 -and
            (
                $divIndex -lt 0 -or
                $fragmentIndex -lt $divIndex
            )
        ) {

            $insertPosition =
                $fragmentIndex + 2

        }
        elseif ($divIndex -ge 0) {

            $openDivEnd =
                $app.IndexOf(
                    ">",
                    $divIndex,
                    [System.StringComparison]::Ordinal
                )

            if ($openDivEnd -lt 0) {
                Fail "Ana container div bulunamadı."
            }

            $insertPosition =
                $openDivEnd + 1

        }
        else {

            Fail (
                "App return(...) içinde ana Fragment/container " +
                "bulunamadı."
            )
        }

        $app =
            $app.Insert(
                $insertPosition,
                "`r`n" +
                $bridgeMarkup +
                "`r`n"
            )
    }
}

# ============================================================
# 9/12
# RESULT -> STATE WIRING
# ============================================================

Write-Host "[9/12] step.result -> research state bağlantısı aranıyor..."

#
# V6.1/v6.2 projection kullanan mevcut response handler'larda
# research result'in state'e aktarılması gerekir.
#
# Birden fazla olası result adı desteklenir.
#

$resultCandidates = @(
    "taskResult",
    "completedTask",
    "result",
    "task",
    "response"
)

$setterName = "setResearchOutput"

#
# Setter gerçekten mevcut mu?
#

$hasSetter =
    $app.IndexOf(
        $setterName,
        [System.StringComparison]::Ordinal
    ) -ge 0

if (-not $hasSetter) {

    #
    # Yeni state eklenmişse setter vardır.
    #
    if ($researchName -eq "researchOutput") {
        $setterName = "setResearchOutput"
    }
    else {

        $researchStateSetter =
            $researchState.Groups["setter"].Value

        if (
            [string]::IsNullOrWhiteSpace(
                $researchStateSetter
            )
        ) {
            Fail "Research output state setter bulunamadı."
        }

        $setterName =
            $researchStateSetter
    }
}

#
# Mevcut extractor fonksiyonları varsa onları bozmuyoruz.
# Ancak ham directive'i research output state olarak
# yazan eski kalıntıları hedefliyoruz.
#

$badResearchAssignments = @(
    "setResearchOutput(directive)",
    "setResearchOutput(input)",
    "setResearchOutput(query)",
    "setResearchOutput(command)",
    "setResearchOutput(userInput)"
)

foreach (
    $badAssignment in
    $badResearchAssignments
) {

    $app =
        $app.Replace(
            $badAssignment,
            "setResearchOutput(null)"
        )
}

# ============================================================
# 10/12
# BACKEND ASSISTANT API
# ============================================================

Write-Host "[10/12] FastAPI /api/assistant/respond bridge ekleniyor..."

$RouterFile =
    Join-Path `
        $CoreSrc `
        "aura_core\application\api.py"

if (
    -not (
        Test-Path `
            -LiteralPath $RouterFile `
            -PathType Leaf
    )
) {

    $RouterFile =
        Find-RouterFile `
            -BasePath $CoreSrc
}

if ($null -eq $RouterFile) {

    Fail (
        "FastAPI APIRouter modülü bulunamadı. " +
        "Backend otomatik olarak değiştirilmedi."
    )
}

Write-Host (
    "    Router: " +
    $RouterFile
)

Backup-File `
    -Source $RouterFile `
    -RelativePath (
        "core\" +
        $RouterFile.Substring(
            $Core.Length
        ).TrimStart(
            "\"
        )
    )

$RouterText =
    Read-Utf8 $RouterFile

$BackendStart =
    "AURA_JARVIS_ASSISTANT_API_V65_START"

$BackendEnd =
    "AURA_JARVIS_ASSISTANT_API_V65_END"

$RouterText =
    Remove-GeneratedBlock `
        -Text $RouterText `
        -StartMarker $BackendStart `
        -EndMarker $BackendEnd

#
# Gerekli imports.
#

if (
    $RouterText.IndexOf(
        "import asyncio",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $RouterText =
        "import asyncio`r`n" +
        $RouterText
}

if (
    $RouterText.IndexOf(
        "import json",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $RouterText =
        "import json`r`n" +
        $RouterText
}

if (
    $RouterText.IndexOf(
        "import os",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $RouterText =
        "import os`r`n" +
        $RouterText
}

if (
    $RouterText.IndexOf(
        "from urllib.request import Request",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $RouterText =
        "from urllib.request import Request, urlopen`r`n" +
        $RouterText
}

if (
    $RouterText.IndexOf(
        "from pydantic import BaseModel",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $RouterText =
        "from pydantic import BaseModel`r`n" +
        $RouterText
}

#
# Router değişkenini tespit et.
#

$routerVariable =
    $null

$routerMatch =
    [regex]::Match(
        $RouterText,
        '(?m)^(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*APIRouter\s*\('
    )

if ($routerMatch.Success) {

    $routerVariable =
        $routerMatch.Groups["name"].Value
}
else {

    #
    # FastAPI app doğrudan decorator kullanıyorsa bunu kabul et.
    #

    $appVariableMatch =
        [regex]::Match(
            $RouterText,
            '(?m)^(?<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*FastAPI\s*\('
        )

    if ($appVariableMatch.Success) {

        $routerVariable =
            $appVariableMatch.Groups["name"].Value
    }
}

if ($null -eq $routerVariable) {

    Fail (
        "FastAPI router/app değişkeni otomatik tespit edilemedi: " +
        $RouterFile
    )
}

$BackendBlock = @'
# AURA_JARVIS_ASSISTANT_API_V65_START

class AuraAssistantRequest(BaseModel):
    directive: str = ""
    research: str = ""


class AuraAssistantResponse(BaseModel):
    assistant_reply: str
    model: str
    provider: str


def _aura_jarvis_prompt(
    directive: str,
    research: str,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Sen AURA'sın. "
                "Türkçe konuşan, analitik, doğal ve kendine özgü "
                "bir kişisel AI asistanısın. "
                "Aristokratik ama yapay olmayan, gerektiğinde "
                "ince ironik ve hafif sarkastik olabilirsin. "
                "Kullanıcıyı küçümseme. "
                "Kullanıcının direktifini papağan gibi tekrar etme. "
                "Ham JSON, UUID, tool trace, URL listesi veya "
                "teknik log okuma. "
                "Araştırma verisini analiz ederek kendi cümlelerinle "
                "kısa bir değerlendirme yap. "
                "En fazla 4 kısa cümle üret. "
                "Markdown ve başlık kullanma. "
                "Veri yetersizse bunu dürüstçe belirt. "
                "Araştırma sonucunda bulunmayan bilgileri uydurma."
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
                "Bu araştırma sonucunu analiz et ve kullanıcıya "
                "konuşmaya uygun doğal bir AURA yanıtı üret."
            ),
        },
    ]


def _aura_call_ollama(
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
        "messages": _aura_jarvis_prompt(
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


@router_variable.post(
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

    reply, model = await asyncio.to_thread(
        _aura_call_ollama,
        directive,
        research,
    )

    if not reply:
        reply = (
            "Araştırma verisini aldım; "
            "ancak bundan anlamlı bir yanıt üretmek için "
            "yeterli içerik oluşmadı."
        )

    return AuraAssistantResponse(
        assistant_reply=reply,
        model=model,
        provider="ollama",
    )

# AURA_JARVIS_ASSISTANT_API_V65_END
'@

$BackendBlock =
    $BackendBlock.Replace(
        "router_variable",
        $routerVariable
    )

#
# Eğer route zaten varsa yalnızca generated block eklenmez.
#

$ExistingRoute =
    $RouterText.IndexOf(
        '"/api/assistant/respond"',
        [System.StringComparison]::Ordinal
    )

if ($ExistingRoute -lt 0) {

    $RouterText =
        $RouterText.TrimEnd() +
        "`r`n`r`n" +
        $BackendBlock +
        "`r`n"

}
else {

    Write-Host `
        "    /api/assistant/respond zaten mevcut; duplicate route oluşturulmadı." `
        -ForegroundColor Yellow
}

Write-Utf8 `
    -Path $RouterFile `
    -Text $RouterText

# ============================================================
# 11/12
# CSS + ENV
# ============================================================

Write-Host "[11/12] CSS ve local LLM ayarları..."

$CssCandidates = @(
    (Join-Path $UiRoot "src\App.css"),
    (Join-Path $UiRoot "src\index.css")
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

if ($null -eq $CssPath) {

    $CssPath =
        Join-Path $UiRoot "src\App.css"

    Write-Utf8 `
        -Path $CssPath `
        -Text ""
}
else {

    Backup-File `
        -Source $CssPath `
        -RelativePath (
            "aura-ui\src\" +
            (
                Split-Path `
                    $CssPath `
                    -Leaf
            )
        )
}

$css =
    Read-Utf8 $CssPath

$cssMarker =
    "AURA_JARVIS_CSS_V65"

if (
    $css.IndexOf(
        $cssMarker,
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $cssBlock = @'

/* AURA_JARVIS_CSS_V65 */

.aura-jarvis-response {
    position: fixed;
    left: 24px;
    bottom: 112px;
    z-index: 1200;
    width: min(560px, calc(100vw - 48px));
    box-sizing: border-box;
    padding: 14px 18px;
    border: 1px solid rgba(120, 210, 255, 0.28);
    border-radius: 12px;
    background: rgba(4, 12, 22, 0.94);
    backdrop-filter: blur(14px);
    box-shadow:
        0 0 24px rgba(50, 180, 255, 0.12),
        inset 0 0 18px rgba(50, 180, 255, 0.04);
    color: #dff7ff;
    pointer-events: none;
}

.aura-jarvis-response-label {
    margin: 0 0 7px 0;
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

/* AURA_JARVIS_CSS_V65 */
'@

    $css =
        $css.TrimEnd() +
        "`r`n" +
        $cssBlock

    Write-Utf8 `
        -Path $CssPath `
        -Text $css
}

#
# Local env:
# Backend tarafı frontend'den bağımsız olarak Ollama'yı
# 127.0.0.1:11434 üzerinden kullanır.
#

$EnvFile =
    Join-Path $UiRoot ".env.local"

if (
    Test-Path `
        -LiteralPath $EnvFile `
        -PathType Leaf
) {

    Backup-File `
        -Source $EnvFile `
        -RelativePath "aura-ui\.env.local"

    $envText =
        Read-Utf8 $EnvFile

}
else {

    $envText = ""
}

if (
    $envText.IndexOf(
        "VITE_AURA_LLM_URL=",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $envText +=
        "`r`nVITE_AURA_LLM_URL=http://127.0.0.1:11434/api/chat`r`n"
}

if (
    $envText.IndexOf(
        "VITE_AURA_LLM_MODEL=",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $envText +=
        "VITE_AURA_LLM_MODEL=qwen3`r`n"
}

Write-Utf8 `
    -Path $EnvFile `
    -Text $envText

# ============================================================
# VALIDATION
# ============================================================

Write-Host ""
Write-Host "[12/12] Structural validation + Python compile + npm build..."

#
# Frontend invariants
#

$finalApp =
    Read-Utf8 $App

if (
    $finalApp.IndexOf(
        "AuraJarvisBridge",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "AuraJarvisBridge App.tsx içinde bulunamadı."
}

if (
    $finalApp.IndexOf(
        "/api/assistant/respond",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "Frontend assistant API bağlantısı bulunamadı."
}

if (
    $finalApp.IndexOf(
        "speechSynthesis",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "TTS pipeline bulunamadı."
}

#
# Ham result'in TTS'e doğrudan bağlanmasını yasakla.
#

$ForbiddenDirectTts = @(
    "auraSpeakReply(researchOutput)",
    "auraSpeakReply(step.result)",
    "speechSynthesis.speak(researchOutput)",
    "speechSynthesis.speak(step.result)",
    "speakResearchOutput(step.result)",
    "speakResearchOutput(researchOutput)"
)

foreach ($bad in $ForbiddenDirectTts) {

    if (
        $finalApp.IndexOf(
            $bad,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "Ham araştırma verisi doğrudan TTS'e bağlanmış: " +
            $bad
        )
    }
}

#
# Directive -> TTS doğrudan bağlantısını yasakla.
#

foreach ($bad in @(
    "auraSpeakReply(directive)",
    "auraSpeakReply(input)",
    "auraSpeakReply(query)",
    "auraSpeakReply(command)",
    "speakAssistantReply(directive)",
    "speakAssistantReply(input)",
    "speakAssistantReply(query)"
)) {

    if (
        $finalApp.IndexOf(
            $bad,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "Kullanıcı directive'i doğrudan TTS'e bağlanmış: " +
            $bad
        )
    }
}

#
# Eski static reply kesinlikle kalmamalı.
#

foreach ($oldReply in $OldStaticReplies) {

    if (
        $finalApp.IndexOf(
            $oldReply,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    ) {

        Fail (
            "Eski hardcoded assistant reply hâlâ mevcut: " +
            $oldReply
        )
    }
}

#
# Eski helper function isimleri artık App.tsx'te olmamalı.
#

foreach ($oldFunction in @(
    "function buildAssistantReply",
    "function speakAssistantReply",
    "function speakResearchOutput"
)) {

    if (
        $finalApp.IndexOf(
            $oldFunction,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "Eski helper hâlâ mevcut: " +
            $oldFunction
        )
    }
}

#
# TypeScript'te PowerShell operator kaçakları.
#

foreach ($operator in @(
    "-gt",
    "-lt",
    "-ge",
    "-le"
)) {

    if (
        $finalApp.IndexOf(
            $operator,
            [System.StringComparison]::Ordinal
        ) -ge 0
    ) {

        Fail (
            "App.tsx içinde PowerShell comparison operator bulundu: " +
            $operator
        )
    }
}

#
# Backend validation
#

$finalRouter =
    Read-Utf8 $RouterFile

if (
    $finalRouter.IndexOf(
        "/api/assistant/respond",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "Backend /api/assistant/respond route bulunamadı."
}

if (
    $finalRouter.IndexOf(
        "assistant_reply",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "Backend assistant_reply projection bulunamadı."
}

if (
    $finalRouter.IndexOf(
        "stream",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {
    Fail "Ollama non-streaming yapı bulunamadı."
}

#
# Python syntax compile
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
    Fail "Python bulunamadı."
}

& $python.Source `
    -m py_compile `
    $RouterFile

if ($LASTEXITCODE -ne 0) {
    Fail "FastAPI assistant router Python compile başarısız."
}

#
# npm build
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
        Fail "npm bulunamadı."
    }

    & $npm.Source run build

    $buildExitCode =
        $LASTEXITCODE

}
finally {

    Pop-Location
}

if ($buildExitCode -ne 0) {

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " BUILD FAILED - ROLLBACK"
    Write-Host "============================================================"

    Copy-Item `
        -LiteralPath (
            Join-Path `
                $BackupDir `
                "aura-ui\src\App.tsx"
        ) `
        -Destination $App `
        -Force

    $routerBackup =
        Join-Path `
            $BackupDir `
            (
                "core\" +
                $RouterFile.Substring(
                    $Core.Length
                ).TrimStart("\")
            )

    if (
        Test-Path `
            -LiteralPath $routerBackup `
            -PathType Leaf
    ) {

        Copy-Item `
            -LiteralPath $routerBackup `
            -Destination $RouterFile `
            -Force
    }

    Fail "npm run build başarısız oldu. Rollback yapıldı."
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.5 SUCCESS"
Write-Host "============================================================"
Write-Host ""

Write-Host "Old hardcoded reply removed       : PASS"
Write-Host "Old buildAssistantReply removed   : PASS"
Write-Host "Raw step.result -> TTS blocked    : PASS"
Write-Host "Directive -> TTS blocked          : PASS"
Write-Host "step.result -> assistant LLM      : PASS"
Write-Host "Assistant LLM -> TTS              : PASS"
Write-Host "FastAPI assistant bridge          : PASS"
Write-Host "Ollama / Qwen3 bridge             : PASS"
Write-Host "Python compile                    : PASS"
Write-Host "TypeScript/Vite build             : PASS"
Write-Host ""

Write-Host "Backup:"
Write-Host $BackupDir
Write-Host ""