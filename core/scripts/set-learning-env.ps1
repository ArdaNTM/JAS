$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "D:\AURA\JAS\core"

$env:AURA_RESEARCH_MCP_TRANSPORT = "stdio"
$env:AURA_RESEARCH_MCP_PROVIDER_ID = "aura-research-local"
$env:AURA_RESEARCH_MCP_SERVICE_NAME = "aura-local-research"
$env:AURA_RESEARCH_MCP_SERVICE_VERSION = "1.0.0"

$env:AURA_RESEARCH_MCP_CAPABILITY_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_OPERATION_ID = "internet.search"
$env:AURA_RESEARCH_MCP_SEARCH_TOOL = "search"

$env:AURA_RESEARCH_MCP_FETCH_CAPABILITY_ID = "internet.search"
$env:AURA_RESEARCH_MCP_FETCH_OPERATION_ID = "internet.fetch"
$env:AURA_RESEARCH_MCP_FETCH_TOOL = "fetch"

$env:AURA_RESEARCH_MCP_COMMAND = "uv"
$env:AURA_RESEARCH_MCP_ARGS = "run|python|D:\AURA\JAS\core\scripts\local_research_mcp.py"

$env:AURA_KNOWLEDGE_ROOT = "D:\AURA\Knowledge"

$env:AURA_POSTGRES_URL = "postgresql+asyncpg://aura:aura@127.0.0.1:5432/aura"

$env:AURA_QDRANT_URL = "http://127.0.0.1:6333"
$env:AURA_QDRANT_COLLECTION = "aura_memory"

$env:AURA_OLLAMA_URL = "http://127.0.0.1:11434"
$env:AURA_EMBEDDING_MODEL = "bge-m3:latest"
$env:AURA_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
$env:AURA_LLM_MODEL = "qwen3:4b-instruct-2507-q4_K_M"

$env:AURA_LEARNING_INTERVAL_SECONDS = "300"
$env:AURA_LEARNING_MAX_SOURCES = "8"
$env:AURA_LEARNING_MAX_STEPS = "16"
$env:AURA_LEARNING_MAX_ITERATIONS = "4"
$env:AURA_LEARNING_MAX_RUNTIME_SECONDS = "180"

Write-Host "AURA learning environment loaded."
$env:AURA_EVENT_STREAM_TOKEN = "aura-dev-event-stream-token-7f3c9a2e6b1d4f8c0e5a9b7d3c1f6e2a"
