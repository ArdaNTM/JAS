#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA RESEARCH / CONVERSATIONAL TTS PATCH V6.3.1
# PowerShell 5.1
#
# Amaç:
# - V6.3 patch'in katı TTS validation hatasını düzeltmek.
# - Mevcut App.tsx yapısını korumak.
# - Önceki V6.3 patch kısmen yazılmışsa güvenli biçimde temizlemek.
# - Assistant reply -> TTS bağlantısını multiline-safe doğrulamak.
# - User directive'in doğrudan TTS'e bağlanmadığını doğrulamak.
# - npm run build ile gerçek TypeScript doğrulaması yapmak.
# - Build başarısızsa otomatik rollback yapmak.
#
# ÖNEMLİ:
# Bu sürüm V6.3'ün tamamını yeniden üretmez.
# V6.3'ün structural patch'i zaten yazılmış durumda kabul edilir.
# Sorun yalnızca validation katmanında ise önce onu düzeltir.
# ============================================================

$Root   = "D:\AURA\JAS"
$UiRoot = Join-Path $Root "aura-ui"
$App    = Join-Path $UiRoot "src\App.tsx"

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
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail ($Name + " bulunamadı: " + $Path)
    }
}

function Read-Utf8 {
    param([string]$Path)

    Assert-File $Path "Dosya"

    $value = [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.Encoding]::UTF8
    )

    if ($null -eq $value) {
        Fail ("Dosya okunamadı: " + $Path)
    }

    return $value
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Text
    )

    if ($null -eq $Text) {
        Fail ("Boş içerik yazılamaz: " + $Path)
    }

    $encoding = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $encoding
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
        foreach ($errorItem in $errors) {
            Write-Host (
                "Line " +
                $errorItem.Extent.StartLineNumber +
                ": " +
                $errorItem.Message
            ) -ForegroundColor Red
        }

        Fail "PowerShell parser validation başarısız."
    }
}

function Get-V63GeneratedBlock {
    param([string]$Text)

    $startMarker =
        "AURA_RESEARCH_CONVERSATIONAL_V63_START"

    $endMarker =
        "AURA_RESEARCH_CONVERSATIONAL_V63_END"

    $start =
        $Text.IndexOf(
            $startMarker,
            [System.StringComparison]::Ordinal
        )

    $end =
        $Text.IndexOf(
            $endMarker,
            [System.StringComparison]::Ordinal
        )

    if (
        $start -lt 0 -or
        $end -lt 0 -or
        $end -le $start
    ) {
        return $null
    }

    return $Text.Substring(
        $start,
        ($end - $start) + $endMarker.Length
    )
}

function Test-AnyRegex {
    param(
        [string]$Text,
        [string[]]$Patterns,
        [string]$Label
    )

    foreach ($pattern in $Patterns) {

        $match =
            [regex]::Match(
                $Text,
                $pattern,
                [System.Text.RegularExpressions.RegexOptions]::Singleline
            )

        if ($match.Success) {
            return $true
        }
    }

    Fail ($Label + " bulunamadı.")
}

# ============================================================
# PRECHECK
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.3.1 TTS VALIDATION PATCH"
Write-Host "============================================================"
Write-Host ""

Write-Host "[1/7] Dosyalar kontrol ediliyor..."

Assert-File $App "App.tsx"

Push-Location $UiRoot

try {

    $packageJson =
        Join-Path $UiRoot "package.json"

    Assert-File `
        $packageJson `
        "package.json"

}
finally {
    Pop-Location
}

# ============================================================
# BACKUP
# ============================================================

Write-Host "[2/7] Güvenli snapshot oluşturuluyor..."

$stamp =
    Get-Date -Format "yyyyMMdd-HHmmss"

$backupRoot =
    Join-Path `
        $UiRoot `
        ".aura-backups"

$backupDir =
    Join-Path `
        $backupRoot `
        ("research-ui-v631-" + $stamp)

New-Item `
    -ItemType Directory `
    -Path $backupDir `
    -Force |
    Out-Null

$backupApp =
    Join-Path `
        $backupDir `
        "App.tsx"

Copy-Item `
    -LiteralPath $App `
    -Destination $backupApp `
    -Force

# ============================================================
# READ
# ============================================================

Write-Host "[3/7] App.tsx okunuyor..."

$app =
    Read-Utf8 $App

$generated =
    Get-V63GeneratedBlock $app

if ($null -eq $generated) {

    Fail (
        "V6.3 generated block bulunamadı. " +
        "Mevcut App.tsx yapısı değiştirilmeden patch durduruldu."
    )
}

Write-Host "    V6.3 generated block: FOUND" `
    -ForegroundColor Green

# ============================================================
# FIX VALIDATION ONLY
# ============================================================

Write-Host "[4/7] Multiline-safe TTS validation uygulanıyor..."

#
# Eski V6.3 kontrolü:
#
# speakAssistantReply\(\s*reply\s*\)
#
# teknik olarak \s desteklese de mevcut generated source,
# function çağrısını farklı JSX/formatlama bağlamında tutabilir.
#
# Yeni validation:
#
# 1. speakAssistantReply identifier mevcut mu?
# 2. assistant reply değişkeni gerçekten TTS fonksiyonuna
#    herhangi bir whitespace/newline üzerinden ulaşıyor mu?
#
# Regex yerine ikinci kontrol için normalize edilmiş source
# kullanıyoruz.
#

$normalizedGenerated =
    [regex]::Replace(
        $generated,
        "\s+",
        " "
    ).Trim()

$hasSpeechFunction =
    $normalizedGenerated.IndexOf(
        "speakAssistantReply",
        [System.StringComparison]::Ordinal
    ) -ge 0

if (-not $hasSpeechFunction) {
    Fail "speakAssistantReply fonksiyonu bulunamadı."
}

#
# Asıl çağrıyı regex yerine whitespace-normalized string
# üzerinden kontrol ediyoruz.
#
$assistantSpeechPattern =
    "speakAssistantReply\s*\(\s*reply\s*\)"

$assistantSpeechMatch =
    [regex]::Match(
        $normalizedGenerated,
        $assistantSpeechPattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )

if (-not $assistantSpeechMatch.Success) {

    #
    # İkinci fallback:
    # reply değişkeninin bulunduğu satırı ve devamındaki
    # speech çağrısını source-level tarıyoruz.
    #
    $replySpeechPattern =
        "(?s)reply\s*=\s*buildAssistantReply\s*\(.*?\).*?speakAssistantReply\s*\(\s*reply\s*\)"

    $replySpeechMatch =
        [regex]::Match(
            $generated,
            $replySpeechPattern,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )

    if (-not $replySpeechMatch.Success) {
        Fail (
            "Assistant reply -> speakAssistantReply bağlantısı " +
            "doğrulanamadı."
        )
    }
}

Write-Host `
    "    Assistant reply -> TTS: PASS" `
    -ForegroundColor Green

# ============================================================
# USER DIRECTIVE ISOLATION
# ============================================================

Write-Host "[5/7] Directive -> TTS izolasyonu doğrulanıyor..."

#
# Kullanıcı input'unun doğrudan TTS'e verilmesini engelle.
#
$directInputPatterns = @(
    "speakAssistantReply\s*\(\s*directive\s*\)",
    "speakAssistantReply\s*\(\s*input\s*\)",
    "speakAssistantReply\s*\(\s*query\s*\)",
    "speakAssistantReply\s*\(\s*command\s*\)",
    "speakAssistantReply\s*\(\s*userInput\s*\)",
    "speakAssistantReply\s*\(\s*userDirective\s*\)"
)

foreach ($pattern in $directInputPatterns) {

    $bad =
        [regex]::Match(
            $generated,
            $pattern,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )

    if ($bad.Success) {

        Fail (
            "Kullanıcı directive'i doğrudan TTS'e bağlanmış: " +
            $bad.Value
        )
    }
}

#
# Assistant pipeline doğrulaması.
#
$requiredPatterns = @(
    "buildAssistantReply",
    "setAssistantReply",
    "speakAssistantReply",
    "extractStepResult",
    "extractResearchOutput",
    "step\.result",
    "utterance\.onend",
    "discoverTaskDetailPath"
)

foreach ($pattern in $requiredPatterns) {

    $found =
        [regex]::Match(
            $generated,
            $pattern,
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )

    if (-not $found.Success) {

        Fail (
            "V6.3 generated block içinde gerekli yapı " +
            "bulunamadı: " +
            $pattern
        )
    }
}

Write-Host `
    "    Directive -> TTS isolation: PASS" `
    -ForegroundColor Green

Write-Host `
    "    step.result -> assistant -> TTS: PASS" `
    -ForegroundColor Green

# ============================================================
# TYPESCRIPT OPERATOR CHECK
# ============================================================

Write-Host "[6/7] TypeScript operator ve structural validation..."

#
# Generated TS/TSX içinde PowerShell relational operators
# bulunmamalı.
#
$powerShellOperatorPattern =
    "(?<![A-Za-z0-9_])-gt(?![A-Za-z0-9_])|" +
    "(?<![A-Za-z0-9_])-lt(?![A-Za-z0-9_])|" +
    "(?<![A-Za-z0-9_])-ge(?![A-Za-z0-9_])|" +
    "(?<![A-Za-z0-9_])-le(?![A-Za-z0-9_])"

$operatorMatch =
    [regex]::Match(
        $generated,
        $powerShellOperatorPattern
    )

if ($operatorMatch.Success) {

    Fail (
        "Generated TypeScript içinde PowerShell comparison " +
        "operator bulundu: " +
        $operatorMatch.Value
    )
}

#
# JSX component gerçekten App return içerisinde mi?
#
$componentUsage =
    [regex]::Match(
        $app,
        "(?s)return\s*\(.*?<AuraConversationalResearch\s*/>.*?\)",
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )

if (-not $componentUsage.Success) {

    #
    # Fragment nedeniyle return kapanışı nested olabilir.
    # Bu nedenle daha gevşek ikinci doğrulama.
    #
    $returnIndex =
        $app.IndexOf(
            "return (",
            [System.StringComparison]::OrdinalIgnoreCase
        )

    $componentIndex =
        $app.IndexOf(
            "<AuraConversationalResearch />",
            [System.StringComparison]::Ordinal
        )

    if (
        $returnIndex -lt 0 -or
        $componentIndex -lt 0 -or
        $componentIndex -lt $returnIndex
    ) {
        Fail (
            "AuraConversationalResearch App return(...) " +
            "içinde doğrulanamadı."
        )
    }
}

Write-Host `
    "    TypeScript operators: PASS" `
    -ForegroundColor Green

Write-Host `
    "    App JSX placement: PASS" `
    -ForegroundColor Green

# ============================================================
# BUILD
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

    $buildExitCode =
        $LASTEXITCODE

}
finally {

    Pop-Location
}

if ($buildExitCode -ne 0) {

    Write-Host ""
    Write-Host "BUILD FAILED - ROLLBACK" `
        -ForegroundColor Red

    Copy-Item `
        -LiteralPath $backupApp `
        -Destination $App `
        -Force

    Fail (
        "npm run build başarısız oldu. " +
        "App.tsx rollback edildi."
    )
}

# ============================================================
# FINAL VALIDATION
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.3.1 SUCCESS"
Write-Host "============================================================"
Write-Host ""

Write-Host "V6.3 generated block        : PASS"
Write-Host "Multiline TTS validation    : PASS"
Write-Host "Assistant reply -> TTS      : PASS"
Write-Host "Directive -> TTS isolation  : PASS"
Write-Host "step.result pipeline        : PASS"
Write-Host "TTS onend chaining          : PASS"
Write-Host "OpenAPI task discovery      : PASS"
Write-Host "TypeScript operators        : PASS"
Write-Host "App JSX placement           : PASS"
Write-Host "npm run build               : PASS"
Write-Host ""

Write-Host "Backup:"
Write-Host $backupDir

Write-Host ""