# ============================================================
# AURA V6.5.9
# JARVIS / TYPESCRIPT CLEANUP + DETERMINISTIC JSX PLACEMENT
# ============================================================

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = 'D:\AURA\JAS'
$Ui = Join-Path $Root 'aura-ui'
$Src = Join-Path $Ui 'src'
$App = Join-Path $Src 'App.tsx'
$Bridge = Join-Path $Src 'AuraJarvisBridge.tsx'

$BackupRoot = Join-Path $Root 'backups'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupDir = Join-Path $BackupRoot "v659_$Stamp"

function Write-Step {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.9 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red

    throw $Message
}

function Read-Utf8 {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail ("Dosya bulunamadı: {0}" -f $Path)
    }

    return [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Write-Utf8 {
    param(
        [string]$Path,
        [string]$Content
    )

    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Find-MatchingParen {
    param(
        [string]$Text,
        [int]$OpenIndex
    )

    if ($OpenIndex -lt 0 -or $OpenIndex -ge $Text.Length) {
        throw ("Geçersiz parantez başlangıcı: {0}" -f $OpenIndex)
    }

    if ($Text[$OpenIndex] -ne '(') {
        throw ("Verilen index '(' karakteri değil: {0}" -f $OpenIndex)
    }

    $depth = 0
    $quote = [char]0
    $template = $false
    $escape = $false
    $lineComment = $false
    $blockComment = $false

    for ($i = $OpenIndex; $i -lt $Text.Length; $i++) {
        $c = $Text[$i]
        $next = if ($i + 1 -lt $Text.Length) {
            $Text[$i + 1]
        }
        else {
            [char]0
        }

        if ($lineComment) {
            if ($c -eq "`n") {
                $lineComment = $false
            }
            continue
        }

        if ($blockComment) {
            if ($c -eq '*' -and $next -eq '/') {
                $blockComment = $false
                $i++
            }
            continue
        }

        if ($quote -ne [char]0) {
            if ($escape) {
                $escape = $false
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                continue
            }

            if ($c -eq $quote) {
                $quote = [char]0
            }

            continue
        }

        if ($template) {
            if ($escape) {
                $escape = $false
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                continue
            }

            if ($c -eq '`') {
                $template = $false
            }

            continue
        }

        if ($c -eq '/' -and $next -eq '/') {
            $lineComment = $true
            $i++
            continue
        }

        if ($c -eq '/' -and $next -eq '*') {
            $blockComment = $true
            $i++
            continue
        }

        if ($c -eq '"' -or $c -eq "'") {
            $quote = $c
            continue
        }

        if ($c -eq '`') {
            $template = $true
            continue
        }

        if ($c -eq '(') {
            $depth++
            continue
        }

        if ($c -eq ')') {
            $depth--

            if ($depth -eq 0) {
                return $i
            }
        }
    }

    throw ("Eşleşen ')' bulunamadı. Başlangıç index: {0}" -f $OpenIndex)
}

function Find-AppScope {
    param([string]$Text)

    $appMatch = [regex]::Match(
        $Text,
        '(?m)(?:export\s+default\s+)?function\s+App\s*\('
    )

    if (-not $appMatch.Success) {
        $appMatch = [regex]::Match(
            $Text,
            '(?m)(?:export\s+default\s+)?const\s+App\s*='
        )
    }

    if (-not $appMatch.Success) {
        throw 'App component scope bulunamadı.'
    }

    $start = $appMatch.Index

    $braceIndex = $Text.IndexOf(
        '{',
        $appMatch.Index + $appMatch.Length
    )

    if ($braceIndex -lt 0) {
        throw 'App component açılış { bulunamadı.'
    }

    $depth = 0
    $quote = [char]0
    $template = $false
    $escape = $false
    $lineComment = $false
    $blockComment = $false

    for ($i = $braceIndex; $i -lt $Text.Length; $i++) {
        $c = $Text[$i]
        $next = if ($i + 1 -lt $Text.Length) {
            $Text[$i + 1]
        }
        else {
            [char]0
        }

        if ($lineComment) {
            if ($c -eq "`n") {
                $lineComment = $false
            }
            continue
        }

        if ($blockComment) {
            if ($c -eq '*' -and $next -eq '/') {
                $blockComment = $false
                $i++
            }
            continue
        }

        if ($quote -ne [char]0) {
            if ($escape) {
                $escape = $false
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                continue
            }

            if ($c -eq $quote) {
                $quote = [char]0
            }

            continue
        }

        if ($template) {
            if ($escape) {
                $escape = $false
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                continue
            }

            if ($c -eq '`') {
                $template = $false
            }

            continue
        }

        if ($c -eq '/' -and $next -eq '/') {
            $lineComment = $true
            $i++
            continue
        }

        if ($c -eq '/' -and $next -eq '*') {
            $blockComment = $true
            $i++
            continue
        }

        if ($c -eq '"' -or $c -eq "'") {
            $quote = $c
            continue
        }

        if ($c -eq '`') {
            $template = $true
            continue
        }

        if ($c -eq '{') {
            $depth++
        }
        elseif ($c -eq '}') {
            $depth--

            if ($depth -eq 0) {
                return @{
                    Start = $start
                    Open = $braceIndex
                    Close = $i
                }
            }
        }
    }

    throw 'App component kapanış } bulunamadı.'
}

function Find-MainJsxReturn {
    param(
        [string]$Text,
        [int]$AppOpen,
        [int]$AppClose
    )

    $scope = $Text.Substring(
        $AppOpen,
        $AppClose - $AppOpen + 1
    )

    $matches = [regex]::Matches(
        $scope,
        '(?m)\breturn\s*\('
    )

    if ($matches.Count -eq 0) {
        throw 'App içinde JSX return ( bulunamadı.'
    }

    foreach ($m in $matches) {
        $globalReturn = $AppOpen + $m.Index

        $openParen = $Text.IndexOf(
            '(',
            $globalReturn + $m.Length - 1
        )

        if ($openParen -lt 0) {
            continue
        }

        try {
            $closeParen = Find-MatchingParen `
                -Text $Text `
                -OpenIndex $openParen

            if ($closeParen -lt $AppClose) {
                return @{
                    ReturnStart = $globalReturn
                    OpenParen = $openParen
                    CloseParen = $closeParen
                }
            }
        }
        catch {
            continue
        }
    }

    throw 'App içindeki ana JSX return (...) bloğu belirlenemedi.'
}

function Remove-ImportIdentifier {
    param(
        [string]$Text,
        [string]$Identifier
    )

    $lines = $Text -split "`r?`n"
    $out = New-Object System.Collections.Generic.List[string]

    foreach ($line in $lines) {
        if (
            $line -match '^\s*import\b' -and
            $line -match ("\b{0}\b" -f [regex]::Escape($Identifier))
        ) {
            $newLine = $line

            $newLine = [regex]::Replace(
                $newLine,
                "(?<![\w`$]){0}(?![\w`$])\s*,?\s*" -f `
                    [regex]::Escape($Identifier),
                ''
            )

            $newLine = $newLine -replace ',\s*,', ','
            $newLine = $newLine -replace '\{\s*,', '{'
            $newLine = $newLine -replace ',\s*\}', '}'

            if ($newLine -match '^\s*import\s+\{\s*\}\s+from') {
                continue
            }

            if ($newLine -match '^\s*import\s+from') {
                continue
            }

            if ($newLine.Trim() -ne '') {
                $out.Add($newLine)
            }

            continue
        }

        $out.Add($line)
    }

    return ($out -join "`r`n")
}

function Find-JsxRootClose {
    param(
        [string]$Text,
        [int]$StartIndex,
        [int]$EndIndex
    )

    $i = $StartIndex

    while (
        $i -lt $EndIndex -and
        [char]::IsWhiteSpace($Text[$i])
    ) {
        $i++
    }

    if ($i -ge $EndIndex) {
        throw 'Ana JSX return boş.'
    }

    if (
        $i + 1 -lt $Text.Length -and
        $Text[$i] -eq '<' -and
        $Text[$i + 1] -eq '>'
    ) {
        $depth = 1
        $i += 2

        while ($i -lt $EndIndex) {
            if (
                $i + 2 -lt $Text.Length -and
                $Text[$i] -eq '<' -and
                $Text[$i + 1] -eq '/' -and
                $Text[$i + 2] -eq '>'
            ) {
                $depth--

                if ($depth -eq 0) {
                    return $i
                }

                $i += 3
                continue
            }

            if (
                $i + 1 -lt $Text.Length -and
                $Text[$i] -eq '<' -and
                $Text[$i + 1] -eq '>'
            ) {
                $depth++
                $i += 2
                continue
            }

            $i++
        }

        throw 'Fragment root kapanışı bulunamadı.'
    }

    if ($Text[$i] -ne '<') {
        throw ("JSX root '<' ile başlamıyor. Index={0}" -f $i)
    }

    $nameStart = $i + 1
    $j = $nameStart

    while (
        $j -lt $EndIndex -and
        (
            [char]::IsLetterOrDigit($Text[$j]) -or
            $Text[$j] -eq '_' -or
            $Text[$j] -eq '-' -or
            $Text[$j] -eq '.' -or
            $Text[$j] -eq ':'
        )
    ) {
        $j++
    }

    if ($j -eq $nameStart) {
        throw ("JSX root tag adı okunamadı. Index={0}" -f $i)
    }

    $rootName = $Text.Substring(
        $nameStart,
        $j - $nameStart
    )

    $k = $j
    $quote = [char]0
    $escape = $false

    while ($k -lt $EndIndex) {
        $c = $Text[$k]

        if ($quote -ne [char]0) {
            if ($escape) {
                $escape = $false
            }
            elseif ($c -eq '\') {
                $escape = $true
            }
            elseif ($c -eq $quote) {
                $quote = [char]0
            }

            $k++
            continue
        }

        if ($c -eq '"' -or $c -eq "'") {
            $quote = $c
            $k++
            continue
        }

        if (
            $c -eq '/' -and
            ($k + 1) -lt $Text.Length -and
            $Text[$k + 1] -eq '>'
        ) {
            return $i
        }

        if ($c -eq '>') {
            break
        }

        $k++
    }

    if ($k -ge $EndIndex) {
        throw ("JSX root açılışı tamamlanamadı: <{0}>" -f $rootName)
    }

    $depth = 1
    $p = $k + 1

    while ($p -lt $EndIndex) {
        if ($Text[$p] -ne '<') {
            $p++
            continue
        }

        if (
            $p + 1 -lt $Text.Length -and
            $Text[$p + 1] -eq '/'
        ) {
            $closeNameStart = $p + 2
            $q = $closeNameStart

            while (
                $q -lt $EndIndex -and
                (
                    [char]::IsLetterOrDigit($Text[$q]) -or
                    $Text[$q] -eq '_' -or
                    $Text[$q] -eq '-' -or
                    $Text[$q] -eq '.' -or
                    $Text[$q] -eq ':'
                )
            ) {
                $q++
            }

            $closeName = $Text.Substring(
                $closeNameStart,
                $q - $closeNameStart
            )

            if ($closeName -eq $rootName) {
                $depth--

                if ($depth -eq 0) {
                    return $p
                }
            }

            $p++
            continue
        }

        if (
            $p + 1 -lt $Text.Length -and
            $Text[$p + 1] -eq '>'
        ) {
            $depth++
            $p += 2
            continue
        }

        $tagStart = $p + 1

        if ($tagStart -ge $EndIndex) {
            break
        }

        if (
            $Text[$tagStart] -eq '!' -or
            $Text[$tagStart] -eq '?'
        ) {
            $p++
            continue
        }

        $q = $tagStart

        while (
            $q -lt $EndIndex -and
            (
                [char]::IsLetterOrDigit($Text[$q]) -or
                $Text[$q] -eq '_' -or
                $Text[$q] -eq '-' -or
                $Text[$q] -eq '.' -or
                $Text[$q] -eq ':'
            )
        ) {
            $q++
        }

        if ($q -eq $tagStart) {
            $p++
            continue
        }

        $tagEnd = $q
        $quote = [char]0
        $escape = $false

        while ($tagEnd -lt $EndIndex) {
            $c = $Text[$tagEnd]

            if ($quote -ne [char]0) {
                if ($escape) {
                    $escape = $false
                }
                elseif ($c -eq '\') {
                    $escape = $true
                }
                elseif ($c -eq $quote) {
                    $quote = [char]0
                }

                $tagEnd++
                continue
            }

            if ($c -eq '"' -or $c -eq "'") {
                $quote = $c
                $tagEnd++
                continue
            }

            if ($c -eq '>') {
                break
            }

            $tagEnd++
        }

        if ($tagEnd -ge $EndIndex) {
            break
        }

        $back = $tagEnd - 1

        while (
            $back -gt $q -and
            [char]::IsWhiteSpace($Text[$back])
        ) {
            $back--
        }

        if ($Text[$back] -ne '/') {
            $depth++
        }

        $p = $tagEnd + 1
    }

    throw ("JSX root kapanışı bulunamadı: <{0}>" -f $rootName)
}

Write-Host '============================================================'
Write-Host ' AURA V6.5.9 JARVIS / DETERMINISTIC JSX PATCH'
Write-Host '============================================================'
Write-Host ''

Write-Step '[1/13] Proje kontrol ediliyor...'

if (-not (Test-Path -LiteralPath $Root)) {
    Fail ("Root bulunamadı: {0}" -f $Root)
}

if (-not (Test-Path -LiteralPath $Ui)) {
    Fail ("UI bulunamadı: {0}" -f $Ui)
}

if (-not (Test-Path -LiteralPath $App)) {
    Fail ("App.tsx bulunamadı: {0}" -f $App)
}

Write-Step '[2/13] Güvenli backup oluşturuluyor...'

New-Item `
    -ItemType Directory `
    -Force `
    -Path $BackupDir | Out-Null

Copy-Item `
    -LiteralPath $App `
    -Destination (Join-Path $BackupDir 'App.tsx') `
    -Force

if (Test-Path -LiteralPath $Bridge) {
    Copy-Item `
        -LiteralPath $Bridge `
        -Destination (Join-Path $BackupDir 'AuraJarvisBridge.tsx') `
        -Force
}

Write-Host (
    '    Backup: {0}' -f $BackupDir
) -ForegroundColor DarkGray

try {

    Write-Step '[3/13] App.tsx okunuyor...'

    $text = Read-Utf8 -Path $App

    Write-Step '[4/13] Eski V6.x generated bloklar temizleniyor...'

    $text = [regex]::Replace(
        $text,
        '(?ms)^[ \t]*<AuraConversationalResearch\b[^>]*/>[ \t]*\r?\n?',
        ''
    )

    $text = [regex]::Replace(
        $text,
        '(?m)^[ \t]*import[^\r\n;]*AuraConversationalResearch[^\r\n;]*;?[ \t]*\r?\n?',
        ''
    )

    $text = [regex]::Replace(
        $text,
        '(?m)^[ \t]*.*\bAuraConversationalResearch\b.*\r?\n?',
        {
            param($m)

            $line = $m.Value

            if (
                $line -match '^\s*import\b' -or
                $line -match '<AuraConversationalResearch\b'
            ) {
                return ''
            }

            return $line
        }
    )

    Write-Step '[5/13] React importleri temizleniyor...'

    $text = Remove-ImportIdentifier `
        -Text $text `
        -Identifier 'useRef'

    Write-Step '[6/13] App scope ve state temizliği hazırlanıyor...'

    $appScope = Find-AppScope -Text $text

    Write-Host (
        '    App Start : {0}' -f $appScope.Start
    )

    Write-Host (
        '    App Open  : {0}' -f $appScope.Open
    )

    Write-Host (
        '    App Close : {0}' -f $appScope.Close
    )

    $jsx = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $appScope.Open `
        -AppClose $appScope.Close

    Write-Host (
        '    JSX return : {0}' -f $jsx.ReturnStart
    )

    Write-Host (
        '    JSX open   : {0}' -f $jsx.OpenParen
    )

    Write-Host (
        '    JSX close  : {0}' -f $jsx.CloseParen
    )

    $text = [regex]::Replace(
        $text,
        'const\s+\[researchOutput\s*,\s*setResearchOutput\s*\]\s*=\s*useState<unknown>\(null\);',
        'const [researchOutput] = useState<unknown>(null);'
    )

    $text = [regex]::Replace(
        $text,
        'const\s+\[researchOutput\s*,\s*setResearchOutput\s*\]\s*=\s*useState\([^;]*\);',
        {
            param($m)

            if ($m.Value -match 'useState<unknown>\(null\)') {
                return 'const [researchOutput] = useState<unknown>(null);'
            }

            return ($m.Value -replace 'setResearchOutput\s*,?', '')
        }
    )

    $text = $text -replace '\bsetResearchOutput\b', ''

    Write-Host '    Research state : researchOutput'
    Write-Host '    setResearchOutput : REMOVED'

    Write-Step '[7/13] AuraJarvisBridge modülü hazırlanıyor...'

    $bridgeContent = @'
import { useRef } from "react";

type AuraJarvisBridgeProps = {
  command?: string;
  researchOutput?: unknown;
};

type AssistantResponse = {
  assistant_reply?: string;
  reply?: string;
  response?: string;
  message?: string;
};

export default function AuraJarvisBridge({
  command,
  researchOutput,
}: AuraJarvisBridgeProps) {
  const busyRef = useRef(false);

  const speak = (text: string) => {
    if (!text || typeof window === "undefined") {
      return;
    }

    if (!("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "tr-TR";
    utterance.rate = 1;
    utterance.pitch = 1;

    window.speechSynthesis.speak(utterance);
  };

  const sendCommand = async () => {
    if (!command || busyRef.current) {
      return;
    }

    busyRef.current = true;

    try {
      const response = await fetch("/api/assistant/respond", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: command,
          research_output: researchOutput ?? null,
        }),
      });

      if (!response.ok) {
        throw new Error(
          `Assistant API HTTP ${response.status}`
        );
      }

      const data = (await response.json()) as AssistantResponse;

      const reply =
        data.assistant_reply ??
        data.reply ??
        data.response ??
        data.message ??
        "";

      if (reply.trim()) {
        speak(reply.trim());
      }
    } catch (error) {
      console.error("AURA JARVIS bridge error:", error);
    } finally {
      busyRef.current = false;
    }
  };

  return (
    <button
      type="button"
      onClick={sendCommand}
      disabled={!command || busyRef.current}
      style={{
        display: "none",
      }}
      aria-hidden="true"
    >
      AURA JARVIS
    </button>
  );
}
'@

    Write-Utf8 `
        -Path $Bridge `
        -Content $bridgeContent

    Write-Step '[8/13] AuraJarvisBridge importu ve JSX placement...'

    $text = Read-Utf8 -Path $App

    $text = [regex]::Replace(
        $text,
        '(?m)^[ \t]*import[^\r\n;]*AuraJarvisBridge[^\r\n;]*;?[ \t]*\r?\n?',
        ''
    )

    $bridgeImport = 'import AuraJarvisBridge from "./AuraJarvisBridge";'

    $importMatches = [regex]::Matches(
        $text,
        '(?m)^[ \t]*import\b[^\r\n]*\r?$'
    )

    if ($importMatches.Count -gt 0) {

        $lastImport = $importMatches[$importMatches.Count - 1]

        $insertAt = $lastImport.Index + $lastImport.Length

        $text =
            $text.Substring(0, $insertAt) +
            "`r`n" +
            $bridgeImport +
            $text.Substring($insertAt)
    }
    else {

        $text =
            $bridgeImport +
            "`r`n" +
            $text
    }

    $appScope2 = Find-AppScope -Text $text

    $jsx2 = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $appScope2.Open `
        -AppClose $appScope2.Close

    $bridgeJsx = @'
      <AuraJarvisBridge
        command={command}
        researchOutput={researchOutput}
      />
'@

    $text = [regex]::Replace(
        $text,
        '(?ms)[ \t]*<AuraJarvisBridge\b.*?/>[ \t]*\r?\n?',
        ''
    )

    $appScope3 = Find-AppScope -Text $text

    $jsx3 = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $appScope3.Open `
        -AppClose $appScope3.Close

    $rootClose3 = Find-JsxRootClose `
        -Text $text `
        -StartIndex ($jsx3.OpenParen + 1) `
        -EndIndex $jsx3.CloseParen

    if (
        $rootClose3 -lt $jsx3.OpenParen -or
        $rootClose3 -gt $jsx3.CloseParen
    ) {
        throw 'JSX root kapanış indexi ana return sınırları dışında.'
    }

    $text =
        $text.Substring(0, $rootClose3) +
        "`r`n" +
        $bridgeJsx +
        "`r`n    " +
        $text.Substring($rootClose3)

    Write-Host '    Bridge JSX root içine yerleştirildi.'
    Write-Host (
        '    Root close index: {0}' -f $rootClose3
    )

    Write-Step '[9/13] Eski component referansları final cleanup...'

    $text = [regex]::Replace(
        $text,
        '(?m)^[ \t]*import[^\r\n]*AuraConversationalResearch[^\r\n]*\r?\n?',
        ''
    )

    $text = [regex]::Replace(
        $text,
        '(?m)^[ \t]*<AuraConversationalResearch\b[^>]*/>[ \t]*\r?\n?',
        ''
    )

    if ($text -match '\bAuraConversationalResearch\b') {
        throw 'AuraConversationalResearch referansı hala App.tsx içinde mevcut.'
    }

    Write-Step '[10/13] Structural validation...'

    $finalApp = Find-AppScope -Text $text

    $finalJsx = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $finalApp.Open `
        -AppClose $finalApp.Close

    $bridgeMatches = [regex]::Matches(
        $text,
        '<AuraJarvisBridge\b'
    )

    if ($bridgeMatches.Count -ne 1) {
        throw (
            'AuraJarvisBridge JSX sayısı beklenen 1 değil: {0}' -f `
            $bridgeMatches.Count
        )
    }

    $bridgeIndex = $bridgeMatches[0].Index

    if (
        $bridgeIndex -lt $finalJsx.OpenParen -or
        $bridgeIndex -gt $finalJsx.CloseParen
    ) {
        throw 'AuraJarvisBridge ana JSX return dışında.'
    }

    if (
        $text -notmatch `
        '(?m)^\s*import\s+AuraJarvisBridge\s+from\s+["'']\.\/AuraJarvisBridge["''];?\s*$'
    ) {
        throw 'AuraJarvisBridge importu bulunamadı.'
    }

    if ($text -match '\bsetResearchOutput\b') {
        throw 'setResearchOutput referansı hala mevcut.'
    }

    if ($text -match '\buseRef\b') {
        throw 'App.tsx içinde useRef referansı hala mevcut.'
    }

    $null = Find-MatchingParen `
        -Text $text `
        -OpenIndex $finalJsx.OpenParen

    Write-Host '    App scope        : PASS' -ForegroundColor Green
    Write-Host '    JSX return       : PASS' -ForegroundColor Green
    Write-Host '    Bridge placement : PASS' -ForegroundColor Green
    Write-Host '    Old component    : PASS' -ForegroundColor Green
    Write-Host '    Setter cleanup   : PASS' -ForegroundColor Green

    Write-Step '[11/13] App.tsx yazılıyor...'

    Write-Utf8 `
        -Path $App `
        -Content $text

    Write-Step '[12/13] Python compile + frontend build...'

    $CoreSrc = Join-Path $Root 'core\src'

    if (-not (Test-Path -LiteralPath $CoreSrc)) {
        throw ("Core src bulunamadı: {0}" -f $CoreSrc)
    }

    $pyFiles = Get-ChildItem `
        -LiteralPath $CoreSrc `
        -Recurse `
        -Filter '*.py' `
        -File

    if ($pyFiles.Count -gt 0) {

        Write-Host (
            '    Python dosyaları: {0}' -f $pyFiles.Count
        )

        $pythonExe = Get-Command python -ErrorAction SilentlyContinue

        if ($null -eq $pythonExe) {
            throw 'python komutu bulunamadı.'
        }

        & python -m compileall -q $CoreSrc

        if ($LASTEXITCODE -ne 0) {
            throw (
                'Python compileall başarısız. ExitCode={0}' -f `
                $LASTEXITCODE
            )
        }

        Write-Host `
            '    Python compileall: PASS' `
            -ForegroundColor Green
    }

    Push-Location $Ui

    try {

        if (
            -not (
                Test-Path `
                    -LiteralPath (Join-Path $Ui 'package.json')
            )
        ) {
            throw ("package.json bulunamadı: {0}" -f $Ui)
        }

        npm run build

        if ($LASTEXITCODE -ne 0) {
            throw (
                'npm run build başarısız. ExitCode={0}' -f `
                $LASTEXITCODE
            )
        }
    }
    finally {
        Pop-Location
    }

    Write-Step '[13/13] Final doğrulama...'

    $verify = Read-Utf8 -Path $App

    if ($verify -notmatch 'AuraJarvisBridge') {
        throw 'Final App.tsx içinde AuraJarvisBridge bulunamadı.'
    }

    if ($verify -match 'AuraConversationalResearch') {
        throw 'Final App.tsx içinde eski AuraConversationalResearch bulundu.'
    }

    if ($verify -match '\bsetResearchOutput\b') {
        throw 'Final App.tsx içinde setResearchOutput bulundu.'
    }

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ' AURA V6.5.9 PATCH SUCCESS' -ForegroundColor Green
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ''
    Write-Host (
        'App.tsx       : {0}' -f $App
    )
    Write-Host (
        'Bridge        : {0}' -f $Bridge
    )
    Write-Host (
        'Backup        : {0}' -f $BackupDir
    )
    Write-Host ''
    Write-Host `
        'Structural validation : PASS' `
        -ForegroundColor Green
    Write-Host `
        'Python compile        : PASS' `
        -ForegroundColor Green
    Write-Host `
        'npm run build         : PASS' `
        -ForegroundColor Green
    Write-Host ''

}
catch {

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.9 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red

    Write-Host `
        $_.Exception.Message `
        -ForegroundColor Red

    Write-Host ''
    Write-Host `
        'Backup üzerinden rollback uygulanıyor...' `
        -ForegroundColor Yellow

    $AppBackup = Join-Path $BackupDir 'App.tsx'
    $BridgeBackup = Join-Path $BackupDir 'AuraJarvisBridge.tsx'

    if (Test-Path -LiteralPath $AppBackup) {

        Copy-Item `
            -LiteralPath $AppBackup `
            -Destination $App `
            -Force

        Write-Host `
            'App.tsx rollback: PASS' `
            -ForegroundColor Green
    }

    if (Test-Path -LiteralPath $BridgeBackup) {

        Copy-Item `
            -LiteralPath $BridgeBackup `
            -Destination $Bridge `
            -Force

        Write-Host `
            'AuraJarvisBridge.tsx rollback: PASS' `
            -ForegroundColor Green
    }
    elseif (Test-Path -LiteralPath $Bridge) {

        Remove-Item `
            -LiteralPath $Bridge `
            -Force

        Write-Host `
            'Yeni Bridge rollback: REMOVED' `
            -ForegroundColor Green
    }

    Write-Host ''
    Write-Host (
        'Backup: {0}' -f $BackupDir
    ) -ForegroundColor DarkGray

    exit 1
}