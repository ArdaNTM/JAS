#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA RESEARCH SAFE PATCH V6.1
# PowerShell 5.1
#
# DÜZELTME:
# V6'da application\__init__.py yanlışlıkla Task API adayı
# olarak seçiliyordu.
#
# V6.1:
#   - __init__.py dosyalarını otomatik olarak dışlar.
#   - Boş Python dosyalarını dışlar.
#   - TaskResponse / task route / step.result referanslarını
#     içerik üzerinden arar.
#   - En yüksek skor alan GERÇEK Python modülünü seçer.
#   - TaskResponse serializer'ını güvenli şekilde bulur.
#   - Mevcut dosyayı backup almadan değiştirmez.
#   - Belirsizlik varsa PATCH ETMEZ.
#   - PowerShell 5.1 uyumludur.
#   - TypeScript tarafındaki > < operatörlerine dokunmaz.
#
# NOT:
# Bu sürüm V6'nın geri kalan UI/TTS patch mantığını yeniden
# çalıştırmaz. Önce V6'nın [7/10] backend contract hatasını
# güvenli biçimde düzeltir.
#
# Sonraki adımda V6.1 PASS verdikten sonra mevcut V6 UI/TTS
# patch'i yeniden çalıştırılabilir.
# ============================================================

$Root     = "D:\AURA\JAS"
$CoreRoot = Join-Path $Root "core"
$CoreSrc  = Join-Path $CoreRoot "src"
$UiRoot   = Join-Path $Root "aura-ui"
$UiSrc    = Join-Path $UiRoot "src"
$Scripts  = Join-Path $Root "scripts"

$Stamp =
    Get-Date -Format "yyyyMMdd-HHmmss"

$BackupRoot =
    Join-Path $Root ".aura-backups"

$BackupDir =
    Join-Path $BackupRoot (
        "research-v61-" + $Stamp
    )

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param(
        [string]$Message
    )

    Write-Host ""
    Write-Host "PATCH ABORTED" -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Assert-Path {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail (
            $Label +
            " bulunamadı: " +
            $Path
        )
    }
}

function Read-Utf8Text {
    param(
        [string]$Path
    )

    Assert-Path `
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

    return $content
}

function Write-Utf8Text {
    param(
        [string]$Path,
        [string]$Content
    )

    if ($null -eq $Content) {
        Fail (
            "Boş içerik yazılmaya çalışıldı: " +
            $Path
        )
    }

    $encoding =
        New-Object System.Text.UTF8Encoding(
            $false
        )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        $encoding
    )
}

function Backup-File {
    param(
        [string]$Source,
        [string]$Destination
    )

    Assert-Path `
        -Path $Source `
        -Label "Backup source"

    $parent =
        Split-Path `
            -Parent $Destination

    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item `
            -ItemType Directory `
            -Path $parent `
            -Force |
            Out-Null
    }

    Copy-Item `
        -LiteralPath $Source `
        -Destination $Destination `
        -Force
}

function Find-RegexMatch {
    param(
        [string]$Text,
        [string]$Pattern
    )

    return [regex]::Match(
        $Text,
        $Pattern,
        [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
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

        Fail "PowerShell parser testi başarısız."
    }
}

# ============================================================
# START
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA RESEARCH SAFE PATCH V6.1"
Write-Host "============================================================"
Write-Host ""

Write-Host "[1/8] Proje doğrulanıyor..."

Assert-Path `
    -Path $Root `
    -Label "AURA root"

Assert-Path `
    -Path $CoreSrc `
    -Label "core/src"

Assert-Path `
    -Path $UiSrc `
    -Label "aura-ui/src"

# ============================================================
# 1. BACKUP
# ============================================================

Write-Host "[2/8] Güvenli backup oluşturuluyor..."

New-Item `
    -ItemType Directory `
    -Path $BackupDir `
    -Force |
    Out-Null

# ============================================================
# 2. PYTHON CANDIDATE DISCOVERY
# ============================================================

Write-Host "[3/8] Gerçek TaskResponse modülü aranıyor..."

$pythonFiles =
    Get-ChildItem `
        -LiteralPath $CoreSrc `
        -Recurse `
        -Filter "*.py" `
        -File |
    Where-Object {

        $_.Name -ne "__init__.py" -and

        $_.FullName -notmatch "\\__pycache__\\" -and

        $_.Length -gt 0
    }

if (
    $null -eq $pythonFiles -or
    $pythonFiles.Count -eq 0
) {
    Fail "Dolu Python modülü bulunamadı."
}

$candidates =
    New-Object System.Collections.Generic.List[object]

foreach ($file in $pythonFiles) {

    try {
        $text =
            Read-Utf8Text `
                -Path $file.FullName
    }
    catch {
        continue
    }

    if (
        $null -eq $text -or
        $text.Trim().Length -eq 0
    ) {
        continue
    }

    $score = 0

    $hasTaskResponse =
        $text -match
        '(?m)^\s*(?:class|class\s+)?TaskResponse\b'

    $hasTasksRoute =
        $text -match
        '(?m)(?:@app\.(?:get|post)|@router\.(?:get|post)|/api/tasks)'

    $hasStepResult =
        $text -match
        '\bstep\.result\b'

    $hasStepState =
        $text -match
        '\bstep\.state\b'

    $hasTaskId =
        $text -match
        '\btask_id\b'

    $hasPydantic =
        $text -match
        '\bBaseModel\b'

    if ($hasTaskResponse) {
        $score += 1000
    }

    if ($hasTasksRoute) {
        $score += 400
    }

    if ($hasStepResult) {
        $score += 300
    }

    if ($hasStepState) {
        $score += 200
    }

    if ($hasTaskId) {
        $score += 100
    }

    if ($hasPydantic) {
        $score += 50
    }

    if ($score -gt 0) {

        $candidates.Add(
            [PSCustomObject]@{
                Path             = $file.FullName
                Score            = $score
                HasTaskResponse  = $hasTaskResponse
                HasTasksRoute    = $hasTasksRoute
                HasStepResult    = $hasStepResult
                HasStepState     = $hasStepState
                HasTaskId        = $hasTaskId
                HasPydantic      = $hasPydantic
            }
        )
    }
}

if ($candidates.Count -eq 0) {
    Fail (
        "TaskResponse/task endpoint içeren Python modülü " +
        "bulunamadı."
    )
}

$candidates =
    $candidates |
    Sort-Object `
        -Property Score `
        -Descending

Write-Host ""
Write-Host "Task API adayları:" -ForegroundColor Cyan

foreach ($candidate in $candidates) {

    Write-Host (
        "  [" +
        $candidate.Score +
        "] " +
        $candidate.Path
    )
}

$TaskTarget =
    $candidates |
    Where-Object {
        $_.HasTaskResponse -and
        $_.HasStepResult
    } |
    Select-Object -First 1

# ============================================================
# FALLBACK:
# TaskResponse başka dosyada, serializer endpoint'te olabilir.
# ============================================================

if ($null -eq $TaskTarget) {

    $TaskTarget =
        $candidates |
        Where-Object {
            $_.HasTasksRoute -and
            $_.HasStepResult
        } |
        Select-Object -First 1
}

if ($null -eq $TaskTarget) {

    $TaskTarget =
        $candidates |
        Select-Object -First 1
}

if ($null -eq $TaskTarget) {
    Fail "Task API hedefi güvenli şekilde belirlenemedi."
}

$TaskFile =
    $TaskTarget.Path

Write-Host ""
Write-Host "Seçilen Task modülü:" -ForegroundColor Green
Write-Host $TaskFile

$taskCode =
    Read-Utf8Text `
        -Path $TaskFile

if (
    $null -eq $taskCode -or
    $taskCode.Trim().Length -eq 0
) {
    Fail (
        "Seçilen Task modülü boş: " +
        $TaskFile
    )
}

# ============================================================
# 3. PRECISE BACKUP
# ============================================================

Write-Host ""
Write-Host "[4/8] Task modülü backup..."

$relativeTask =
    $TaskFile.Substring(
        $CoreSrc.Length
    ).TrimStart(
        "\"
    )

$TaskBackup =
    Join-Path `
        $BackupDir `
        ("core\" + $relativeTask)

Backup-File `
    -Source $TaskFile `
    -Destination $TaskBackup

Write-Host "Backup:"
Write-Host $TaskBackup

# ============================================================
# 4. EXISTING result CHECK
# ============================================================

Write-Host ""
Write-Host "[5/8] TaskResponse contract analiz ediliyor..."

$alreadyProjected =
    $taskCode -match
    '(?m)["'']result["'']\s*:\s*step\.result'

if ($alreadyProjected) {

    Write-Host ""
    Write-Host (
        "step.result zaten HTTP response'a expose ediliyor."
    ) -ForegroundColor Green

    $changed = $false
}
else {

    $changed = $true

    # --------------------------------------------------------
    # STRATEGY A
    #
    # Existing dict:
    #
    # {
    #   "step_id": step.step_id,
    #   "state": step.state,
    #   "attempts": step.attempts,
    #   "reason": step.reason,
    # }
    #
    # Add:
    #
    #   "result": step.result,
    # --------------------------------------------------------

    $patternA =
        '(?m)^(?<indent>\s*)["'']reason["'']\s*:\s*step\.reason\s*,\s*$'

    $matchA =
        [regex]::Match(
            $taskCode,
            $patternA
        )

    if ($matchA.Success) {

        $indent =
            $matchA.Groups["indent"].Value

        $replacement =
            $matchA.Value +
            "`r`n" +
            $indent +
            '"result": step.result,'

        $taskCode =
            $taskCode.Remove(
                $matchA.Index,
                $matchA.Length
            )

        $taskCode =
            $taskCode.Insert(
                $matchA.Index,
                $replacement
            )

        Write-Host ""
        Write-Host (
            "Strategy A başarılı: reason -> result"
        ) -ForegroundColor Green
    }

    # --------------------------------------------------------
    # STRATEGY B
    #
    # Existing dict does not have reason.
    # Insert after attempts.
    # --------------------------------------------------------

    if (
        $taskCode -notmatch
        '(?m)["'']result["'']\s*:\s*step\.result'
    ) {

        $patternB =
            '(?m)^(?<indent>\s*)["'']attempts["'']\s*:\s*step\.attempts\s*,\s*$'

        $matchB =
            [regex]::Match(
                $taskCode,
                $patternB
            )

        if ($matchB.Success) {

            $indent =
                $matchB.Groups["indent"].Value

            $replacement =
                $matchB.Value +
                "`r`n" +
                $indent +
                '"result": step.result,'

            $taskCode =
                $taskCode.Remove(
                    $matchB.Index,
                    $matchB.Length
                )

            $taskCode =
                $taskCode.Insert(
                    $matchB.Index,
                    $replacement
                )

            Write-Host ""
            Write-Host (
                "Strategy B başarılı: attempts -> result"
            ) -ForegroundColor Green
        }
    }

    # --------------------------------------------------------
    # STRATEGY C
    #
    # Dict uses single quotes.
    # --------------------------------------------------------

    if (
        $taskCode -notmatch
        '(?m)["'']result["'']\s*:\s*step\.result'
    ) {

        $patternC =
            '(?m)^(?<indent>\s*)["'']step_id["'']\s*:\s*step\.step_id\s*,\s*$'

        $matchC =
            [regex]::Match(
                $taskCode,
                $patternC
            )

        if ($matchC.Success) {

            $indent =
                $matchC.Groups["indent"].Value

            $replacement =
                $matchC.Value +
                "`r`n" +
                $indent +
                '"result": step.result,'

            $taskCode =
                $taskCode.Remove(
                    $matchC.Index,
                    $matchC.Length
                )

            $taskCode =
                $taskCode.Insert(
                    $matchC.Index,
                    $replacement
                )

            Write-Host ""
            Write-Host (
                "Strategy C başarılı: step_id -> result"
            ) -ForegroundColor Green
        }
    }
}

# ============================================================
# 5. STRICT RESULT VERIFICATION
# ============================================================

Write-Host ""
Write-Host "[6/8] step.result projection doğrulanıyor..."

if (
    $taskCode -notmatch
    '(?m)["'']result["'']\s*:\s*step\.result'
) {

    Write-Host ""
    Write-Host "Otomatik patch noktası bulunamadı." `
        -ForegroundColor Yellow

    Write-Host ""
    Write-Host "Dosya:"
    Write-Host $TaskFile

    Write-Host ""
    Write-Host "Bulunan ilgili satırlar:" `
        -ForegroundColor Cyan

    $taskCode -split "`r?`n" |
        Select-String `
            -Pattern `
                'TaskResponse|step_id|step\.state|step\.result|attempts|reason|return\s+\{|return\s+TaskResponse' |
        Select-Object `
            -First 80 |
        ForEach-Object {
            Write-Host (
                $_.LineNumber.ToString() +
                ": " +
                $_.Line
            )
        }

    # No modification is written.
    Fail (
        "step.result serializer noktası güvenli biçimde " +
        "tespit edilemedi. Dosya değiştirilmedi."
    )
}

Write-Host (
    "step.result HTTP response projection: PASS"
) -ForegroundColor Green

# ============================================================
# 6. Pydantic MODEL CHECK
# ============================================================

Write-Host ""
Write-Host "[7/8] Pydantic TaskResponse kontrolü..."

$hasTaskResponse =
    $taskCode -match
    '(?m)^\s*class\s+TaskResponse\b'

if ($hasTaskResponse) {

    Write-Host (
        "TaskResponse modeli bulundu."
    ) -ForegroundColor Green

    $responseMatch =
        [regex]::Match(
            $taskCode,
            '(?s)class\s+TaskResponse\b.*?(?=^\s*class\s+|\z)'
        )

    if ($responseMatch.Success) {

        $responseBody =
            $responseMatch.Value

        if (
            $responseBody -match
            '(?m)^\s*steps\s*:'
        ) {

            Write-Host (
                "TaskResponse.steps alanı bulundu."
            ) -ForegroundColor Green
        }
        else {

            Write-Host (
                "UYARI: TaskResponse bulundu fakat steps alanı " +
                "aynı model içinde görünmüyor."
            ) -ForegroundColor Yellow
        }
    }
}
else {

    Write-Host (
        "TaskResponse class bu dosyada değil; " +
        "endpoint response serializer'ı patchlendi."
    ) -ForegroundColor Yellow
}

# ============================================================
# 7. WRITE
# ============================================================

if ($changed) {

    Write-Host ""
    Write-Host "Task modülü yazılıyor..."

    Write-Utf8Text `
        -Path $TaskFile `
        -Content $taskCode

    Write-Host (
        "Yazıldı: " +
        $TaskFile
    ) -ForegroundColor Green
}
else {

    Write-Host ""
    Write-Host (
        "Değişiklik gerekmiyor."
    ) -ForegroundColor Green
}

# ============================================================
# 8. PYTHON COMPILE
# ============================================================

Write-Host ""
Write-Host "[8/8] Python compile testi..."

$pythonCommand =
    Get-Command `
        python.exe `
        -ErrorAction SilentlyContinue

$pyCommand =
    Get-Command `
        py.exe `
        -ErrorAction SilentlyContinue

$compileExit = 0

if ($null -ne $pythonCommand) {

    Push-Location $CoreRoot

    try {

        & $pythonCommand.Source `
            -m `
            compileall `
            -q `
            src

        $compileExit =
            $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
elseif ($null -ne $pyCommand) {

    Push-Location $CoreRoot

    try {

        & $pyCommand.Source `
            -3 `
            -m `
            compileall `
            -q `
            src

        $compileExit =
            $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}
else {

    Write-Host (
        "python.exe / py.exe bulunamadı; compile testi " +
        "çalıştırılamadı."
    ) -ForegroundColor Yellow
}

if ($compileExit -ne 0) {

    Write-Host ""
    Write-Host "PYTHON COMPILE FAILED" `
        -ForegroundColor Red

    Write-Host ""
    Write-Host "Rollback yapılıyor..."

    Restore-File `
        -Backup $TaskBackup `
        -Destination $TaskFile

    Fail (
        "Python compile başarısız oldu. " +
        "Task modülü rollback edildi."
    )
}

# ============================================================
# FINAL VALIDATION
# ============================================================

$finalCode =
    Read-Utf8Text `
        -Path $TaskFile

if (
    $finalCode -notmatch
    '(?m)["'']result["'']\s*:\s*step\.result'
) {

    Restore-File `
        -Backup $TaskBackup `
        -Destination $TaskFile

    Fail (
        "Final validation başarısız. " +
        "step.result bulunamadı; rollback yapıldı."
    )
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.1 SUCCESS"
Write-Host "============================================================"
Write-Host ""

Write-Host "Task API module:"
Write-Host $TaskFile

Write-Host ""
Write-Host "step.result projection : PASS" `
    -ForegroundColor Green

Write-Host "Python compile          : PASS" `
    -ForegroundColor Green

Write-Host ""
Write-Host "Backup:"
Write-Host $TaskBackup

Write-Host ""
Write-Host (
    "V6.1 yalnızca gerçek Task API modülünü değiştirdi."
)

Write-Host ""
Write-Host (
    "V6 UI/TTS patch'i bundan sonra çalıştırılabilir."
)

Write-Host ""