# ============================================================
# AURA V6.5.10
# JARVIS / SAFE JSX ROOT PLACEMENT PATCH
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
$BackupDir = Join-Path $BackupRoot "v6510_$Stamp"

function Write-Step {
    param([string]$Message)
    Write-Host $Message -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' AURA V6.5.10 PATCH ABORTED' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $Message -ForegroundColor Red
    throw $Message
}

function Read-Utf8 {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail ("Dosya bulunamadı: {0}" -f $Path)
    }

    [System.IO.File]::ReadAllText(
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

function Find-MatchingDelimiter {
    param(
        [string]$Text,
        [int]$OpenIndex,
        [char]$OpenChar,
        [char]$CloseChar
    )

    if ($OpenIndex -lt 0 -or $OpenIndex -ge $Text.Length) {
        throw ("Geçersiz delimiter indexi: {0}" -f $OpenIndex)
    }

    if ($Text[$OpenIndex] -ne $OpenChar) {
        throw ("Beklenen açılış karakteri bulunamadı: {0}" -f $OpenChar)
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

        if ($c -eq $OpenChar) {
            $depth++
            continue
        }

        if ($c -eq $CloseChar) {
            $depth--

            if ($depth -eq 0) {
                return $i
            }
        }
    }

    throw (
        "Eşleşen kapanış karakteri bulunamadı. Açılış indexi: {0}" -f `
        $OpenIndex
    )
}

function Find-AppScope {
    param([string]$Text)

    $match = [regex]::Match(
        $Text,
        '(?m)(?:export\s+default\s+)?function\s+App\s*\('
    )

    if (-not $match.Success) {
        $match = [regex]::Match(
            $Text,
            '(?m)(?:export\s+default\s+)?const\s+App\s*='
        )
    }

    if (-not $match.Success) {
        throw 'App component bulunamadı.'
    }

    $open = $Text.IndexOf(
        '{',
        $match.Index + $match.Length
    )

    if ($open -lt 0) {
        throw 'App açılış { karakteri bulunamadı.'
    }

    $close = Find-MatchingDelimiter `
        -Text $Text `
        -OpenIndex $open `
        -OpenChar '{' `
        -CloseChar '}'

    @{
        Start = $match.Index
        Open = $open
        Close = $close
    }
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
        throw 'App içinde return ( bulunamadı.'
    }

    $candidate = $null

    foreach ($m in $matches) {
        $global = $AppOpen + $m.Index

        $open = $Text.IndexOf(
            '(',
            $global + $m.Length - 1
        )

        if ($open -lt 0) {
            continue
        }

        try {
            $close = Find-MatchingDelimiter `
                -Text $Text `
                -OpenIndex $open `
                -OpenChar '(' `
                -CloseChar ')'

            if (
                $close -le $AppClose -and
                $close -gt $open
            ) {
                $candidate = @{
                    ReturnStart = $global
                    OpenParen = $open
                    CloseParen = $close
                }
            }
        }
        catch {
            continue
        }
    }

    if ($null -eq $candidate) {
        throw 'App içindeki ana JSX return bulunamadı.'
    }

    $candidate
}

function Remove-Bridge {
    param([string]$Text)

    [regex]::Replace(
        $Text,
        '(?ms)[ \t]*<AuraJarvisBridge\b.*?/>[ \t]*\r?\n?',
        ''
    )
}

function Remove-OldResearchComponent {
    param([string]$Text)

    $Text = [regex]::Replace(
        $Text,
        '(?m)^[ \t]*import[^\r\n]*AuraConversationalResearch[^\r\n]*\r?\n?',
        ''
    )

    $Text = [regex]::Replace(
        $Text,
        '(?ms)[ \t]*<AuraConversationalResearch\b[^>]*/>[ \t]*\r?\n?',
        ''
    )

    $Text
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

            $newLine = [regex]::Replace(
                $line,
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

    $out -join "`r`n"
}

function Find-JsxRootClose {
    param(
        [string]$Text,
        [int]$StartIndex,
        [int]$EndIndex
    )

    # ------------------------------------------------------------
    # V6.5.10:
    #
    # Önceki sürümün "return sonrası boş" varsayımı kaldırıldı.
    # Burada return(...) gövdesinin ilk gerçek karakterini buluyoruz.
    #
    # JSX root:
    #   <>
    # veya
    #   <main>
    # veya
    #   <div>
    #
    # ayrıca root'un içindeki React expression / string / comment
    # içerikleri scanner tarafından atlanıyor.
    # ------------------------------------------------------------

    $i = $StartIndex

    while (
        $i -lt $EndIndex -and
        [char]::IsWhiteSpace($Text[$i])
    ) {
        $i++
    }

    if ($i -ge $EndIndex) {
        throw 'Ana JSX return gövdesinde root başlangıcı bulunamadı.'
    }

    if (
        $Text[$i] -eq '<' -and
        $i + 1 -lt $EndIndex -and
        $Text[$i + 1] -eq '>'
    ) {

        $fragmentDepth = 1
        $i += 2

        while ($i -lt $EndIndex) {

            if (
                $Text[$i] -eq '<' -and
                $i + 2 -lt $EndIndex -and
                $Text[$i + 1] -eq '/' -and
                $Text[$i + 2] -eq '>'
            ) {
                $fragmentDepth--

                if ($fragmentDepth -eq 0) {
                    return $i
                }

                $i += 3
                continue
            }

            if (
                $Text[$i] -eq '<' -and
                $i + 1 -lt $EndIndex -and
                $Text[$i + 1] -eq '>'
            ) {
                $fragmentDepth++
                $i += 2
                continue
            }

            $i++
        }

        throw 'React Fragment root kapanışı bulunamadı.'
    }

    if ($Text[$i] -ne '<') {
        throw (
            "Ana JSX root '<' ile başlamıyor. Index={0}" -f $i
        )
    }

    $nameStart = $i + 1
    $nameEnd = $nameStart

    while (
        $nameEnd -lt $EndIndex -and
        (
            [char]::IsLetterOrDigit($Text[$nameEnd]) -or
            $Text[$nameEnd] -eq '_' -or
            $Text[$nameEnd] -eq '-' -or
            $Text[$nameEnd] -eq '.' -or
            $Text[$nameEnd] -eq ':'
        )
    ) {
        $nameEnd++
    }

    if ($nameEnd -eq $nameStart) {
        throw 'JSX root tag adı bulunamadı.'
    }

    $rootName = $Text.Substring(
        $nameStart,
        $nameEnd - $nameStart
    )

    $tagEnd = $nameEnd
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
        throw (
            "JSX root açılışı tamamlanamadı: <{0}>" -f $rootName
        )
    }

    $back = $tagEnd - 1

    while (
        $back -gt $nameEnd -and
        [char]::IsWhiteSpace($Text[$back])
    ) {
        $back--
    }

    if ($Text[$back] -eq '/') {
        return $i
    }

    $depth = 1
    $p = $tagEnd + 1

    $braceDepth = 0
    $stringQuote = [char]0
    $template = $false
    $escape = $false
    $lineComment = $false
    $blockComment = $false

    while ($p -lt $EndIndex) {

        $c = $Text[$p]
        $next = if ($p + 1 -lt $EndIndex) {
            $Text[$p + 1]
        }
        else {
            [char]0
        }

        if ($lineComment) {
            if ($c -eq "`n") {
                $lineComment = $false
            }

            $p++
            continue
        }

        if ($blockComment) {
            if ($c -eq '*' -and $next -eq '/') {
                $blockComment = $false
                $p += 2
                continue
            }

            $p++
            continue
        }

        if ($stringQuote -ne [char]0) {

            if ($escape) {
                $escape = $false
                $p++
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                $p++
                continue
            }

            if ($c -eq $stringQuote) {
                $stringQuote = [char]0
            }

            $p++
            continue
        }

        if ($template) {

            if ($escape) {
                $escape = $false
                $p++
                continue
            }

            if ($c -eq '\') {
                $escape = $true
                $p++
                continue
            }

            if ($c -eq '`') {
                $template = $false
            }

            $p++
            continue
        }

        if ($c -eq '/' -and $next -eq '/') {
            $lineComment = $true
            $p += 2
            continue
        }

        if ($c -eq '/' -and $next -eq '*') {
            $blockComment = $true
            $p += 2
            continue
        }

        if ($c -eq '"' -or $c -eq "'") {
            $stringQuote = $c
            $p++
            continue
        }

        if ($c -eq '`') {
            $template = $true
            $p++
            continue
        }

        if ($c -eq '{') {
            $braceDepth++
            $p++
            continue
        }

        if ($c -eq '}' -and $braceDepth -gt 0) {
            $braceDepth--
            $p++
            continue
        }

        if ($braceDepth -gt 0) {
            $p++
            continue
        }

        if ($c -ne '<') {
            $p++
            continue
        }

        if (
            $next -eq '/' -and
            $p + 2 -lt $EndIndex
        ) {

            $closeStart = $p + 2
            $closeEnd = $closeStart

            while (
                $closeEnd -lt $EndIndex -and
                (
                    [char]::IsLetterOrDigit($Text[$closeEnd]) -or
                    $Text[$closeEnd] -eq '_' -or
                    $Text[$closeEnd] -eq '-' -or
                    $Text[$closeEnd] -eq '.' -or
                    $Text[$closeEnd] -eq ':'
                )
            ) {
                $closeEnd++
            }

            $closeName = $Text.Substring(
                $closeStart,
                $closeEnd - $closeStart
            )

            if ($closeName -eq $rootName) {

                $closeTagEnd = $closeEnd

                while (
                    $closeTagEnd -lt $EndIndex -and
                    $Text[$closeTagEnd] -ne '>'
                ) {
                    $closeTagEnd++
                }

                if ($closeTagEnd -ge $EndIndex) {
                    throw (
                        "JSX kapanış tag'i tamamlanamadı: </{0}>" -f `
                        $rootName
                    )
                }

                $depth--

                if ($depth -eq 0) {
                    return $p
                }

                $p = $closeTagEnd + 1
                continue
            }

            $p++
            continue
        }

        if ($next -eq '>') {
            $depth++
            $p += 2
            continue
        }

        $tagNameStart = $p + 1
        $tagNameEnd = $tagNameStart

        while (
            $tagNameEnd -lt $EndIndex -and
            (
                [char]::IsLetterOrDigit($Text[$tagNameEnd]) -or
                $Text[$tagNameEnd] -eq '_' -or
                $Text[$tagNameEnd] -eq '-' -or
                $Text[$tagNameEnd] -eq '.' -or
                $Text[$tagNameEnd] -eq ':'
            )
        ) {
            $tagNameEnd++
        }

        if ($tagNameEnd -eq $tagNameStart) {
            $p++
            continue
        }

        $innerTagEnd = $tagNameEnd
        $innerQuote = [char]0
        $innerEscape = $false

        while ($innerTagEnd -lt $EndIndex) {

            $tc = $Text[$innerTagEnd]

            if ($innerQuote -ne [char]0) {

                if ($innerEscape) {
                    $innerEscape = $false
                }
                elseif ($tc -eq '\') {
                    $innerEscape = $true
                }
                elseif ($tc -eq $innerQuote) {
                    $innerQuote = [char]0
                }

                $innerTagEnd++
                continue
            }

            if ($tc -eq '"' -or $tc -eq "'") {
                $innerQuote = $tc
                $innerTagEnd++
                continue
            }

            if ($tc -eq '>') {
                break
            }

            $innerTagEnd++
        }

        if ($innerTagEnd -ge $EndIndex) {
            throw 'İç JSX tag kapanışı bulunamadı.'
        }

        $innerBack = $innerTagEnd - 1

        while (
            $innerBack -gt $tagNameEnd -and
            [char]::IsWhiteSpace($Text[$innerBack])
        ) {
            $innerBack--
        }

        if ($Text[$innerBack] -ne '/') {
            $depth++
        }

        $p = $innerTagEnd + 1
    }

    throw (
        "JSX root kapanışı bulunamadı: <{0}>" -f $rootName
    )
}

Write-Host '============================================================'
Write-Host ' AURA V6.5.10 JARVIS / SAFE JSX ROOT PATCH'
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

    $text = Remove-OldResearchComponent -Text $text
    $text = Remove-Bridge -Text $text

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

    if ($jsx.CloseParen -le $jsx.OpenParen) {
        throw 'JSX return parantez sınırları geçersiz.'
    }

    $returnBodyLength =
        $jsx.CloseParen - $jsx.OpenParen - 1

    Write-Host (
        '    JSX body length : {0}' -f $returnBodyLength
    )

    if ($returnBodyLength -le 0) {
        throw 'JSX return gerçekten boş görünüyor.'
    }

    $text = [regex]::Replace(
        $text,
        'const\s+\[researchOutput\s*,\s*setResearchOutput\s*\]\s*=\s*useState<unknown>\(null\);',
        'const [researchOutput] = useState<unknown>(null);'
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
        '(?m)^[ \t]*import[^\r\n]*AuraJarvisBridge[^\r\n]*;?[ \t]*\r?\n?',
        ''
    )

    $bridgeImport =
        'import AuraJarvisBridge from "./AuraJarvisBridge";'

    $imports = [regex]::Matches(
        $text,
        '(?m)^[ \t]*import\b[^\r\n]*\r?$'
    )

    if ($imports.Count -gt 0) {

        $lastImport = $imports[$imports.Count - 1]

        $insertAt =
            $lastImport.Index +
            $lastImport.Length

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

    # ------------------------------------------------------------
    # IMPORT EKLENDİKTEN SONRA TÜM INDEXLER YENİDEN HESAPLANIYOR.
    # ------------------------------------------------------------

    $appScope2 = Find-AppScope -Text $text

    $jsx2 = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $appScope2.Open `
        -AppClose $appScope2.Close

    if ($jsx2.CloseParen -le $jsx2.OpenParen) {
        throw 'Import sonrası JSX return sınırları geçersiz.'
    }

    $bodyLength =
        $jsx2.CloseParen -
        $jsx2.OpenParen -
        1

    Write-Host (
        '    JSX body length : {0}' -f $bodyLength
    )

    if ($bodyLength -le 0) {
        throw 'Import sonrası ana JSX return gövdesi boş görünüyor.'
    }

    # ------------------------------------------------------------
    # ROOT KAPANIŞINI BUL.
    # ------------------------------------------------------------

    $rootClose = Find-JsxRootClose `
        -Text $text `
        -StartIndex ($jsx2.OpenParen + 1) `
        -EndIndex $jsx2.CloseParen

    if (
        $rootClose -le $jsx2.OpenParen -or
        $rootClose -ge $jsx2.CloseParen
    ) {
        throw 'JSX root kapanış konumu ana return sınırları dışında.'
    }

    Write-Host (
        '    JSX root close : {0}' -f $rootClose
    )

    $bridgeJsx = @'
      <AuraJarvisBridge
        command={command}
        researchOutput={researchOutput}
      />
'@

    $text =
        $text.Substring(0, $rootClose) +
        "`r`n" +
        $bridgeJsx +
        "`r`n    " +
        $text.Substring($rootClose)

    Write-Host '    Bridge JSX root içine yerleştirildi.'

    Write-Step '[9/13] Eski component referansları final cleanup...'

    $text = Remove-OldResearchComponent -Text $text

    if ($text -match '\bAuraConversationalResearch\b') {
        throw 'AuraConversationalResearch referansı hala mevcut.'
    }

    if (
        ([regex]::Matches(
            $text,
            '<AuraJarvisBridge\b'
        )).Count -ne 1
    ) {
        throw 'AuraJarvisBridge JSX sayısı tam olarak 1 değil.'
    }

    Write-Step '[10/13] Structural validation...'

    $finalApp = Find-AppScope -Text $text

    $finalJsx = Find-MainJsxReturn `
        -Text $text `
        -AppOpen $finalApp.Open `
        -AppClose $finalApp.Close

    if ($finalJsx.CloseParen -le $finalJsx.OpenParen) {
        throw 'Final JSX return sınırları geçersiz.'
    }

    $finalBridgeMatches = [regex]::Matches(
        $text,
        '<AuraJarvisBridge\b'
    )

    $bridgeIndex = $finalBridgeMatches[0].Index

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

    $null = Find-MatchingDelimiter `
        -Text $text `
        -OpenIndex $finalJsx.OpenParen `
        -OpenChar '(' `
        -CloseChar ')'

    Write-Host '    App scope        : PASS' -ForegroundColor Green
    Write-Host '    JSX return       : PASS' -ForegroundColor Green
    Write-Host '    JSX body         : PASS' -ForegroundColor Green
    Write-Host '    JSX root         : PASS' -ForegroundColor Green
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
        throw 'Final App.tsx içinde eski component bulundu.'
    }

    if ($verify -match '\bsetResearchOutput\b') {
        throw 'Final App.tsx içinde setResearchOutput bulundu.'
    }

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Green
    Write-Host ' AURA V6.5.10 PATCH SUCCESS' -ForegroundColor Green
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
    Write-Host ' AURA V6.5.10 PATCH ABORTED' -ForegroundColor Red
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