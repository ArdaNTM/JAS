$ErrorActionPreference = "Stop"

ollama --version

Write-Host "Pulling BGE-M3..."
ollama pull bge-m3

Write-Host "BGE-M3 ready."
