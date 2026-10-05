$Root = "D:\AURA\Knowledge"

$Directories = @(
    "$Root\raw",
    "$Root\normalized",
    "$Root\sources",
    "$Root\knowledge",
    "$Root\embeddings",
    "$Root\indexes",
    "$Root\snapshots",
    "$Root\manifests",
    "$Root\audit",
    "$Root\logs",
    "$Root\checkpoints"
)

foreach ($Directory in $Directories) {
    New-Item `
        -ItemType Directory `
        -Force `
        -Path $Directory `
        | Out-Null
}

Write-Host "AURA Knowledge SSD initialized:"
Write-Host $Root
