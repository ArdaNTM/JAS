from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .contracts import ResearchToolSpec
from .engine import LearningEngine
from .models import LearningPolicy
from .planner import ResearchPlanner
from .scheduler import ContinuousLearningScheduler

from ..knowledge.graph import KnowledgeGraph
from ..knowledge.repository import KnowledgeRepository
from ..knowledge.service import KnowledgeService
from ..knowledge.store import KnowledgeStore

from ..memory.embeddings import OllamaEmbeddingProvider
from ..memory.semantic_store import SemanticMemoryStore

from ..models.setup_llm import build_llm_router


@dataclass(slots=True)
class LearningRuntimeConfig:
    knowledge_root: Path
    postgres_url: str
    qdrant_url: str
    embedding_model: str
    ollama_url: str
    qdrant_collection: str

    interval_seconds: float
    max_sources: int
    max_steps: int
    max_iterations: int
    max_runtime_seconds: float

    checkpoint_root: Path

    @classmethod
    def from_env(
        cls,
    ) -> "LearningRuntimeConfig":
        return cls(
            knowledge_root=Path(
                os.getenv(
                    "AURA_KNOWLEDGE_ROOT",
                    r"D:\AURA\Knowledge",
                )
            ),
            postgres_url=os.getenv(
                "AURA_POSTGRES_URL",
                (
                    "postgresql+asyncpg://"
                    "postgres:postgres@"
                    "127.0.0.1:5432/aura"
                ),
            ),
            qdrant_url=os.getenv(
                "AURA_QDRANT_URL",
                "http://127.0.0.1:6333",
            ),
            embedding_model=os.getenv(
                "AURA_EMBEDDING_MODEL",
                "bge-m3",
            ),
            ollama_url=os.getenv(
                "AURA_OLLAMA_URL",
                "http://127.0.0.1:11434",
            ),
            qdrant_collection=os.getenv(
                "AURA_QDRANT_COLLECTION",
                "aura_memory",
            ),
            interval_seconds=float(
                os.getenv(
                    "AURA_LEARNING_INTERVAL_SECONDS",
                    "300",
                )
            ),
            max_sources=int(
                os.getenv(
                    "AURA_LEARNING_MAX_SOURCES",
                    "8",
                )
            ),
            max_steps=int(
                os.getenv(
                    "AURA_LEARNING_MAX_STEPS",
                    "16",
                )
            ),
            max_iterations=int(
                os.getenv(
                    "AURA_LEARNING_MAX_ITERATIONS",
                    "4",
                )
            ),
            max_runtime_seconds=float(
                os.getenv(
                    "AURA_LEARNING_MAX_RUNTIME_SECONDS",
                    "180",
                )
            ),
            checkpoint_root=Path(
                os.getenv(
                    "AURA_LEARNING_CHECKPOINT_ROOT",
                    r"D:\AURA\Knowledge\checkpoints",
                )
            ),
        )


def create_learning_runtime(
    *,
    gateway,
    session_factory,
    search_capability_id: str,
    search_operation_id: str,
    search_tool_name: str,
    fetch_capability_id: str,
    fetch_operation_id: str,
    fetch_tool_name: str,
    config: LearningRuntimeConfig | None = None,
    objectives=None,
):
    cfg = (
        config
        or LearningRuntimeConfig.from_env()
    )

    cfg.knowledge_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    cfg.checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    knowledge = KnowledgeService(
        store=KnowledgeStore(
            cfg.knowledge_root
        ),
        repository=KnowledgeRepository(
            session_factory
        ),
        graph=KnowledgeGraph(),
    )

    embeddings = OllamaEmbeddingProvider(
        model=cfg.embedding_model,
        base_url=cfg.ollama_url,
    )

    memory = SemanticMemoryStore(
        embeddings=embeddings,
        qdrant_url=cfg.qdrant_url,
        collection=cfg.qdrant_collection,
    )

    policy = LearningPolicy(
        interval_seconds=(
            cfg.interval_seconds
        ),
        max_sources=cfg.max_sources,
        max_steps=cfg.max_steps,
        max_runtime_seconds=(
            cfg.max_runtime_seconds
        ),
    )

    engine = LearningEngine(
        gateway=gateway,
        knowledge=knowledge,
        memory=memory,
        planner=ResearchPlanner(),
        policy=policy,
        tool_spec=ResearchToolSpec(
            search_capability_id=(
                search_capability_id
            ),
            search_operation_id=(
                search_operation_id
            ),
            search_tool_name=(
                search_tool_name
            ),
            fetch_capability_id=(
                fetch_capability_id
            ),
            fetch_operation_id=(
                fetch_operation_id
            ),
            fetch_tool_name=(
                fetch_tool_name
            ),
        ),
        llm=build_llm_router(),
        checkpoint_root=(
            cfg.checkpoint_root
        ),
    )

    scheduler = ContinuousLearningScheduler(
        engine=engine,
        objectives=list(
            objectives or []
        ),
    )

    return engine, scheduler
