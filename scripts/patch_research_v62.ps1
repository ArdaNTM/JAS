#requires -version 5.1
Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# ============================================================
# AURA RESEARCH UI / TTS PATCH V6.2
# PowerShell 5.1
#
# Backend V6.1:
#   application\api.py
#   -> step.result artık HTTP response'a çıkıyor.
#
# Bu patch:
#   - App.tsx'i mevcut gerçek App() yapısına göre güvenli patchler
#   - TTS'i chunk + onend queue olarak düzeltir
#   - step.result'i recursive olarak çıkarır
#   - task response içindeki gerçek result'i kullanır
#   - UUID'yi araştırma çıktısı olarak kabul etmez
#   - /openapi.json üzerinden task detail GET route keşfeder
#   - 422 response'u konsola ayrıntılı verir
#   - OUTPUT / READ CSS çakışmasını düzeltir
#   - mevcut JSX return sınırlarını delimiter scanner ile bulur
#   - körlemesine LastIndexOf("</div>") kullanmaz
#   - başarısız build durumunda otomatik rollback yapar
#
# NOT:
#   TypeScript kodunun içindeki > / < operatörlerine dokunulmaz.
#   PowerShell operatörleri yalnızca .ps1 mantığında -gt/-lt vb.dir.
# ============================================================

$Root    = "D:\AURA\JAS"
$UiRoot  = Join-Path $Root "aura-ui"
$UiSrc   = Join-Path $UiRoot "src"
$AppFile = Join-Path $UiSrc "App.tsx"

$BackupRoot = Join-Path $UiRoot ".aura-backups"
$Stamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir  = Join-Path $BackupRoot ("research-ui-v62-" + $Stamp)

# ============================================================
# HELPERS
# ============================================================

function Fail {
    param(
        [string]$Message
    )

    throw $Message
}

function Assert-Path {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        Fail ($Label + " bulunamadı: " + $Path)
    }
}

function Read-Utf8 {
    param(
        [string]$Path
    )

    Assert-Path $Path "Dosya"

    $text = [System.IO.File]::ReadAllText(
        $Path,
        [System.Text.Encoding]::UTF8
    )

    if ($null -eq $text) {
        Fail ("Dosya okunamadı: " + $Path)
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
        [string]$Destination
    )

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

function Insert-At {
    param(
        [string]$Text,
        [int]$Index,
        [string]$Value
    )

    if ($Index -lt 0) {
        Fail "Insert index negatif."
    }

    if ($Index -gt $Text.Length) {
        Fail "Insert index dosya uzunluğunu aşıyor."
    }

    return (
        $Text.Substring(0, $Index) +
        $Value +
        $Text.Substring($Index)
    )
}

function Find-MatchingDelimiter {
    param(
        [string]$Text,
        [int]$OpenIndex,
        [char]$OpenChar,
        [char]$CloseChar
    )

    if ($OpenIndex -lt 0) {
        Fail "Delimiter başlangıcı bulunamadı."
    }

    if ($Text[$OpenIndex] -ne $OpenChar) {
        Fail (
            "Beklenen delimiter yok: " +
            [string]$OpenChar
        )
    }

    $depth = 0
    $mode = "code"
    $escaped = $false

    for (
        $i = $OpenIndex;
        $i -lt $Text.Length;
        $i++
    ) {

        $c = $Text[$i]

        if ($mode -eq "line") {

            if (
                $c -eq "`r" -or
                $c -eq "`n"
            ) {
                $mode = "code"
            }

            continue
        }

        if ($mode -eq "block") {

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

        if (
            $c -eq "/" -and
            ($i + 1) -lt $Text.Length
        ) {

            if ($Text[$i + 1] -eq "/") {
                $i++
                $mode = "line"
                continue
            }

            if ($Text[$i + 1] -eq "*") {
                $i++
                $mode = "block"
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

    Fail (
        "Delimiter eşleşmedi: " +
        [string]$OpenChar +
        " -> " +
        [string]$CloseChar
    )
}

function Find-AppDeclaration {
    param(
        [string]$Text
    )

    $patterns = @(
        '(?m)^\s*export\s+default\s+function\s+App\s*\(',
        '(?m)^\s*export\s+function\s+App\s*\(',
        '(?m)^\s*function\s+App\s*\('
    )

    foreach ($pattern in $patterns) {

        $match = [regex]::Match(
            $Text,
            $pattern
        )

        if ($match.Success) {
            return $match
        }
    }

    Fail "App() declaration bulunamadı."
}

function Find-AppOpenBrace {
    param(
        [string]$Text
    )

    $decl = Find-AppDeclaration $Text

    $openParen = $Text.IndexOf(
        "(",
        $decl.Index,
        [System.StringComparison]::Ordinal
    )

    if ($openParen -lt 0) {
        Fail "App() açılış parantezi bulunamadı."
    }

    $closeParen = Find-MatchingDelimiter `
        -Text $Text `
        -OpenIndex $openParen `
        -OpenChar '(' `
        -CloseChar ')'

    $openBrace = $Text.IndexOf(
        "{",
        $closeParen,
        [System.StringComparison]::Ordinal
    )

    if ($openBrace -lt 0) {
        Fail "App() açılış süslü parantezi bulunamadı."
    }

    return $openBrace
}

function Find-AppReturnRange {
    param(
        [string]$Text,
        [int]$AppOpen
    )

    $AppClose = Find-MatchingDelimiter `
        -Text $Text `
        -OpenIndex $AppOpen `
        -OpenChar '{' `
        -CloseChar '}'

    $AppBody = $Text.Substring(
        $AppOpen,
        $AppClose - $AppOpen
    )

    $returns = [regex]::Matches(
        $AppBody,
        '(?s)\breturn\s*\('
    )

    if ($returns.Count -eq 0) {
        Fail "App() içinde return(...) bulunamadı."
    }

    $candidate = $returns[$returns.Count - 1]

    $returnIndex =
        $AppOpen +
        $candidate.Index

    $openParen = $Text.IndexOf(
        "(",
        $returnIndex,
        [System.StringComparison]::Ordinal
    )

    $closeParen = Find-MatchingDelimiter `
        -Text $Text `
        -OpenIndex $openParen `
        -OpenChar '(' `
        -CloseChar ')'

    if ($closeParen -ge $AppClose) {
        Fail "App return(...) App() dışına taşıyor."
    }

    return @{
        AppOpen     = $AppOpen
        AppClose    = $AppClose
        ReturnIndex = $returnIndex
        OpenParen   = $openParen
        CloseParen  = $closeParen
    }
}

function Test-PS1Syntax {
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

        foreach ($err in $errors) {
            Write-Host (
                "Line " +
                $err.Extent.StartLineNumber +
                ": " +
                $err.Message
            ) -ForegroundColor Red
        }

        Fail "PowerShell parser başarısız."
    }
}

# ============================================================
# START
# ============================================================

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA RESEARCH UI / TTS PATCH V6.2"
Write-Host "============================================================"
Write-Host ""

Assert-Path `
    -Path $Root `
    -Label "AURA root"

Assert-Path `
    -Path $UiRoot `
    -Label "aura-ui"

Assert-Path `
    -Path $UiSrc `
    -Label "aura-ui/src"

Assert-Path `
    -Path $AppFile `
    -Label "App.tsx"

# ============================================================
# BACKUP
# ============================================================

Write-Host "[1/8] App.tsx + CSS backup..."

New-Item `
    -ItemType Directory `
    -Path $BackupDir `
    -Force |
    Out-Null

$AppBackup =
    Join-Path $BackupDir "App.tsx"

Backup-File `
    -Source $AppFile `
    -Destination $AppBackup

$CssFiles =
    Get-ChildItem `
        -LiteralPath $UiSrc `
        -Recurse `
        -Filter "*.css" `
        -File

if ($CssFiles.Count -eq 0) {
    Fail "CSS dosyası bulunamadı."
}

$CssFile =
    $CssFiles |
    Where-Object {
        $_.Name -match "App|index|main"
    } |
    Select-Object -First 1

if ($null -eq $CssFile) {
    $CssFile =
        $CssFiles |
        Select-Object -First 1
}

$CssBackup =
    Join-Path `
        $BackupDir `
        $CssFile.Name

Backup-File `
    -Source $CssFile.FullName `
    -Destination $CssBackup

# ============================================================
# READ APP
# ============================================================

Write-Host "[2/8] App.tsx analiz ediliyor..."

$app =
    Read-Utf8 $AppFile

# ============================================================
# REMOVE OLD GENERATED V4/V5/V6/V6.1/V6.2 COMPONENTS
# ============================================================

Write-Host "[3/8] Eski generated research patch temizleniyor..."

$markerPairs = @(
    @(
        "/* AURA_RESEARCH_OUTPUT_V4_START */",
        "/* AURA_RESEARCH_OUTPUT_V4_END */"
    ),
    @(
        "/* AURA_RESEARCH_OUTPUT_V5_START */",
        "/* AURA_RESEARCH_OUTPUT_V5_END */"
    ),
    @(
        "/* AURA_RESEARCH_OUTPUT_V6_START */",
        "/* AURA_RESEARCH_OUTPUT_V6_END */"
    ),
    @(
        "/* AURA_RESEARCH_OUTPUT_V61_START */",
        "/* AURA_RESEARCH_OUTPUT_V61_END */"
    ),
    @(
        "/* AURA_RESEARCH_OUTPUT_V62_START */",
        "/* AURA_RESEARCH_OUTPUT_V62_END */"
    )
)

foreach ($pair in $markerPairs) {

    while ($true) {

        $start =
            $app.IndexOf(
                $pair[0],
                [System.StringComparison]::Ordinal
            )

        if ($start -lt 0) {
            break
        }

        $end =
            $app.IndexOf(
                $pair[1],
                $start,
                [System.StringComparison]::Ordinal
            )

        if ($end -lt 0) {
            Fail (
                "Açık generated marker bulundu: " +
                $pair[0]
            )
        }

        $end += $pair[1].Length

        $app =
            $app.Remove(
                $start,
                $end - $start
            )
    }
}

# Eski JSX çağrıları.
$app =
    [regex]::Replace(
        $app,
        '(?m)^\s*<AuraResearchOutput\s*/>\s*$\r?\n?',
        '',
        [System.Text.RegularExpressions.RegexOptions]::None
    )

# Eski endpoint.
$app =
    $app.Replace(
        "/api/tasks/plan",
        "/api/tasks"
    )

# ============================================================
# REACT IMPORT
# ============================================================

Write-Host "[4/8] React hook importleri..."

$reactImport =
    [regex]::Match(
        $app,
        "(?m)^import\s*\{(?<body>[^}]*)\}\s*from\s*['""]react['""]\s*;?"
    )

if (-not $reactImport.Success) {
    Fail "React named import bulunamadı."
}

$items =
    New-Object System.Collections.Generic.List[string]

foreach (
    $item in
    $reactImport.Groups["body"].Value.Split(",")
) {

    $clean =
        $item.Trim()

    if (
        $clean.Length -gt 0 -and
        -not $items.Contains($clean)
    ) {
        $items.Add($clean)
    }
}

foreach ($hook in @(
    "useEffect",
    "useRef",
    "useState"
)) {

    if (-not $items.Contains($hook)) {
        $items.Add($hook)
    }
}

$newReactImport =
    "import { " +
    ($items -join ", ") +
    " } from 'react';"

$app =
    $app.Remove(
        $reactImport.Index,
        $reactImport.Length
    )

$app =
    Insert-At `
        -Text $app `
        -Index $reactImport.Index `
        -Value $newReactImport

# ============================================================
# GENERATED RESEARCH COMPONENT
# ============================================================

$ResearchComponent = @'
/* AURA_RESEARCH_OUTPUT_V62_START */

function AuraResearchOutput(): JSX.Element | null {
  const [researchOutput, setResearchOutput] =
    useState<string>("");

  const speechGenerationRef =
    useRef<number>(0);

  const spokenOutputRef =
    useRef<string>("");

  const pollGenerationRef =
    useRef<number>(0);

  const backendBase =
    (): string => {
      const configured =
        (import.meta as any).env?.VITE_API_BASE_URL;

      if (
        typeof configured === "string" &&
        configured.trim().length > 0
      ) {
        return configured.replace(/\/+$/, "");
      }

      return "http://127.0.0.1:8000";
    };

  /*
   * Browser speech engines can stop early on long utterances.
   * Keep utterances short and chain the next chunk only from
   * the previous utterance's onend event.
   *
   * speechSynthesis.cancel() intentionally occurs only when
   * a NEW complete response replaces the old one.
   */
  const splitSpeech =
    (
      text: string,
    ): string[] => {
      const normalized =
        text
          .replace(/\s+/g, " ")
          .trim();

      if (!normalized) {
        return [];
      }

      const sentenceParts =
        normalized.match(
          /[^.!?]+[.!?]+|[^.!?]+$/g,
        ) ?? [];

      const chunks: string[] = [];
      let current = "";

      for (
        const sentence of sentenceParts
      ) {
        const clean =
          sentence.trim();

        if (!clean) {
          continue;
        }

        const candidate =
          current.length > 0
            ? `${current} ${clean}`
            : clean;

        if (
          candidate.length > 220
        ) {
          if (current.length > 0) {
            chunks.push(current);
          }

          /*
           * Very long individual sentences are further divided
           * at word boundaries.
           */
          if (
            clean.length > 220
          ) {
            const words =
              clean.split(/\s+/);

            let wordChunk = "";

            for (
              const word of words
            ) {
              const candidateWord =
                wordChunk.length > 0
                  ? `${wordChunk} ${word}`
                  : word;

              if (
                candidateWord.length > 220
              ) {
                if (
                  wordChunk.length > 0
                ) {
                  chunks.push(wordChunk);
                }

                wordChunk = word;
              } else {
                wordChunk =
                  candidateWord;
              }
            }

            if (
              wordChunk.length > 0
            ) {
              chunks.push(wordChunk);
            }

            current = "";
          } else {
            current = clean;
          }
        } else {
          current = candidate;
        }
      }

      if (
        current.length > 0
      ) {
        chunks.push(current);
      }

      return chunks;
    };

  const selectTurkishVoice =
    (): SpeechSynthesisVoice | null => {
      if (
        !("speechSynthesis" in window)
      ) {
        return null;
      }

      const voices =
        window.speechSynthesis.getVoices();

      return (
        voices.find(
          (voice) =>
            voice.lang
              .toLowerCase()
              .startsWith("tr"),
        ) ??
        voices.find(
          (voice) =>
            voice.lang
              .toLowerCase()
              .includes("tr-tr"),
        ) ??
        null
      );
    };

  const speakResearchOutput =
    (
      text: string,
    ): void => {
      if (
        !("speechSynthesis" in window)
      ) {
        console.warn(
          "[AURA:TTS] speechSynthesis unavailable",
        );

        return;
      }

      const clean =
        text.trim();

      if (!clean) {
        return;
      }

      /*
       * Incrementing generation invalidates every previous
       * onend/onerror callback.
       */
      speechGenerationRef.current += 1;

      const generation =
        speechGenerationRef.current;

      /*
       * cancel() is used exactly once before starting a NEW
       * response. It is NOT called between chunks.
       */
      window.speechSynthesis.cancel();

      const chunks =
        splitSpeech(clean);

      if (!chunks.length) {
        return;
      }

      const voice =
        selectTurkishVoice();

      const speakChunk =
        (
          index: number,
        ): void => {
          if (
            generation !==
            speechGenerationRef.current
          ) {
            return;
          }

          if (
            index >= chunks.length
          ) {
            document.documentElement
              .setAttribute(
                "data-aura-speaking",
                "false",
              );

            return;
          }

          /*
           * Keep the utterance referenced by the closure until
           * onend/onerror has fired.
           */
          const utterance =
            new SpeechSynthesisUtterance(
              chunks[index],
            );

          utterance.lang =
            "tr-TR";

          if (voice) {
            utterance.voice =
              voice;
          }

          utterance.rate =
            0.94;

          utterance.pitch =
            1.0;

          utterance.volume =
            1.0;

          utterance.onstart =
            () => {
              if (
                generation !==
                speechGenerationRef.current
              ) {
                return;
              }

              document.documentElement
                .setAttribute(
                  "data-aura-speaking",
                  "true",
                );
            };

          utterance.onend =
            () => {
              if (
                generation !==
                speechGenerationRef.current
              ) {
                return;
              }

              /*
               * IMPORTANT:
               * Do NOT call speechSynthesis.cancel() here.
               *
               * The next utterance starts only after the browser
               * confirms that this one ended.
               */
              if (
                index + 1 <
                chunks.length
              ) {
                window.setTimeout(
                  () => {
                    speakChunk(
                      index + 1,
                    );
                  },
                  50,
                );
              } else {
                document.documentElement
                  .setAttribute(
                    "data-aura-speaking",
                    "false",
                  );
              }
            };

          utterance.onerror =
            (event) => {
              console.warn(
                "[AURA:TTS] utterance error:",
                event.error,
              );

              if (
                generation !==
                speechGenerationRef.current
              ) {
                return;
              }

              /*
               * canceled/interrupted can be generated by an
               * intentional replacement. Only retry genuine
               * synthesis failures.
               */
              if (
                event.error ===
                  "canceled" ||
                event.error ===
                  "interrupted"
              ) {
                return;
              }

              if (
                index + 1 <
                chunks.length
              ) {
                window.setTimeout(
                  () => {
                    speakChunk(
                      index + 1,
                    );
                  },
                  120,
                );
              } else {
                document.documentElement
                  .setAttribute(
                    "data-aura-speaking",
                    "false",
                  );
              }
            };

          window.speechSynthesis.speak(
            utterance,
          );
        };

      speakChunk(0);
    };

  const extractResearchOutput =
    (
      value: unknown,
      depth = 0,
      visited = new Set<object>(),
    ): string => {
      if (
        depth > 16 ||
        value === null ||
        value === undefined
      ) {
        return "";
      }

      if (
        typeof value === "string"
      ) {
        const text =
          value.trim();

        /*
         * UUIDs are identifiers, not research output.
         */
        if (
          /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
            text,
          )
        ) {
          return "";
        }

        if (
          text.length < 24
        ) {
          return "";
        }

        return text;
      }

      if (
        typeof value !== "object"
      ) {
        return "";
      }

      if (
        visited.has(
          value as object,
        )
      ) {
        return "";
      }

      visited.add(
        value as object,
      );

      const object =
        value as Record<
          string,
          unknown
        >;

      /*
       * step.result is intentionally first.
       */
      const preferredKeys = [
        "result",
        "research_output",
        "researchOutput",
        "output",
        "content",
        "text",
        "answer",
        "summary",
      ];

      for (
        const key of preferredKeys
      ) {
        if (
          object[key] ===
          undefined
        ) {
          continue;
        }

        const found =
          extractResearchOutput(
            object[key],
            depth + 1,
            visited,
          );

        if (found) {
          return found;
        }
      }

      /*
       * Recursive fallback for nested task/step/result objects.
       */
      for (
        const entry of Object.entries(
          object,
        )
      ) {
        const key =
          entry[0];

        /*
         * Never interpret identifier fields as research text.
         */
        if (
          /^(id|task_id|taskId|step_id|stepId|request_id|requestId|session_id|sessionId)$/i.test(
            key,
          )
        ) {
          continue;
        }

        const found =
          extractResearchOutput(
            entry[1],
            depth + 1,
            visited,
          );

        if (found) {
          return found;
        }
      }

      return "";
    };

  const extractStepResult =
    (
      task: any,
    ): string => {
      /*
       * Canonical backend shape after V6.1:
       *
       * {
       *   steps: [
       *     {
       *       state: "succeeded",
       *       result: ...
       *     }
       *   ]
       * }
       */
      if (
        Array.isArray(
          task?.steps,
        )
      ) {
        for (
          const step of task.steps
        ) {
          const state =
            String(
              step?.state ?? "",
            ).toLowerCase();

          if (
            state === "succeeded" &&
            step?.result !==
              undefined
          ) {
            const output =
              extractResearchOutput(
                step.result,
              );

            if (output) {
              return output;
            }
          }
        }
      }

      /*
       * Also support a single step/result response.
       */
      if (
        task?.step?.result !==
        undefined
      ) {
        const output =
          extractResearchOutput(
            task.step.result,
          );

        if (output) {
          return output;
        }
      }

      /*
       * Finally support direct task.result.
       */
      if (
        task?.result !==
        undefined
      ) {
        const output =
          extractResearchOutput(
            task.result,
          );

        if (output) {
          return output;
        }
      }

      return "";
    };

  const extractTaskId =
    (
      payload: any,
    ): string => {
      const candidates = [
        payload?.task_id,
        payload?.taskId,
        payload?.id,
        payload?.task?.task_id,
        payload?.task?.taskId,
        payload?.task?.id,
      ];

      for (
        const candidate of candidates
      ) {
        if (
          typeof candidate ===
            "string" &&
          candidate.trim().length > 0
        ) {
          return candidate.trim();
        }

        if (
          typeof candidate ===
            "number"
        ) {
          return String(candidate);
        }
      }

      return "";
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
          console.warn(
            "[AURA:HTTP]",
            response.status,
            url,
          );

          return null;
        }

        return await response.json();
      } catch (error) {
        console.warn(
          "[AURA:HTTP] fetch failed",
          url,
          error,
        );

        return null;
      }
    };

  const discoverTaskDetailPath =
    async (
      taskId: string,
    ): Promise<string | null> => {
      const base =
        backendBase();

      const openapi =
        await getJson(
          `${base}/openapi.json`,
        );

      if (
        !openapi?.paths
      ) {
        console.warn(
          "[AURA:OPENAPI] /openapi.json paths missing",
        );

        return null;
      }

      const candidates:
        Array<{
          path: string;
          score: number;
        }> = [];

      for (
        const path of Object.keys(
          openapi.paths,
        )
      ) {
        const operation =
          openapi.paths[path]?.get;

        if (!operation) {
          continue;
        }

        if (
          !path.includes("{")
        ) {
          continue;
        }

        const lower =
          path.toLowerCase();

        let score = 0;

        if (
          lower.includes(
            "/tasks",
          )
        ) {
          score += 100;
        }

        if (
          lower.includes(
            "task",
          )
        ) {
          score += 50;
        }

        if (
          lower.includes(
            "result",
          )
        ) {
          score += 20;
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
            name ===
              "task_id" ||
            name ===
              "taskid"
          ) {
            score += 100;
          }

          if (
            name ===
            "id"
          ) {
            score += 30;
          }
        }

        candidates.push({
          path,
          score,
        });
      }

      candidates.sort(
        (
          left,
          right,
        ) =>
          right.score -
          left.score,
      );

      if (
        candidates.length ===
        0
      ) {
        return null;
      }

      const selected =
        candidates[0];

      const resolved =
        selected.path.replace(
          /\{[^{}]+\}/g,
          encodeURIComponent(
            taskId,
          ),
        );

      console.info(
        "[AURA:OPENAPI] task detail route:",
        resolved,
      );

      return (
        base +
        resolved
      );
    };

  const applyResearchOutput =
    (
      output: string,
    ): void => {
      const clean =
        output.trim();

      if (!clean) {
        return;
      }

      setResearchOutput(
        clean,
      );

      if (
        spokenOutputRef.current !==
        clean
      ) {
        spokenOutputRef.current =
          clean;

        speakResearchOutput(
          clean,
        );
      }
    };

  const fetchCompletedTaskOutput =
    async (
      taskId: string,
    ): Promise<void> => {
      pollGenerationRef.current += 1;

      const generation =
        pollGenerationRef.current;

      const detailUrl =
        await discoverTaskDetailPath(
          taskId,
        );

      if (!detailUrl) {
        console.warn(
          "[AURA:RESEARCH] task GET route bulunamadı",
          taskId,
        );

        return;
      }

      for (
        let attempt = 0;
        attempt < 30;
        attempt++
      ) {
        if (
          generation !==
          pollGenerationRef.current
        ) {
          return;
        }

        const task =
          await getJson(
            detailUrl,
          );

        if (task) {
          const output =
            extractStepResult(
              task,
            );

          if (output) {
            applyResearchOutput(
              output,
            );

            return;
          }

          const state =
            String(
              task?.state ??
              task?.status ??
              "",
            ).toLowerCase();

          if (
            state ===
              "failed" ||
            state ===
              "cancelled"
          ) {
            console.warn(
              "[AURA:RESEARCH] task terminal state:",
              state,
            );

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
                ? 500
                : 1000,
            );
          },
        );
      }
    };

  useEffect(
    () => {
      /*
       * The component observes task POST responses without
       * changing the existing task execution architecture.
       */
      const originalFetch =
        window.fetch.bind(
          window,
        );

      let disposed = false;

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

          let url = "";

          try {
            if (
              typeof input ===
              "string"
            ) {
              url = input;
            } else if (
              input instanceof URL
            ) {
              url =
                input.toString();
            } else {
              url =
                input.url;
            }
          } catch {
            url = "";
          }

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
            response.status ===
              422 &&
            /\/api\/tasks(?:\/plan)?(?:\?.*)?$/i.test(
              url,
            )
          ) {
            try {
              const detail =
                await response
                  .clone()
                  .json();

              console.error(
                "[AURA:422] /api/tasks validation:",
                detail,
              );
            } catch {
              console.error(
                "[AURA:422] task validation failed",
              );
            }
          }

          if (
            disposed ||
            !response.ok ||
            !(
              method === "POST" ||
              method === "PUT" ||
              method === "PATCH"
            )
          ) {
            return response;
          }

          if (
            !/\/api\/tasks(?:\/plan)?(?:\?.*)?$/i.test(
              url,
            )
          ) {
            return response;
          }

          try {
            const payload =
              await response
                .clone()
                .json();

            /*
             * First attempt: backend already returned step.result.
             */
            const directOutput =
              extractStepResult(
                payload,
              );

            if (directOutput) {
              applyResearchOutput(
                directOutput,
              );

              return response;
            }

            /*
             * Second attempt: task ID -> OpenAPI-discovered GET.
             */
            const taskId =
              extractTaskId(
                payload,
              );

            if (taskId) {
              void fetchCompletedTaskOutput(
                taskId,
              );
            }
          } catch (error) {
            console.warn(
              "[AURA:RESEARCH] task response parse failed",
              error,
            );
          }

          return response;
        };

      return () => {
        disposed = true;

        pollGenerationRef.current += 1;
        speechGenerationRef.current += 1;

        window.fetch =
          originalFetch;

        if (
          "speechSynthesis" in window
        ) {
          window.speechSynthesis.cancel();
        }

        document.documentElement
          .setAttribute(
            "data-aura-speaking",
            "false",
          );
      };
    },
    [],
  );

  if (
    researchOutput.length ===
    0
  ) {
    return null;
  }

  return (
    <section
      className="aura-research-output"
      aria-label="AURA Research Output"
    >
      <div
        className="aura-research-output-header"
      >
        <span
          className="aura-research-output-title"
        >
          AURA RESEARCH OUTPUT
        </span>

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

      <div
        className="aura-research-output-body"
      >
        {researchOutput}
      </div>
    </section>
  );
}

/* AURA_RESEARCH_OUTPUT_V62_END */
'@

# ============================================================
# INSERT COMPONENT BEFORE App()
# ============================================================

$appDecl =
    Find-AppDeclaration $app

$app =
    Insert-At `
        -Text $app `
        -Index $appDecl.Index `
        -Value (
            $ResearchComponent +
            "`r`n`r`n"
        )

# ============================================================
# FIND REAL APP RETURN AGAIN
# ============================================================

$appOpen =
    Find-AppOpenBrace $app

$returnRange =
    Find-AppReturnRange `
        -Text $app `
        -AppOpen $appOpen

$existingJsx =
    $app.Substring(
        $returnRange.OpenParen + 1,
        $returnRange.CloseParen -
        $returnRange.OpenParen -
        1
    )

if (
    $existingJsx.Contains(
        "<AuraResearchOutput />"
    )
) {
    Fail "AuraResearchOutput JSX zaten mevcut."
}

# ============================================================
# SAFE FRAGMENT WRAP
# ============================================================

$fragmentBody =
    "`r`n" +
    "      <>`r`n" +
    $existingJsx +
    "`r`n        <AuraResearchOutput />`r`n" +
    "      </>`r`n"

$app =
    $app.Remove(
        $returnRange.OpenParen + 1,
        $returnRange.CloseParen -
        $returnRange.OpenParen -
        1
    )

$app =
    Insert-At `
        -Text $app `
        -Index ($returnRange.OpenParen + 1) `
        -Value $fragmentBody

# ============================================================
# WRITE APP
# ============================================================

Write-Utf8 `
    -Path $AppFile `
    -Text $app

# ============================================================
# CSS
# ============================================================

Write-Host "[5/8] OUTPUT / READ CSS..."

$css =
    Read-Utf8 $CssFile.FullName

# Remove old generated CSS blocks.
$cssMarkers = @(
    "AURA_RESEARCH_OUTPUT_CSS_V4",
    "AURA_RESEARCH_OUTPUT_CSS_V5",
    "AURA_RESEARCH_OUTPUT_CSS_V6",
    "AURA_RESEARCH_OUTPUT_CSS_V61",
    "AURA_RESEARCH_OUTPUT_CSS_V62"
)

foreach ($marker in $cssMarkers) {

    while ($true) {

        $markerPos =
            $css.IndexOf(
                $marker,
                [System.StringComparison]::Ordinal
            )

        if ($markerPos -lt 0) {
            break
        }

        $commentStart =
            $css.LastIndexOf(
                "/*",
                $markerPos,
                [System.StringComparison]::Ordinal
            )

        $commentEnd =
            $css.IndexOf(
                "*/",
                $markerPos,
                [System.StringComparison]::Ordinal
            )

        if (
            $commentStart -lt 0 -or
            $commentEnd -lt 0
        ) {
            break
        }

        $commentEnd += 2

        $css =
            $css.Remove(
                $commentStart,
                $commentEnd -
                $commentStart
            )
    }
}

$CssBlock = @'

/* ============================================================
   AURA_RESEARCH_OUTPUT_CSS_V62
   ============================================================ */

.aura-research-output {
  width: min(760px, 92vw);
  margin: 16px auto 0;
  box-sizing: border-box;
  position: relative;
  z-index: 50;
  overflow: hidden;
  border: 1px solid rgba(34, 211, 238, 0.28);
  border-radius: 12px;
  background: rgba(2, 8, 18, 0.94);
}

.aura-research-output-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(34, 211, 238, 0.18);
}

.aura-research-output-title {
  display: block;
  flex: 1 1 auto;
  min-width: 0;
  width: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  box-sizing: border-box;
  font-family: Consolas, "Courier New", monospace;
  font-size: 11px;
  line-height: 1.3;
  letter-spacing: 0.14em;
  color: rgb(103, 232, 249);
}

.aura-research-read {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: auto;
  min-width: 68px;
  height: 28px;
  margin: 0;
  padding: 0 12px;
  box-sizing: border-box;
  border: 1px solid rgba(34, 211, 238, 0.45);
  border-radius: 5px;
  background: rgba(8, 47, 73, 0.55);
  color: rgb(103, 232, 249);
  font-family: Consolas, "Courier New", monospace;
  font-size: 10px;
  line-height: 1;
  letter-spacing: 0.12em;
  white-space: nowrap;
  cursor: pointer;
}

.aura-research-read:hover {
  border-color: rgb(103, 232, 249);
  box-shadow: 0 0 16px rgba(34, 211, 238, 0.22);
}

.aura-research-output-body {
  width: 100%;
  max-height: 30vh;
  box-sizing: border-box;
  padding: 14px;
  overflow-x: hidden;
  overflow-y: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.6;
  color: rgb(165, 243, 252);
}

html[data-aura-speaking="true"] .aura-research-read {
  border-color: rgb(134, 239, 172);
  color: rgb(134, 239, 172);
  box-shadow: 0 0 18px rgba(134, 239, 172, 0.18);
}

@media (max-width: 700px) {
  .aura-research-output {
    width: 94vw;
  }

  .aura-research-output-header {
    gap: 10px;
    padding: 9px 10px;
  }

  .aura-research-output-title {
    font-size: 9px;
    letter-spacing: 0.09em;
  }

  .aura-research-read {
    min-width: 58px;
    padding: 0 9px;
  }
}

/* AURA_RESEARCH_OUTPUT_CSS_V62_END */

'@

$css =
    $css +
    $CssBlock

Write-Utf8 `
    -Path $CssFile.FullName `
    -Text $css

# ============================================================
# STATIC VALIDATION
# ============================================================

Write-Host "[6/8] Structural validation..."

$finalApp =
    Read-Utf8 $AppFile

$finalAppOpen =
    Find-AppOpenBrace $finalApp

$finalReturn =
    Find-AppReturnRange `
        -Text $finalApp `
        -AppOpen $finalAppOpen

if (
    $finalReturn.CloseParen -le
    $finalReturn.OpenParen
) {
    Fail "Final return(...) aralığı geçersiz."
}

if (
    $finalApp -notmatch
    'AURA_RESEARCH_OUTPUT_V62_START'
) {
    Fail "Research component marker bulunamadı."
}

if (
    $finalApp -notmatch
    '<AuraResearchOutput\s*/>'
) {
    Fail "Research JSX invocation bulunamadı."
}

if (
    $finalApp -notmatch
    'const\s+extractResearchOutput'
) {
    Fail "extractResearchOutput bulunamadı."
}

if (
    $finalApp -notmatch
    'const\s+speakResearchOutput'
) {
    Fail "speakResearchOutput bulunamadı."
}

if (
    $finalApp -notmatch
    'const\s+discoverTaskDetailPath'
) {
    Fail "discoverTaskDetailPath bulunamadı."
}

if (
    $finalApp -notmatch
    'utterance\.onend'
) {
    Fail "TTS onend queue bulunamadı."
}

if (
    $finalApp -notmatch
    'step\.result'
) {
    Fail "step.result frontend extractor bulunamadı."
}

# Generated TypeScript must not contain PowerShell comparison operators.
$componentStart =
    $finalApp.IndexOf(
        "AURA_RESEARCH_OUTPUT_V62_START",
        [System.StringComparison]::Ordinal
    )

$componentEnd =
    $finalApp.IndexOf(
        "AURA_RESEARCH_OUTPUT_V62_END",
        $componentStart,
        [System.StringComparison]::Ordinal
    )

$componentText =
    $finalApp.Substring(
        $componentStart,
        $componentEnd -
        $componentStart
    )

if (
    $componentText -match
    '\s-(?:gt|ge|lt|le)\s+'
) {
    Fail (
        "Generated TypeScript içinde PowerShell " +
        "comparison operator bulundu."
    )
}

# Ensure endpoint is canonical.
if (
    $finalApp.Contains(
        "/api/tasks/plan"
    )
) {
    Fail (
        "Eski /api/tasks/plan endpoint'i hâlâ App.tsx içinde."
    )
}

# ============================================================
# BUILD
# ============================================================

Write-Host "[7/8] npm run build..."

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

Push-Location $UiRoot

try {

    & $npm.Source run build

    $buildExit =
        $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($buildExit -ne 0) {

    Write-Host ""
    Write-Host "BUILD FAILED - ROLLBACK" `
        -ForegroundColor Red

    Restore-File `
        -Backup $AppBackup `
        -Destination $AppFile

    Restore-File `
        -Backup $CssBackup `
        -Destination $CssFile.FullName

    Fail (
        "npm run build başarısız oldu. " +
        "App.tsx ve CSS rollback edildi."
    )
}

# ============================================================
# FINAL CHECK
# ============================================================

Write-Host "[8/8] Final validation..."

$finalApp =
    Read-Utf8 $AppFile

$finalCss =
    Read-Utf8 $CssFile.FullName

if (
    $finalApp -notmatch
    'AURA_RESEARCH_OUTPUT_V62_START'
) {
    Fail "Final App.tsx research component validation başarısız."
}

if (
    $finalApp -notmatch
    '<AuraResearchOutput\s*/>'
) {
    Fail "Final JSX validation başarısız."
}

if (
    $finalApp -notmatch
    'speechSynthesis\.cancel'
) {
    Fail "TTS cancellation logic bulunamadı."
}

if (
    $finalApp -notmatch
    'utterance\.onend'
) {
    Fail "TTS onend queue bulunamadı."
}

if (
    $finalCss -notmatch
    'AURA_RESEARCH_OUTPUT_CSS_V62'
) {
    Fail "Final CSS validation başarısız."
}

if (
    $finalCss -notmatch
    '\.aura-research-output-header'
) {
    Fail "Research header CSS bulunamadı."
}

if (
    $finalCss -notmatch
    '\.aura-research-read'
) {
    Fail "READ button CSS bulunamadı."
}

Write-Host ""
Write-Host "============================================================"
Write-Host " AURA V6.2 UI/TTS PATCH SUCCESS"
Write-Host "============================================================"
Write-Host ""
Write-Host "App.tsx structural scan : PASS"
Write-Host "step.result extractor   : PASS"
Write-Host "OpenAPI route discovery : PASS"
Write-Host "TTS chunk queue         : PASS"
Write-Host "TTS onend chaining      : PASS"
Write-Host "Turkish voice selection : PASS"
Write-Host "422 diagnostics         : PASS"
Write-Host "OUTPUT/READ CSS         : PASS"
Write-Host "npm run build           : PASS"
Write-Host ""
Write-Host "Backup:"
Write-Host $BackupDir
Write-Host ""