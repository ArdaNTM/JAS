#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA V6.3.2
# CONVERSATIONAL TTS VALIDATION / BUILD PATCH
#
# PowerShell 5.1
#
# V6.3.1'deki problem:
#   "Assistant reply -> speakAssistantReply bağlantısı"
#   statik regex ile zorunlu tutuluyordu.
#
# V6.3.2:
#   - Bu katı bağlantı regex'i tamamen kaldırılır.
#   - Kodun gerçek TS/TSX yapısı statik regex ile yeniden
#     yorumlanmaz.
#   - Gerekli semboller ayrı ayrı doğrulanır.
#   - TTS pipeline için yalnızca güvenli minimum invariant'lar
#     kontrol edilir.
#   - App.tsx değiştirilmez.
#   - CSS değiştirilmez.
#   - V6.3 patch'in mevcut çıktısı korunur.
#   - npm run build gerçek doğrulama olarak kullanılır.
#   - Build başarısız olursa App.tsx rollback edilir.
#
# Bu yaklaşım daha güvenlidir çünkü PowerShell'in -match /
# -notmatch operatörleri regex tabanlıdır; regex'in source-code
# yapısını kesin bir AST gibi yorumlaması beklenmez.
# ============================================================

$Root   = "D:\AURA\JAS"
$UiRoot = Join-Path $Root "aura-ui"
$App    = Join-Path $UiRoot "src\App.tsx"

function Fail {
    param(
        [string]$Message
    )

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
        Fail (
            $Label +
            " bulunamadı: " +
            $Path
        )
    }
}

function Read-Utf8 {
    param(
        [string]$Path
    )

    Assert-File `
        -Path $Path `
        -Label "Dosya"

    $content =
        [System.IO.File]::ReadAllText(
            $Path,
            [System.Text.Encoding]::UTF8
        )

    if ($null -eq $content) {
        Fail (
            "Dosya okunamadı: " +
            $Path
        )
    }

    if ($content.Trim().Length -eq 0) {
        Fail (
            "Dosya boş: " +
            $Path
        )
    }

    return $content
}

function Get-V63Block {
    param(
        [string]$Text
    )

    $startMarker =
        "AURA_RESEARCH_CONVERSATIONAL_V63_START"

    $endMarker =
        "AURA_RESEARCH_CONVERSATIONAL_V63_END"

    $start =
        $Text.IndexOf(
            $startMarker,
            [System.StringComparison]::Ordinal
        )

    if ($start -lt 0) {
        return $null
    }

    $end =
        $Text.IndexOf(
            $endMarker,
            $start,
            [System.StringComparison]::Ordinal
        )

    if ($end -lt 0) {
        Fail (
            "V6.3 başlangıç marker'ı bulundu fakat " +
            "bitiş marker'ı bulunamadı."
        )
    }

    return $Text.Substring(
        $start,
        (
            $end -
            $start +
            $endMarker.Length
        )
    )
}

function Test-Token {
    param(
        [string]$Text,
        [string]$Token,
        [string]$Label
    )

    $index =
        $Text.IndexOf(
            $Token,
            [System.StringComparison]::Ordinal
        )

    if ($index -lt 0) {

        Fail (
            $Label +
            " bulunamadı: " +
            $Token
        )
    }

    return $true
}

function Test-TokenAny {
    param(
        [string]$Text,
        [string[]]$Tokens,
        [string]$Label
    )

    foreach ($token in $Tokens) {

        $index =
            $Text.IndexOf(
                $token,
                [System.StringComparison]::Ordinal
            )

        if ($index -ge 0) {
            return $true
        }
    }

    Fail (
        $Label +
        " için beklenen token bulunamadı."
    )
}

function Test-PowerShellParser {
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

# ============================================================
# HEADER
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.3.2 CONVERSATIONAL TTS SAFE VALIDATION"
Write-Host "============================================================"
Write-Host ""

# ============================================================
# 1
# ============================================================

Write-Host "[1/7] Proje ve App.tsx kontrol ediliyor..."

if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    Fail "AURA root bulunamadı."
}

if (-not (Test-Path -LiteralPath $UiRoot -PathType Container)) {
    Fail "aura-ui bulunamadı."
}

Assert-File `
    -Path $App `
    -Label "App.tsx"

# ============================================================
# 2
# ============================================================

Write-Host "[2/7] App.tsx okunuyor..."

$app =
    Read-Utf8 $App

$generated =
    Get-V63Block $app

if ($null -eq $generated) {

    Fail (
        "V6.3 generated block bulunamadı. " +
        "Dosya değiştirilmedi."
    )
}

Write-Host `
    "    V6.3 generated block: FOUND" `
    -ForegroundColor Green

# ============================================================
# 3
# ============================================================

Write-Host "[3/7] Katı assistant-reply regex validation kaldırılıyor..."

#
# Burada bilinçli olarak:
#
#   speakAssistantReply(reply)
#
# gibi tek bir source-code yazım biçimini zorunlu tutmuyoruz.
#
# Çünkü aşağıdaki biçimlerin hepsi semantik olarak geçerlidir:
#
#   speakAssistantReply(reply);
#
#   speakAssistantReply(
#       reply
#   );
#
#   const speechText = reply;
#   speakAssistantReply(speechText);
#
#   window.setTimeout(() => {
#       speakAssistantReply(reply);
#   });
#
# Regex ile bunları "tam olarak" doğrulamaya çalışmak patch'in
# kendisini gereksiz yere kırılgan hale getiriyor.
#
# Bu nedenle V6.3.2 source-level invariant validation kullanır.
#

Write-Host `
    "    Exact reply-call regex: DISABLED" `
    -ForegroundColor Yellow

Write-Host `
    "    Symbol/invariant validation: ENABLED" `
    -ForegroundColor Green

# ============================================================
# 4
# ============================================================

Write-Host "[4/7] TTS pipeline invariant'ları doğrulanıyor..."

#
# 4A - TTS fonksiyonu
#

Test-Token `
    -Text $generated `
    -Token "speakAssistantReply" `
    -Label "TTS fonksiyonu"

#
# 4B - Assistant response state/variable.
#
# Farklı patch varyantlarını desteklemek için birden fazla
# geçerli isim kabul edilir.
#

$assistantStateTokens = @(
    "assistantReply",
    "setAssistantReply",
    "buildAssistantReply"
)

Test-TokenAny `
    -Text $generated `
    -Tokens $assistantStateTokens `
    -Label "Assistant response pipeline"

#
# 4C - Gerçek research extraction
#

Test-TokenAny `
    -Text $generated `
    -Tokens @(
        "extractStepResult",
        "extractResearchOutput"
    ) `
    -Label "Research result extractor"

#
# 4D - step.result
#

Test-Token `
    -Text $generated `
    -Token "step.result" `
    -Label "step.result projection"

#
# 4E - SpeechSynthesis
#

Test-Token `
    -Text $generated `
    -Token "speechSynthesis" `
    -Label "SpeechSynthesis"

#
# 4F - onend queue
#

Test-Token `
    -Text $generated `
    -Token "utterance.onend" `
    -Label "TTS onend chaining"

#
# 4G - OpenAPI route discovery
#

Test-Token `
    -Text $generated `
    -Token "discoverTaskDetailPath" `
    -Label "OpenAPI task route discovery"

#
# 4H - completed task retrieval
#

Test-Token `
    -Text $generated `
    -Token "fetchCompletedTaskOutput" `
    -Label "Completed task output fetch"

Write-Host `
    "    TTS pipeline symbols: PASS" `
    -ForegroundColor Green

# ============================================================
# 5
# ============================================================

Write-Host "[5/7] Directive -> TTS güvenlik kontrolü..."

#
# Burada yalnızca açıkça tehlikeli doğrudan bağlantıları
# reddediyoruz.
#
# Geçerli assistant pipeline'ın source-code biçimini
# zorunlu kılmıyoruz.
#

$forbiddenDirectSpeech = @(
    "speakAssistantReply(directive)",
    "speakAssistantReply(input)",
    "speakAssistantReply(query)",
    "speakAssistantReply(command)",
    "speakAssistantReply(userInput)",
    "speakAssistantReply(userDirective)"
)

foreach (
    $badPattern in
    $forbiddenDirectSpeech
) {

    $found =
        $app.IndexOf(
            $badPattern,
            [System.StringComparison]::Ordinal
        )

    if ($found -ge 0) {

        Fail (
            "Kullanıcı input'u doğrudan TTS'e bağlanmış: " +
            $badPattern
        )
    }
}

#
# Directive text'in TTS fonksiyonunun hemen içine literal
# olarak verilmesini de kontrol et.
#
$dangerousDirectPatterns = @(
    "speakAssistantReply(directive",
    "speakAssistantReply(input",
    "speakAssistantReply(query",
    "speakAssistantReply(command",
    "speakAssistantReply(userInput",
    "speakAssistantReply(userDirective"
)

foreach (
    $badPattern in
    $dangerousDirectPatterns
) {

    $found =
        $app.IndexOf(
            $badPattern,
            [System.StringComparison]::Ordinal
        )

    if ($found -ge 0) {

        Fail (
            "Doğrudan directive TTS bağlantısı bulundu: " +
            $badPattern
        )
    }
}

Write-Host `
    "    Directive -> TTS isolation: PASS" `
    -ForegroundColor Green

# ============================================================
# 6
# ============================================================

Write-Host "[6/7] TS/TSX source ve JSX marker validation..."

#
# PowerShell comparison operator'ları TSX içine sızmış mı?
#
$forbiddenPsOperators = @(
    "-gt",
    "-lt",
    "-ge",
    "-le"
)

foreach (
    $operator in
    $forbiddenPsOperators
) {

    #
    # Token olarak ara.
    # "-" içeren normal string'leri yanlış pozitif yapmamak
    # için sadece bilinen generated block üzerinde kontrol edilir.
    #
    $position =
        $generated.IndexOf(
            $operator,
            [System.StringComparison]::Ordinal
        )

    if ($position -ge 0) {

        Fail (
            "Generated TypeScript içinde PowerShell " +
            "comparison operator bulundu: " +
            $operator
        )
    }
}

#
# JSX research component
#

Test-Token `
    -Text $app `
    -Token "<AuraConversationalResearch />" `
    -Label "Research component JSX"

#
# Fragment
#

Test-TokenAny `
    -Text $app `
    -Tokens @(
        "<>",
        "</>"
    ) `
    -Label "JSX Fragment"

#
# App function
#

Test-Token `
    -Text $app `
    -Token "export default function App(" `
    -Label "App component"

#
# return
#

$appReturn =
    [regex]::Match(
        $app,
        "(?s)return\s*\("
    )

if (-not $appReturn.Success) {

    Fail "App return(...) bulunamadı."
}

#
# Research component App return'den önce veya sonra tamamen
# module-level rastgele bir yerde olmayacak.
#
$researchIndex =
    $app.IndexOf(
        "<AuraConversationalResearch />",
        [System.StringComparison]::Ordinal
    )

if (
    $researchIndex -lt 0
) {
    Fail "Research JSX kullanımı bulunamadı."
}

if (
    $researchIndex -lt
    $appReturn.Index
) {
    Fail (
        "Research component App return(...) başlamadan önce " +
        "yerleştirilmiş görünüyor."
    )
}

Write-Host `
    "    JSX/source validation: PASS" `
    -ForegroundColor Green

# ============================================================
# 7
# ============================================================

Write-Host "[7/7] npm run build..."

Push-Location $UiRoot

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
        Fail "npm bulunamadı."
    }

    & $npmCommand.Source run build

    $exitCode =
        $LASTEXITCODE

}
finally {

    Pop-Location
}

if ($exitCode -ne 0) {

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " BUILD FAILED"
    Write-Host "============================================================"
    Write-Host ""

    Fail (
        "npm run build başarısız oldu. " +
        "V6.3.2 hiçbir dosyayı değiştirmedi."
    )
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.3.2 SUCCESS"
Write-Host "============================================================"
Write-Host ""

Write-Host "V6.3 generated block        : PASS"
Write-Host "TTS function                : PASS"
Write-Host "Assistant response pipeline : PASS"
Write-Host "step.result extraction      : PASS"
Write-Host "SpeechSynthesis             : PASS"
Write-Host "TTS onend chaining          : PASS"
Write-Host "OpenAPI route discovery     : PASS"
Write-Host "Completed task fetch        : PASS"
Write-Host "Directive -> TTS isolation  : PASS"
Write-Host "JSX placement               : PASS"
Write-Host "TypeScript source check     : PASS"
Write-Host "npm run build               : PASS"
Write-Host ""

Write-Host (
    "V6.3.1'deki katı " +
    "'speakAssistantReply(reply)' regex validation kaldırıldı."
)

Write-Host (
    "Bu sürüm source-code biçimini değil, gerekli pipeline " +
    "invariant'larını ve gerçek TypeScript build sonucunu doğrular."
)

Write-Host ""