#Requires -Version 5.1

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

# ============================================================
# AURA RESEARCH OUTPUT - V5 SAFE PATCH
# PowerShell 5.1
#
# FIXES:
#   1. Explicitly targets "export default function App("
#   2. Never confuses makeId / ArcReactor / StatusItem with App
#   3. Inserts module component BEFORE App declaration
#   4. Finds App's own return(...) after App's opening brace
#   5. Uses JS/TS operators inside generated TypeScript
#   6. Uses PowerShell operators only inside this .ps1
#   7. No LastIndexOf("</div>") JSX injection
#   8. No Git HEAD dependency
#   9. Automatic backup + rollback
#  10. npm run build is mandatory for success
# ============================================================

$Root      = "D:\AURA\JAS"
$UiRoot    = Join-Path $Root "aura-ui"
$SrcRoot   = Join-Path $UiRoot "src"
$AppFile   = Join-Path $SrcRoot "App.tsx"
$IndexFile = Join-Path $UiRoot "index.html"

$BackupRoot = Join-Path $UiRoot ".aura-backups"
$Stamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$RunBackup  = Join-Path $BackupRoot ("research-v5-" + $Stamp)

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    throw $Message
}

function Assert-Path {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail ($Label + " bulunamadı: " + $Path)
    }
}

function Assert-Text {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if ($null -eq $Text) {
        Fail ($Label + " NULL.")
    }

    if ($Text.Length -eq 0) {
        Fail ($Label + " boş.")
    }
}

function Read-Utf8Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    Assert-Path -Path $Path -Label "Dosya"

    $text = [System.IO.File]::ReadAllText($Path)

    Assert-Text -Text $text -Label $Path

    return $text
}

function Write-Utf8Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    Assert-Text -Text $Text -Label ("Write target " + $Path)

    $encoding = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllText(
        $Path,
        $Text,
        $encoding
    )
}

function Backup-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    Assert-Path -Path $Source -Label "Backup source"

    $parent = Split-Path -Parent $Destination

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

function Restore-File {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Backup,

        [Parameter(Mandatory = $true)]
        [string]$Destination
    )

    Assert-Path -Path $Backup -Label "Rollback backup"

    Copy-Item `
        -LiteralPath $Backup `
        -Destination $Destination `
        -Force
}

function Insert-Text {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [int]$Index,

        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    Assert-Text -Text $Text -Label "Insert source"

    if ($Index -lt 0) {
        Fail "Insert index negatif."
    }

    if ($Index -gt $Text.Length) {
        Fail "Insert index text uzunluğunu aşıyor."
    }

    if ($null -eq $Value) {
        Fail "Insert value NULL."
    }

    $left = $Text.Substring(0, $Index)
    $right = $Text.Substring($Index)

    $result = $left + $Value + $right

    Assert-Text -Text $result -Label "Insert result"

    return $result
}

# ============================================================
# POWERSHELL PARSER PREFLIGHT
# ============================================================

function Test-SelfParser {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath
    )

    Assert-Path -Path $ScriptPath -Label "Patch script"

    $tokens = $null
    $errors = $null

    [System.Management.Automation.Language.Parser]::ParseFile(
        $ScriptPath,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null

    if ($null -ne $errors -and $errors.Count -gt 0) {

        $messages = $errors | ForEach-Object {
            "Line " +
            $_.Extent.StartLineNumber +
            ", Char " +
            $_.Extent.StartColumnNumber +
            ": " +
            $_.Message
        }

        Fail (
            "PATCH SCRIPT PARSER FAILURE:`r`n" +
            ($messages -join "`r`n")
        )
    }

    return $true
}

# ============================================================
# SAFE BRACE SCANNER
# ============================================================

function Find-MatchingBrace {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [int]$OpenIndex
    )

    Assert-Text -Text $Text -Label "Brace scanner input"

    if ($OpenIndex -lt 0) {
        Fail "Brace OpenIndex negatif."
    }

    if ($OpenIndex -ge $Text.Length) {
        Fail "Brace OpenIndex text sınırını aşıyor."
    }

    if ($Text[$OpenIndex] -ne '{') {
        Fail "Find-MatchingBrace '{' bekliyordu."
    }

    $depth = 0
    $mode = "code"
    $escaped = $false

    for ($i = $OpenIndex; $i -lt $Text.Length; $i++) {

        $c = $Text[$i]

        if ($mode -eq "line-comment") {

            if ($c -eq "`r" -or $c -eq "`n") {
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "block-comment") {

            if (
                $c -eq "*" -and
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq "/"
            ) {
                $i++
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "single") {

            if ($escaped) {
                $escaped = $false
                continue
            }

            if ($c -eq "\") {
                $escaped = $true
                continue
            }

            if ($c -eq "'") {
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "double") {

            if ($escaped) {
                $escaped = $false
                continue
            }

            if ($c -eq "\") {
                $escaped = $true
                continue
            }

            if ($c -eq '"') {
                $mode = "code"
            }

            continue
        }

        if ($c -eq "/" -and ($i + 1) -lt $Text.Length) {

            $next = $Text[$i + 1]

            if ($next -eq "/") {
                $i++
                $mode = "line-comment"
                continue
            }

            if ($next -eq "*") {
                $i++
                $mode = "block-comment"
                continue
            }
        }

        if ($c -eq "'") {
            $mode = "single"
            continue
        }

        if ($c -eq '"') {
            $mode = "double"
            continue
        }

        if ($c -eq '{') {
            $depth++
            continue
        }

        if ($c -eq '}') {

            $depth--

            if ($depth -eq 0) {
                return $i
            }
        }
    }

    Fail "Eşleşen '}' bulunamadı."
}

# ============================================================
# SAFE PAREN SCANNER
# ============================================================

function Find-MatchingParen {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [int]$OpenIndex
    )

    Assert-Text -Text $Text -Label "Paren scanner input"

    if ($OpenIndex -lt 0) {
        Fail "Paren OpenIndex negatif."
    }

    if ($OpenIndex -ge $Text.Length) {
        Fail "Paren OpenIndex text sınırını aşıyor."
    }

    if ($Text[$OpenIndex] -ne '(') {
        Fail "Find-MatchingParen '(' bekliyordu."
    }

    $depth = 0
    $mode = "code"
    $escaped = $false

    for ($i = $OpenIndex; $i -lt $Text.Length; $i++) {

        $c = $Text[$i]

        if ($mode -eq "line-comment") {

            if ($c -eq "`r" -or $c -eq "`n") {
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "block-comment") {

            if (
                $c -eq "*" -and
                ($i + 1) -lt $Text.Length -and
                $Text[$i + 1] -eq "/"
            ) {
                $i++
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "single") {

            if ($escaped) {
                $escaped = $false
                continue
            }

            if ($c -eq "\") {
                $escaped = $true
                continue
            }

            if ($c -eq "'") {
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "double") {

            if ($escaped) {
                $escaped = $false
                continue
            }

            if ($c -eq "\") {
                $escaped = $true
                continue
            }

            if ($c -eq '"') {
                $mode = "code"
            }

            continue
        }

        if ($c -eq "/" -and ($i + 1) -lt $Text.Length) {

            $next = $Text[$i + 1]

            if ($next -eq "/") {
                $i++
                $mode = "line-comment"
                continue
            }

            if ($next -eq "*") {
                $i++
                $mode = "block-comment"
                continue
            }
        }

        if ($c -eq "'") {
            $mode = "single"
            continue
        }

        if ($c -eq '"') {
            $mode = "double"
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

    Fail "Eşleşen ')' bulunamadı."
}

# ============================================================
# EXPLICIT APP DISCOVERY
#
# IMPORTANT:
# We DO NOT search for "any React component".
# We target App specifically.
# ============================================================

function Find-AppDeclaration {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    Assert-Text -Text $Text -Label "App source"

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\(',
        '(?m)^\s*export\s+function\s+App\s*\(',
        '(?m)^\s*function\s+App\s*\(',
        '(?m)^\s*export\s+const\s+App\s*=\s*',
        '(?m)^\s*const\s+App\s*=\s*'
    )

    foreach ($pattern in $patterns) {

        $match = [regex]::Match($Text, $pattern)

        if ($match.Success) {

            return @{
                Index = $match.Index
                Length = $match.Length
                Text = $match.Value
            }
        }
    }

    Fail "export default function App(...) declaration bulunamadı."
}

# ============================================================
# APP OPEN BRACE
#
# Explicitly resolves the brace belonging to App.
# ============================================================

function Find-AppOpenBrace {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $declaration =
        Find-AppDeclaration -Text $Text

    $searchStart =
        $declaration.Index

    $paren =
        $Text.IndexOf(
            "(",
            $searchStart,
            [System.StringComparison]::Ordinal
        )

    if ($paren -lt 0) {

        # Arrow/alternate declaration fallback.
        $brace =
            $Text.IndexOf(
                "{",
                $searchStart,
                [System.StringComparison]::Ordinal
            )

        if ($brace -lt 0) {
            Fail "App açılış brace'i bulunamadı."
        }

        return $brace
    }

    $closeParen =
        Find-MatchingParen `
            -Text $Text `
            -OpenIndex $paren

    $brace =
        $Text.IndexOf(
            "{",
            $closeParen,
            [System.StringComparison]::Ordinal
        )

    if ($brace -lt 0) {
        Fail "App(...) sonrasında '{' bulunamadı."
    }

    return $brace
}

# ============================================================
# APP RETURN RANGE
#
# Starts searching AFTER App's opening brace.
# Therefore makeId / ArcReactor / StatusItem cannot hijack it.
# ============================================================

function Find-AppReturnRange {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [int]$AppOpenBrace
    )

    Assert-Text -Text $Text -Label "App return source"

    $appClose =
        Find-MatchingBrace `
            -Text $Text `
            -OpenIndex $AppOpenBrace

    if ($appClose -le $AppOpenBrace) {
        Fail "App body range geçersiz."
    }

    $bodyLength =
        $appClose -
        $AppOpenBrace

    $body =
        $Text.Substring(
            $AppOpenBrace,
            $bodyLength
        )

    # Only search inside App body.
    $returnMatches =
        [regex]::Matches(
            $body,
            '(?s)\breturn\s*\('
        )

    if ($returnMatches.Count -eq 0) {

        Write-Host ""
        Write-Host "========== APP BODY DIAGNOSTIC =========="
        Write-Host ""

        $previewLength =
            [Math]::Min(
                3500,
                $body.Length
            )

        Write-Host (
            $body.Substring(
                0,
                $previewLength
            )
        )

        Write-Host ""
        Write-Host "=========================================="
        Write-Host ""

        Fail "App() içinde return(...) bulunamadı."
    }

    # Normally App has one return.
    # If multiple returns exist, select the return
    # closest to the end of App body.
    $selected =
        $returnMatches[
            $returnMatches.Count - 1
        ]

    $returnAbsolute =
        $AppOpenBrace +
        $selected.Index

    $openParen =
        $Text.IndexOf(
            "(",
            $returnAbsolute,
            [System.StringComparison]::Ordinal
        )

    if ($openParen -lt 0) {
        Fail "App return '(' bulunamadı."
    }

    $closeParen =
        Find-MatchingParen `
            -Text $Text `
            -OpenIndex $openParen

    if ($closeParen -ge $appClose) {
        Fail "App return ')' App body sınırının dışına çıktı."
    }

    return @{
        AppOpen = $AppOpenBrace
        AppClose = $appClose
        ReturnIndex = $returnAbsolute
        OpenParen = $openParen
        CloseParen = $closeParen
    }
}

# ============================================================
# REACT IMPORTS
# ============================================================

function Ensure-ReactHooks {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $requiredHooks = @(
        "useEffect",
        "useRef",
        "useState"
    )

    $missing =
        New-Object System.Collections.Generic.List[string]

    foreach ($hook in $requiredHooks) {

        if (
            $Text -notmatch (
                "(?m)\b" +
                [regex]::Escape($hook) +
                "\b"
            )
        ) {
            $missing.Add($hook)
        }
    }

    if ($missing.Count -eq 0) {
        return $Text
    }

    $namedImport =
        [regex]::Match(
            $Text,
            "(?m)^import\s*\{(?<imports>[^}]*)\}\s*from\s*['""]react['""]\s*;?"
        )

    if ($namedImport.Success) {

        $imports =
            $namedImport.Groups["imports"].Value.Trim()

        $parts =
            New-Object System.Collections.Generic.List[string]

        if ($imports.Length -gt 0) {

            foreach ($part in $imports.Split(',')) {

                $clean =
                    $part.Trim()

                if (
                    $clean.Length -gt 0 -and
                    -not $parts.Contains($clean)
                ) {
                    $parts.Add($clean)
                }
            }
        }

        foreach ($hook in $missing) {

            if (-not $parts.Contains($hook)) {
                $parts.Add($hook)
            }
        }

        $replacement =
            "import { " +
            ($parts -join ", ") +
            " } from 'react';"

        return (
            $Text.Remove(
                $namedImport.Index,
                $namedImport.Length
            ) |
            ForEach-Object {
                Insert-Text `
                    -Text $_ `
                    -Index $namedImport.Index `
                    -Value $replacement
            }
        )
    }

    $defaultImport =
        [regex]::Match(
            $Text,
            "(?m)^import\s+React\s+from\s*['""]react['""]\s*;?"
        )

    if ($defaultImport.Success) {

        $line =
            "`r`nimport { " +
            ($missing -join ", ") +
            " } from 'react';"

        return (
            Insert-Text `
                -Text $Text `
                -Index (
                    $defaultImport.Index +
                    $defaultImport.Length
                ) `
                -Value $line
        )
    }

    Fail "React import bulunamadı."
}

# ============================================================
# REMOVE PREVIOUS V5/V4 MARKERS
# ============================================================

function Remove-MarkedBlock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$StartMarker,

        [Parameter(Mandatory = $true)]
        [string]$EndMarker
    )

    $start =
        $Text.IndexOf(
            $StartMarker,
            [System.StringComparison]::Ordinal
        )

    if ($start -lt 0) {
        return $Text
    }

    $end =
        $Text.IndexOf(
            $EndMarker,
            $start,
            [System.StringComparison]::Ordinal
        )

    if ($end -lt 0) {
        Fail (
            "Marker bulundu fakat kapanış marker bulunamadı: " +
            $StartMarker
        )
    }

    $end =
        $end +
        $EndMarker.Length

    $result =
        $Text.Remove(
            $start,
            $end - $start
        )

    Assert-Text -Text $result -Label "marker cleanup"

    return $result
}

# ============================================================
# RESEARCH COMPONENT
#
# NOTE:
# Everything between @' and '@ is TypeScript.
# Therefore JS/TS comparison operators are used here.
# ============================================================

$ResearchComponent = @'
/* AURA_RESEARCH_OUTPUT_V5_START */

function AuraResearchOutput(): JSX.Element | null {
  const [researchOutput, setResearchOutput] =
    useState<string>("");

  const spokenRef =
    useRef<string>("");

  const pollGeneration =
    useRef<number>(0);

  const backendBase =
    (): string => {
      const configured =
        (import.meta as any).env?.VITE_API_BASE_URL;

      if (
        typeof configured === "string" &&
        configured.trim().length > 0
      ) {
        return configured.replace(
          /\/+$/,
          "",
        );
      }

      return "http://127.0.0.1:8000";
    };

  const extractResearchOutput =
    (
      value: any,
    ): string => {
      const visited =
        new Set<any>();

      const preferred = [
        "research_output",
        "researchOutput",
        "output",
        "answer",
        "summary",
        "content",
        "text",
        "response",
        "result",
        "research",
        "data",
        "message",
        "steps",
      ];

      const walk =
        (
          node: any,
          depth: number,
        ): string => {
          if (
            node === null ||
            node === undefined ||
            depth > 16
          ) {
            return "";
          }

          if (
            typeof node === "string"
          ) {
            const candidate =
              node.trim();

            if (
              candidate.length >= 24 &&
              !/^(success|succeeded|completed|running|pending|idle)$/i.test(
                candidate,
              )
            ) {
              return candidate;
            }

            return "";
          }

          if (
            typeof node !== "object" ||
            visited.has(node)
          ) {
            return "";
          }

          visited.add(node);

          for (
            const key of preferred
          ) {
            if (
              Object.prototype.hasOwnProperty.call(
                node,
                key,
              )
            ) {
              const found =
                walk(
                  node[key],
                  depth + 1,
                );

              if (found) {
                return found;
              }
            }
          }

          for (
            const key of Object.keys(node)
          ) {
            if (
              preferred.includes(key)
            ) {
              continue;
            }

            const found =
              walk(
                node[key],
                depth + 1,
              );

            if (found) {
              return found;
            }
          }

          return "";
        };

      return walk(
        value,
        0,
      );
    };

  const extractTaskId =
    (
      value: any,
    ): string => {
      const visited =
        new Set<any>();

      const walk =
        (
          node: any,
          depth: number,
        ): string => {
          if (
            node === null ||
            node === undefined ||
            depth > 10
          ) {
            return "";
          }

          if (
            typeof node !== "object" ||
            visited.has(node)
          ) {
            return "";
          }

          visited.add(node);

          const idKeys = [
            "task_id",
            "taskId",
            "id",
          ];

          for (
            const key of idKeys
          ) {
            const candidate =
              node[key];

            if (
              typeof candidate === "string" &&
              candidate.trim().length > 0
            ) {
              return candidate.trim();
            }

            if (
              typeof candidate === "number"
            ) {
              return String(candidate);
            }
          }

          for (
            const key of Object.keys(node)
          ) {
            const found =
              walk(
                node[key],
                depth + 1,
              );

            if (found) {
              return found;
            }
          }

          return "";
        };

      return walk(
        value,
        0,
      );
    };

  const getJson =
    async (
      url: string,
    ): Promise<any | null> => {
      try {
        const response =
          await fetch(
            url,
            {
              method: "GET",
              headers: {
                Accept:
                  "application/json",
              },
            },
          );

        if (!response.ok) {
          return null;
        }

        return await response.json();
      } catch {
        return null;
      }
    };

  const discoverTaskDetailPath =
    async (
      taskId: string,
    ): Promise<string | null> => {
      const backend =
        backendBase();

      const openApiUrls = [
        `${backend}/openapi.json`,
        `${backend}/api/openapi.json`,
      ];

      let schema: any | null =
        null;

      for (
        const url of openApiUrls
      ) {
        const candidate =
          await getJson(url);

        if (
          candidate &&
          candidate.paths
        ) {
          schema =
            candidate;
          break;
        }
      }

      if (!schema) {
        console.warn(
          "[AURA] OpenAPI discovery failed",
        );

        return null;
      }

      let apiBase =
        backend;

      if (
        Array.isArray(
          schema.servers,
        ) &&
        schema.servers.length > 0 &&
        typeof schema.servers[0]?.url ===
          "string"
      ) {
        const serverUrl =
          schema.servers[0].url;

        if (
          /^https?:\/\//i.test(
            serverUrl,
          )
        ) {
          apiBase =
            serverUrl.replace(
              /\/+$/,
              "",
            );
        }
      }

      const routes:
        Array<{
          path: string;
          score: number;
        }> = [];

      for (
        const path of Object.keys(
          schema.paths,
        )
      ) {
        const operation =
          schema.paths[path]?.get;

        if (!operation) {
          continue;
        }

        if (!path.includes("{")) {
          continue;
        }

        const lower =
          path.toLowerCase();

        let score =
          0;

        if (
          lower.includes("task")
        ) {
          score += 100;
        }

        if (
          lower.includes("tasks")
        ) {
          score += 25;
        }

        if (
          lower.includes("result")
        ) {
          score += 25;
        }

        if (
          lower.includes("execution")
        ) {
          score += 10;
        }

        const parameters =
          Array.isArray(
            operation.parameters,
          )
            ? operation.parameters
            : [];

        for (
          const parameter of parameters
        ) {
          const name =
            String(
              parameter?.name ?? "",
            ).toLowerCase();

          if (
            name === "task_id" ||
            name === "taskid"
          ) {
            score += 60;
          }

          if (
            name === "id"
          ) {
            score += 20;
          }
        }

        routes.push({
          path,
          score,
        });
      }

      routes.sort(
        (
          left,
          right,
        ) =>
          right.score -
          left.score,
      );

      if (
        routes.length === 0
      ) {
        return null;
      }

      const selected =
        routes[0].path;

      const resolved =
        selected.replace(
          /\{[^{}]+\}/g,
          encodeURIComponent(
            taskId,
          ),
        );

      return (
        apiBase +
        resolved
      );
    };

  const speakResearchOutput =
    (
      text: string,
    ): void => {
      const clean =
        text.trim();

      if (
        clean.length === 0 ||
        !(
          "speechSynthesis" in
          window
        )
      ) {
        return;
      }

      window.speechSynthesis.cancel();

      const utterance =
        new SpeechSynthesisUtterance(
          clean,
        );

      utterance.lang =
        "tr-TR";

      utterance.rate =
        0.96;

      utterance.pitch =
        1.0;

      utterance.volume =
        1.0;

      window.speechSynthesis.speak(
        utterance,
      );
    };

  const pollTask =
    async (
      taskId: string,
    ): Promise<void> => {
      const generation =
        pollGeneration.current + 1;

      pollGeneration.current =
        generation;

      const detailUrl =
        await discoverTaskDetailPath(
          taskId,
        );

      if (!detailUrl) {
        return;
      }

      for (
        let attempt = 0;
        attempt < 30;
        attempt++
      ) {
        if (
          pollGeneration.current !==
          generation
        ) {
          return;
        }

        const task =
          await getJson(
            detailUrl,
          );

        if (task) {
          const output =
            extractResearchOutput(
              task,
            );

          if (output) {
            setResearchOutput(
              output,
            );

            if (
              spokenRef.current !==
              output
            ) {
              spokenRef.current =
                output;

              speakResearchOutput(
                output,
              );
            }

            return;
          }
        }

        await new Promise<void>(
          (
            resolve,
          ) => {
            window.setTimeout(
              resolve,
              attempt < 5
                ? 800
                : 1500,
            );
          },
        );
      }
    };

  useEffect(
    () => {
      const originalFetch =
        window.fetch.bind(
          window,
        );

      let disposed =
        false;

      window.fetch =
        async (
          input: RequestInfo | URL,
          init?: RequestInit,
        ): Promise<Response> => {
          const response =
            await originalFetch(
              input,
              init,
            );

          try {
            const url =
              typeof input === "string"
                ? input
                : input instanceof URL
                  ? input.toString()
                  : input.url;

            const method =
              String(
                init?.method ??
                (
                  input instanceof Request
                    ? input.method
                    : "GET"
                ),
              ).toUpperCase();

            if (
              (
                method === "POST" ||
                method === "PUT" ||
                method === "PATCH"
              ) &&
              response.ok &&
              /task/i.test(url)
            ) {
              const clone =
                response.clone();

              clone
                .json()
                .then(
                  (
                    payload: any,
                  ) => {
                    if (disposed) {
                      return;
                    }

                    const direct =
                      extractResearchOutput(
                        payload,
                      );

                    if (direct) {
                      setResearchOutput(
                        direct,
                      );

                      if (
                        spokenRef.current !==
                        direct
                      ) {
                        spokenRef.current =
                          direct;

                        speakResearchOutput(
                          direct,
                        );
                      }

                      return;
                    }

                    const taskId =
                      extractTaskId(
                        payload,
                      );

                    if (taskId) {
                      void pollTask(
                        taskId,
                      );
                    }
                  },
                )
                .catch(
                  () => {
                    // Non-JSON response.
                  },
                );
            }
          } catch {
            // Fetch observer must never
            // break the original request.
          }

          return response;
        };

      return () => {
        disposed = true;

        window.fetch =
          originalFetch;

        if (
          "speechSynthesis" in
          window
        ) {
          window.speechSynthesis.cancel();
        }
      };
    },
    [],
  );

  if (
    researchOutput.length === 0
  ) {
    return null;
  }

  return (
    <section className="aura-research-output">
      <div className="aura-research-output-header">
        <span>AURA RESEARCH OUTPUT</span>

        <button
          type="button"
          className="aura-research-read"
          onClick={() =>
            speakResearchOutput(
              researchOutput,
            )
          }
        >
          READ
        </button>
      </div>

      <div className="aura-research-output-body">
        {researchOutput}
      </div>
    </section>
  );
}

/* AURA_RESEARCH_OUTPUT_V5_END */
'@

# ============================================================
# START
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA RESEARCH SAFE PATCH V5"
Write-Host "============================================================"
Write-Host ""

# ============================================================
# 1. SELF PARSER
# ============================================================

Write-Host "[1/11] PowerShell parser preflight..."

$scriptPath =
    $MyInvocation.MyCommand.Path

if ($null -eq $scriptPath) {
    Fail "Script path belirlenemedi."
}

Test-SelfParser `
    -ScriptPath $scriptPath |
    Out-Null

Write-Host "    PASS"

# ============================================================
# 2. PROJECT
# ============================================================

Write-Host "[2/11] Proje dosyaları kontrol ediliyor..."

Assert-Path `
    -Path $Root `
    -Label "AURA root"

Assert-Path `
    -Path $UiRoot `
    -Label "aura-ui"

Assert-Path `
    -Path $AppFile `
    -Label "App.tsx"

Assert-Path `
    -Path $IndexFile `
    -Label "index.html"

# ============================================================
# 3. READ
# ============================================================

Write-Host "[3/11] Mevcut dosyalar okunuyor..."

$currentApp =
    Read-Utf8Text `
        -Path $AppFile

$currentIndex =
    Read-Utf8Text `
        -Path $IndexFile

# ============================================================
# CSS DISCOVERY
# ============================================================

$cssFiles =
    Get-ChildItem `
        -LiteralPath $SrcRoot `
        -Recurse `
        -Filter "*.css" `
        -File

if ($cssFiles.Count -le 0) {
    Fail "src altında CSS dosyası bulunamadı."
}

$cssFile =
    $cssFiles |
    Where-Object {
        $_.Name -match "App|index|main"
    } |
    Select-Object -First 1

if ($null -eq $cssFile) {
    $cssFile =
        $cssFiles |
        Select-Object -First 1
}

$CssFilePath =
    $cssFile.FullName

$currentCss =
    Read-Utf8Text `
        -Path $CssFilePath

# ============================================================
# 4. BACKUP
# ============================================================

Write-Host "[4/11] Rollback snapshot oluşturuluyor..."

New-Item `
    -ItemType Directory `
    -Path $RunBackup `
    -Force |
    Out-Null

$AppBackup =
    Join-Path $RunBackup "App.tsx"

$IndexBackup =
    Join-Path $RunBackup "index.html"

$CssBackup =
    Join-Path $RunBackup "styles.css"

Backup-File `
    -Source $AppFile `
    -Destination $AppBackup

Backup-File `
    -Source $IndexFile `
    -Destination $IndexBackup

Backup-File `
    -Source $CssFilePath `
    -Destination $CssBackup

# ============================================================
# 5. CLEAN SOURCE SELECTION
#
# Prefer local backup if current file contains previous patch.
# Never use Git HEAD.
# ============================================================

Write-Host "[5/11] Güvenli local App.tsx kaynağı seçiliyor..."

function Test-ResearchPatchMarkers {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $markers = @(
        "AURA_RESEARCH_OUTPUT_V4_START",
        "AURA_RESEARCH_OUTPUT_V4_END",
        "AURA_RESEARCH_OUTPUT_V5_START",
        "AURA_RESEARCH_OUTPUT_V5_END",
        "AURA_RESEARCH_OUTPUT_V3_START",
        "AURA_RESEARCH_OUTPUT_START",
        "AURA_RESEARCH_OUTPUT_CSS_V4"
    )

    foreach ($marker in $markers) {

        if (
            $Text.IndexOf(
                $marker,
                [System.StringComparison]::Ordinal
            ) -ge 0
        ) {
            return $true
        }
    }

    return $false
}

$app =
    $currentApp

if (
    Test-ResearchPatchMarkers `
        -Text $app
) {

    Write-Host "    Mevcut App.tsx önceki research patch marker'ı içeriyor."

    Assert-Path `
        -Path $BackupRoot `
        -Label ".aura-backups"

    $backupCandidates =
        Get-ChildItem `
            -LiteralPath $BackupRoot `
            -Recurse `
            -Filter "App.tsx" `
            -File |
        Sort-Object LastWriteTime -Descending

    $selectedBackup =
        $null

    foreach ($candidate in $backupCandidates) {

        try {

            $candidateText =
                Read-Utf8Text `
                    -Path $candidate.FullName

            if (
                Test-ResearchPatchMarkers `
                    -Text $candidateText
            ) {
                continue
            }

            $candidateAppOpen =
                Find-AppOpenBrace `
                    -Text $candidateText

            $candidateReturn =
                Find-AppReturnRange `
                    -Text $candidateText `
                    -AppOpenBrace $candidateAppOpen

            if (
                $candidateReturn.CloseParen -gt
                $candidateReturn.OpenParen
            ) {

                $selectedBackup =
                    $candidate

                $app =
                    $candidateText

                break
            }

        } catch {
            continue
        }
    }

    if ($null -eq $selectedBackup) {

        Fail (
            "Research patch marker içermeyen ve " +
            "export default function App() return(...) yapısı " +
            "doğrulanabilen local backup bulunamadı."
        )
    }

    Write-Host (
        "    Backup source: " +
        $selectedBackup.FullName
    )
}
else {

    Write-Host "    Source: mevcut local App.tsx"
}

Assert-Text `
    -Text $app `
    -Label "normalized App.tsx"

# ============================================================
# 6. CLEAN OLD V5 BLOCK IF ANY
# ============================================================

Write-Host "[6/11] Önceki V5 marker'ları temizleniyor..."

$app =
    Remove-MarkedBlock `
        -Text $app `
        -StartMarker "/* AURA_RESEARCH_OUTPUT_V5_START */" `
        -EndMarker "/* AURA_RESEARCH_OUTPUT_V5_END */"

# ============================================================
# REACT HOOKS
# ============================================================

$app =
    Ensure-ReactHooks `
        -Text $app

Assert-Text `
    -Text $app `
    -Label "post-import App.tsx"

# ============================================================
# 7. FIND REAL APP BEFORE INSERTING ANYTHING
# ============================================================

Write-Host "[7/11] Gerçek App() declaration ve return sınırı bulunuyor..."

$appDeclaration =
    Find-AppDeclaration `
        -Text $app

Write-Host (
    "    Declaration: " +
    $appDeclaration.Text.Trim()
)

$appOpen =
    Find-AppOpenBrace `
        -Text $app

$returnInfo =
    Find-AppReturnRange `
        -Text $app `
        -AppOpenBrace $appOpen

if (
    $returnInfo.ReturnIndex -lt
    $returnInfo.AppOpen
) {
    Fail "Return index App() öncesinde."
}

if (
    $returnInfo.CloseParen -le
    $returnInfo.OpenParen
) {
    Fail "App return paren range geçersiz."
}

Write-Host "    App declaration : PASS"
Write-Host "    App opening {   : PASS"
Write-Host "    App return(...) : PASS"

# ============================================================
# 8. INSERT RESEARCH COMPONENT
#
# IMPORTANT:
# Insert BEFORE the App declaration.
# Never insert at App's opening brace.
# ============================================================

Write-Host "[8/11] Research component module scope'a ekleniyor..."

$moduleInsert =
    $ResearchComponent +
    "`r`n`r`n"

$app =
    Insert-Text `
        -Text $app `
        -Index $appDeclaration.Index `
        -Value $moduleInsert

Assert-Text `
    -Text $app `
    -Label "research component insertion"

# ============================================================
# RE-FIND APP AFTER MODULE INSERT
# ============================================================

$appOpen =
    Find-AppOpenBrace `
        -Text $app

$returnInfo =
    Find-AppReturnRange `
        -Text $app `
        -AppOpenBrace $appOpen

# ============================================================
# 9. SAFE JSX FRAGMENT INSERTION
#
# No </div> search.
# No LastIndexOf.
# We only modify the exact App return expression.
# ============================================================

Write-Host "[9/11] App return() içine güvenli Fragment ekleniyor..."

$originalReturnBody =
    $app.Substring(
        $returnInfo.OpenParen + 1,
        $returnInfo.CloseParen -
        $returnInfo.OpenParen -
        1
    )

Assert-Text `
    -Text $originalReturnBody `
    -Label "App JSX return body"

# ------------------------------------------------------------
# Prevent duplicate insertion.
# ------------------------------------------------------------

if (
    $originalReturnBody.IndexOf(
        "<AuraResearchOutput />",
        [System.StringComparison]::Ordinal
    ) -ge 0
) {

    Fail (
        "App return içinde zaten <AuraResearchOutput /> mevcut. " +
        "Patch ikinci kez uygulanmayacak."
    )
}

# ------------------------------------------------------------
# Existing root:
#
# return (
#   <Something>
#     ...
#   </Something>
# );
#
# becomes:
#
# return (
#   <>
#     <Something>
#       ...
#     </Something>
#     <AuraResearchOutput />
#   </>
# );
#
# We intentionally wrap the COMPLETE existing return body.
# This avoids guessing the last </div>.
# ------------------------------------------------------------

$wrappedBody =
    "`r`n      <>`r`n" +
    $originalReturnBody +
    "`r`n      <AuraResearchOutput />`r`n" +
    "      </>`r`n"

$app =
    $app.Remove(
        $returnInfo.OpenParen + 1,
        $returnInfo.CloseParen -
        $returnInfo.OpenParen -
        1
    )

$app =
    Insert-Text `
        -Text $app `
        -Index ($returnInfo.OpenParen + 1) `
        -Value $wrappedBody

Assert-Text `
    -Text $app `
    -Label "wrapped App JSX"

# ============================================================
# STRUCTURAL VALIDATION
# ============================================================

Write-Host "    JSX structure validation..."

$verifyAppOpen =
    Find-AppOpenBrace `
        -Text $app

$verifyReturn =
    Find-AppReturnRange `
        -Text $app `
        -AppOpenBrace $verifyAppOpen

$jsxIndex =
    $app.IndexOf(
        "<AuraResearchOutput />",
        $verifyReturn.OpenParen,
        [System.StringComparison]::Ordinal
    )

$fragmentOpen =
    $app.IndexOf(
        "<>",
        $verifyReturn.OpenParen,
        [System.StringComparison]::Ordinal
    )

$fragmentClose =
    $app.IndexOf(
        "</>",
        $verifyReturn.OpenParen,
        [System.StringComparison]::Ordinal
    )

if ($fragmentOpen -lt 0) {
    Fail "App return Fragment açılışı bulunamadı."
}

if ($jsxIndex -lt 0) {
    Fail "AuraResearchOutput JSX çağrısı bulunamadı."
}

if ($fragmentClose -lt 0) {
    Fail "App return Fragment kapanışı bulunamadı."
}

if ($fragmentOpen -ge $jsxIndex) {
    Fail "Research Output Fragment'ın içinde değil."
}

if ($jsxIndex -ge $fragmentClose) {
    Fail "Research Output Fragment kapanışından sonra."
}

if ($fragmentClose -ge $verifyReturn.CloseParen) {
    Fail "Fragment return(...) dışına taştı."
}

# ============================================================
# REQUIRED FEATURE CHECKS
# ============================================================

$requiredMarkers = @(
    "discoverTaskDetailPath",
    "extractResearchOutput",
    "speakResearchOutput",
    "speechSynthesis",
    "SpeechSynthesisUtterance",
    'utterance.lang',
    "AURA_RESEARCH_OUTPUT_V5_START",
    "AURA_RESEARCH_OUTPUT_V5_END"
)

foreach ($marker in $requiredMarkers) {

    if (
        $app.IndexOf(
            $marker,
            [System.StringComparison]::Ordinal
        ) -lt 0
    ) {
        Fail (
            "Required marker/function bulunamadı: " +
            $marker
        )
    }
}

# ============================================================
# TYPE SCRIPT OPERATOR GUARD
#
# Detect accidental PowerShell operators inside the generated
# ResearchComponent block.
# ============================================================

$researchStart =
    $app.IndexOf(
        "/* AURA_RESEARCH_OUTPUT_V5_START */",
        [System.StringComparison]::Ordinal
    )

$researchEnd =
    $app.IndexOf(
        "/* AURA_RESEARCH_OUTPUT_V5_END */",
        $researchStart,
        [System.StringComparison]::Ordinal
    )

if (
    $researchStart -lt 0 -or
    $researchEnd -lt 0
) {
    Fail "Research component validation range bulunamadı."
}

$researchLength =
    $researchEnd -
    $researchStart

$researchBlock =
    $app.Substring(
        $researchStart,
        $researchLength
    )

# Accidental PowerShell relational operators in TS are forbidden.
$badTsOperatorPatterns = @(
    '\b[A-Za-z0-9_.\)\]]+\s+-gt\s+',
    '\b[A-Za-z0-9_.\)\]]+\s+-ge\s+',
    '\b[A-Za-z0-9_.\)\]]+\s+-lt\s+',
    '\b[A-Za-z0-9_.\)\]]+\s+-le\s+'
)

foreach ($pattern in $badTsOperatorPatterns) {

    if (
        $researchBlock -match $pattern
    ) {
        Fail (
            "TypeScript research block içinde PowerShell " +
            "comparison operator bulundu: " +
            $pattern
        )
    }
}

# ============================================================
# WRITE APP
# ============================================================

Write-Host "    JSX structure : PASS"
Write-Host "    Research API  : PASS"
Write-Host "    Turkish TTS   : PASS"
Write-Host "    TS operators  : PASS"

Write-Utf8Text `
    -Path $AppFile `
    -Text $app

# ============================================================
# INDEX.HTML
# ============================================================

Write-Host "[10/11] index.html normalize ediliyor..."

$index =
    $currentIndex

if (
    $index -match
    '(?i)<html\b[^>]*\blang\s*=\s*["''][^"'']*["'']'
) {

    $index =
        [regex]::Replace(
            $index,
            '(?i)(<html\b[^>]*\blang\s*=\s*["''])[^"'']*(["''])',
            '${1}tr-TR${2}',
            1
        )
}
else {

    if (
        $index -match
        '(?i)<html\b'
    ) {

        $index =
            [regex]::Replace(
                $index,
                '(?i)<html\b',
                '<html lang="tr-TR"',
                1
            )
    }
    else {
        Fail "index.html <html> etiketi bulunamadı."
    }
}

if (
    $index -match
    '(?is)<title>.*?</title>'
) {

    $index =
        [regex]::Replace(
            $index,
            '(?is)<title>.*?</title>',
            '<title>AURA JAS HUD</title>',
            1
        )
}
else {

    $head =
        [regex]::Match(
            $index,
            '(?is)<head\b[^>]*>'
        )

    if ($head.Success) {

        $index =
            Insert-Text `
                -Text $index `
                -Index (
                    $head.Index +
                    $head.Length
                ) `
                -Value "`r`n    <title>AURA JAS HUD</title>"
    }
}

Write-Utf8Text `
    -Path $IndexFile `
    -Text $index

# ============================================================
# CSS
# ============================================================

$css =
    $currentCss

if (
    $css.IndexOf(
        "AURA_RESEARCH_OUTPUT_CSS_V5",
        [System.StringComparison]::Ordinal
    ) -lt 0
) {

    $cssBlock = @'

/* ============================================================
   AURA_RESEARCH_OUTPUT_CSS_V5
   ============================================================ */

.aura-research-output {
  width: min(760px, 92vw);
  max-height: 32vh;
  margin: 12px auto 0;
  overflow: hidden;
  border: 1px solid rgba(34, 211, 238, 0.28);
  border-radius: 12px;
  background: rgba(2, 8, 18, 0.90);
  backdrop-filter: blur(14px);
  box-shadow: 0 0 26px rgba(34, 211, 238, 0.08);
  z-index: 20;
}

.aura-research-output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.18);
  font-family: Consolas, "Courier New", monospace;
  font-size: 11px;
  letter-spacing: 0.16em;
  color: rgb(103, 232, 249);
}

.aura-research-read {
  padding: 4px 9px;
  border: 1px solid rgba(34, 211, 238, 0.40);
  border-radius: 5px;
  background: transparent;
  font-family: Consolas, "Courier New", monospace;
  font-size: 10px;
  letter-spacing: 0.10em;
  color: rgb(103, 232, 249);
  cursor: pointer;
}

.aura-research-read:hover {
  border-color: rgb(103, 232, 249);
  box-shadow: 0 0 14px rgba(34, 211, 238, 0.18);
}

.aura-research-output-body {
  max-height: 26vh;
  overflow-y: auto;
  padding: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.55;
  color: rgb(165, 243, 252);
}

@media (max-width: 900px) {
  .aura-research-output {
    width: 92vw;
    max-height: 38vh;
  }

  .aura-research-output-body {
    max-height: 32vh;
  }
}

'@

    $css =
        $css +
        $cssBlock

    Write-Utf8Text `
        -Path $CssFilePath `
        -Text $css
}

# ============================================================
# FINAL FILE CHECK
# ============================================================

$finalApp =
    Read-Utf8Text `
        -Path $AppFile

$finalIndex =
    Read-Utf8Text `
        -Path $IndexFile

$finalCss =
    Read-Utf8Text `
        -Path $CssFilePath

Assert-Text -Text $finalApp -Label "final App.tsx"
Assert-Text -Text $finalIndex -Label "final index.html"
Assert-Text -Text $finalCss -Label "final CSS"

# ============================================================
# BUILD
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " npm run build"
Write-Host "============================================================"
Write-Host ""

$buildExit = 999

Push-Location $UiRoot

try {

    & npm run build

    $buildExit =
        $LASTEXITCODE
}
finally {

    Pop-Location
}

# ============================================================
# ROLLBACK
# ============================================================

if ($buildExit -ne 0) {

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " BUILD FAILED - FULL ROLLBACK"
    Write-Host "============================================================"
    Write-Host ""

    Restore-File `
        -Backup $AppBackup `
        -Destination $AppFile

    Restore-File `
        -Backup $IndexBackup `
        -Destination $IndexFile

    Restore-File `
        -Backup $CssBackup `
        -Destination $CssFilePath

    Write-Host "Rollback tamamlandı."
    Write-Host ""
    Write-Host (
        "Backup: " +
        $RunBackup
    )
    Write-Host ""

    Fail (
        "npm run build başarısız oldu. " +
        "Tüm değişiklikler rollback edildi. " +
        "ExitCode=" +
        $buildExit
    )
}

# ============================================================
# SUCCESS
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA RESEARCH SAFE PATCH V5 - SUCCESS"
Write-Host "============================================================"
Write-Host ""
Write-Host "PowerShell parser       : PASS"
Write-Host "Explicit App discovery  : PASS"
Write-Host "App return discovery    : PASS"
Write-Host "Module-scope component  : PASS"
Write-Host "Fragment JSX injection  : PASS"
Write-Host "OpenAPI route discovery : ENABLED"
Write-Host "Recursive extraction    : ENABLED"
Write-Host "Turkish TTS             : ENABLED"
Write-Host "TypeScript operators    : PASS"
Write-Host "index.html              : UPDATED"
Write-Host "Research CSS            : UPDATED"
Write-Host "npm run build           : PASS"
Write-Host ""
Write-Host "Rollback snapshot:"
Write-Host $RunBackup
Write-Host ""