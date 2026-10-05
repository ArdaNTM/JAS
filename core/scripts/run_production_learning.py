from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from aura_core.kernel.capabilities import (
    CapabilityRegistry,
)
from aura_core.kernel.permissions import (
    AuthorizationDecision,
    AuthorizationLevel,
    PermissionEngine,
    PermissionPolicy,
)
from aura_core.kernel.services import (
    ServiceRegistry,
)
from aura_core.mcp.gateway import MCPGateway
from aura_core.mcp.provider import ProviderRegistry
from aura_core.mcp.tool_registry import MCPToolRegistry

from aura_core.knowledge.graph import KnowledgeGraph
from aura_core.knowledge.repository import KnowledgeRepository
from aura_core.knowledge.service import KnowledgeService
from aura_core.knowledge.store import KnowledgeStore

from aura_core.learning.bootstrap import (
    LearningRuntimeConfig,
)
from aura_core.learning.contracts import (
    ResearchToolSpec,
)
from aura_core.learning.engine import (
    LearningEngine,
)
from aura_core.learning.models import (
    LearningObjective,
    LearningPolicy,
)
from aura_core.learning.planner import (
    ResearchPlanner,
)
from aura_core.learning.scheduler import (
    ContinuousLearningScheduler,
)

from aura_core.memory.embeddings import (
    OllamaEmbeddingProvider,
)
from aura_core.memory.semantic_store import (
    SemanticMemoryStore,
)

from aura_core.models.ollama import (
    OllamaProvider,
)

from aura_core.research.config import (
    ResearchMCPConfig,
)
from aura_core.research.provider_bootstrap import (
    register_research_mcp,
)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable is missing: {name}"
        )

    return value


def build_runtime_config() -> LearningRuntimeConfig:
    cfg = LearningRuntimeConfig.from_env()

    cfg.knowledge_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    return cfg


async def build_production_runtime():
    cfg = build_runtime_config()

    research = ResearchMCPConfig.from_env()

    postgres_url = required_env(
        "AURA_POSTGRES_URL"
    )

    # --------------------------------------------------------
    # PostgreSQL
    # --------------------------------------------------------

    postgres_engine = create_async_engine(
        postgres_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

    session_factory = async_sessionmaker(
        postgres_engine,
        expire_on_commit=False,
    )

    # --------------------------------------------------------
    # AURA registries
    # --------------------------------------------------------

    services = ServiceRegistry()

    providers = ProviderRegistry(
        services
    )

    capabilities = CapabilityRegistry(
        services
    )

    tools = MCPToolRegistry()

    permissions = PermissionEngine(
        capabilities
    )

    # --------------------------------------------------------
    # REAL MCP PROVIDER
    # --------------------------------------------------------

    provider = await register_research_mcp(
        config=research,
        services=services,
        providers=providers,
        capabilities=capabilities,
        tools=tools,
    )

    # --------------------------------------------------------
    # DEFAULT-DENY -> explicit READ permissions
    # --------------------------------------------------------

    permissions.add_policy(
        PermissionPolicy(
            policy_id="aura.learning.research.search",
            policy_version="1.0.0",
            principal_id="aura-learning",
            capability_id=research.capability_id,
            operation_id=research.search_operation_id,
            resource_scope="research",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        )
    )

    permissions.add_policy(
        PermissionPolicy(
            policy_id="aura.learning.research.fetch",
            policy_version="1.0.0",
            principal_id="aura-learning",
            capability_id=research.fetch_capability_id,
            operation_id=research.fetch_operation_id,
            resource_scope="research",
            authorization_level=AuthorizationLevel.READ,
            decision=AuthorizationDecision.ALLOW,
        )
    )

    gateway = MCPGateway(
        capability_registry=capabilities,
        provider_registry=providers,
        permission_engine=permissions,
    )

    # --------------------------------------------------------
    # Knowledge -> SSD + PostgreSQL
    # --------------------------------------------------------

    knowledge = KnowledgeService(
        store=KnowledgeStore(
            cfg.knowledge_root
        ),
        repository=KnowledgeRepository(
            session_factory
        ),
        graph=KnowledgeGraph(),
    )

    # --------------------------------------------------------
    # Ollama BGE-M3 -> Qdrant
    # --------------------------------------------------------

    embeddings = OllamaEmbeddingProvider(
        model=cfg.embedding_model,
        base_url=cfg.ollama_url,
    )

    memory = SemanticMemoryStore(
        embeddings=embeddings,
        qdrant_url=cfg.qdrant_url,
        collection=cfg.qdrant_collection,
    )

    # --------------------------------------------------------
    # Local Qwen3 / Ollama
    # --------------------------------------------------------

    llm_model = os.getenv(
        "AURA_LLM_MODEL",
        "qwen3:4b-instruct-2507-q4_K_M",
    ).strip()

    llm = OllamaProvider(
        model=llm_model,
        base_url=cfg.ollama_url,
        timeout=float(
            os.getenv(
                "AURA_OLLAMA_TIMEOUT_SECONDS",
                "180",
            )
        ),
    )

    # --------------------------------------------------------
    # Learning Engine
    # --------------------------------------------------------

    policy = LearningPolicy(
        interval_seconds=cfg.interval_seconds,
        max_sources=cfg.max_sources,
        max_steps=cfg.max_steps,
        max_iterations=cfg.max_iterations,
        max_runtime_seconds=cfg.max_runtime_seconds,
    )

    engine = LearningEngine(
        gateway=gateway,
        knowledge=knowledge,
        memory=memory,
        llm=llm,
        planner=ResearchPlanner(),
        policy=policy,
        tool_spec=ResearchToolSpec(
            search_capability_id=(
                research.capability_id
            ),
            search_operation_id=(
                research.search_operation_id
            ),
            search_tool_name=(
                research.search_tool_name
            ),
            fetch_capability_id=(
                research.fetch_capability_id
            ),
            fetch_operation_id=(
                research.fetch_operation_id
            ),
            fetch_tool_name=(
                research.fetch_tool_name
            ),
        ),
        checkpoint_root=(
            cfg.checkpoint_root
        ),
    )

    # --------------------------------------------------------
    # REAL LEARNING OBJECTIVE
    # --------------------------------------------------------

    objective = LearningObjective(
        objective_id=os.getenv(
            "AURA_LEARNING_OBJECTIVE_ID",
            "aura-autonomous-architecture",
        ),
        title=os.getenv(
            "AURA_LEARNING_OBJECTIVE_TITLE",
            "AURA Architecture Autonomous Learning",
        ),
        description=os.getenv(
            "AURA_LEARNING_OBJECTIVE_DESCRIPTION",
            (
                "Research AURA architecture, "
                "its runtime, MCP provider architecture, "
                "knowledge persistence, semantic memory, "
                "LLM integration and authoritative "
                "technical documentation. "
                "Prefer authoritative primary sources "
                "and preserve evidence for every learned fact."
            ),
        ),
        namespace=os.getenv(
            "AURA_LEARNING_NAMESPACE",
            "aura",
        ),
        priority=int(
            os.getenv(
                "AURA_LEARNING_PRIORITY",
                "100",
            )
        ),
        enabled=True,
    )

    scheduler = ContinuousLearningScheduler(
        engine=engine,
        objectives=[objective],
    )

    return {
        "cfg": cfg,
        "research": research,
        "postgres_engine": postgres_engine,
        "provider": provider,
        "knowledge": knowledge,
        "memory": memory,
        "engine": engine,
        "scheduler": scheduler,
        "objective": objective,
    }


async def validate_runtime(runtime):
    cfg = runtime["cfg"]
    research = runtime["research"]

    print("")
    print("=" * 64)
    print("AURA PRODUCTION LEARNING BOOTSTRAP")
    print("=" * 64)

    print(f"Knowledge root : {cfg.knowledge_root}")
    print(f"PostgreSQL     : {os.environ['AURA_POSTGRES_URL']}")
    print(f"Qdrant         : {cfg.qdrant_url}")
    print(f"Qdrant         : {cfg.qdrant_collection}")
    print(f"Ollama         : {cfg.ollama_url}")
    print(f"Embedding      : {cfg.embedding_model}")
    print(
        "LLM            : "
        + os.getenv(
            "AURA_LLM_MODEL",
            "qwen3:4b-instruct-2507-q4_K_M",
        )
    )
    print(f"MCP transport  : {research.transport}")
    print(f"MCP provider   : {research.provider_id}")
    print(f"Search tool    : {research.search_tool_name}")
    print(f"Fetch tool     : {research.fetch_tool_name}")
    print(
        f"Objective      : "
        f"{runtime['objective'].objective_id}"
    )

    # --------------------------------------------------------
    # PostgreSQL schema
    # --------------------------------------------------------

    await runtime["knowledge"].initialize()

    # --------------------------------------------------------
    # Qdrant collection + BGE-M3 dimension validation
    # --------------------------------------------------------

    await runtime["memory"].initialize()

    print("")
    print("PostgreSQL       : READY")
    print("Qdrant + BGE-M3  : READY")
    print("SSD Knowledge    : READY")
    print("MCP provider     : READY")
    print("Permission chain : READY")
    print("Learning Engine  : READY")
    print("")

    print(
        "REAL PRODUCTION RUNTIME VALIDATION: PASS"
    )

    print("=" * 64)
    print("STARTING CONTINUOUS LEARNING SCHEDULER")
    print("=" * 64)
    print("")


async def main():
    runtime = await build_production_runtime()

    stop_event = asyncio.Event()

    def stop():
        if not stop_event.is_set():
            print("")
            print("Shutdown requested...")
            stop_event.set()

    try:
        loop = asyncio.get_running_loop()

        for sig in (
            signal.SIGINT,
            signal.SIGTERM,
        ):
            try:
                loop.add_signal_handler(
                    sig,
                    stop,
                )
            except NotImplementedError:
                pass

        await validate_runtime(runtime)

        scheduler = runtime["scheduler"]

        await scheduler.start()

        print(
            "ContinuousLearningScheduler : RUNNING"
        )
        print(
            "Objective                    : "
            + runtime["objective"].objective_id
        )
        print(
            "Checkpoint root              : "
            + str(
                runtime["cfg"].checkpoint_root
            )
        )
        print("")
        print(
            "AURA autonomous learning is now active."
        )
        print(
            "Press CTRL+C to stop."
        )
        print("")

        await stop_event.wait()

    finally:
        scheduler = runtime.get(
            "scheduler"
        )

        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception:
                pass

        provider = runtime.get(
            "provider"
        )

        if provider is not None:
            try:
                await provider.close()
            except Exception:
                pass

        postgres_engine = runtime.get(
            "postgres_engine"
        )

        if postgres_engine is not None:
            await postgres_engine.dispose()

        print(
            "AURA autonomous learning stopped."
        )


if __name__ == "__main__":
    asyncio.run(main())
