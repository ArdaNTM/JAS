from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from aura_core.kernel.permissions import (
    AuthorizationDecision,
    RiskLevel,
)
from aura_core.mcp.gateway import MCPGatewayRequest

from ..knowledge.models import (
    KnowledgeEvidence,
    KnowledgeFact,
    KnowledgeRecord,
    KnowledgeSource,
)
from ..knowledge.service import KnowledgeService
from ..memory.models import MemoryRecord
from ..memory.semantic_store import SemanticMemoryStore
from ..models.multi_router import LLMProvider

from .admission import (
    AdmissionController,
    AdmissionDecision,
)
from .contracts import ResearchToolSpec
from .episodic import EpisodicMemory
from .models import (
    LearningObjective,
    LearningPolicy,
    LearningRun,
    LearningRuntimeState,
    LearningStatus,
)
from .planner import ResearchPlanner
from .reflection import (
    ReflectionInput,
    ReflectionSynthesizer,
    reflection_memory_record,
)


class LearningEngine:
    def __init__(
        self,
        *,
        gateway: Any,
        knowledge: KnowledgeService,
        memory: SemanticMemoryStore,
        tool_spec: ResearchToolSpec,
        planner: ResearchPlanner | None = None,
        policy: LearningPolicy | None = None,
        llm: LLMProvider | None = None,
        checkpoint_root: Path | None = None,
    ) -> None:
        self.gateway = gateway
        self.knowledge = knowledge
        self.memory = memory
        self.tool_spec = tool_spec
        self.tool_spec.validate()
        self.planner = planner or ResearchPlanner()
        self.policy = policy or LearningPolicy()
        self.llm = llm

        self.checkpoint_root = (
            checkpoint_root
            or Path(
                r"D:\AURA\Knowledge\checkpoints"
            )
        )

        self.checkpoint_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.admission = AdmissionController()
        self.runtime_states: dict[
            str,
            LearningRuntimeState,
        ] = {}

        self.episodic_memory = EpisodicMemory(
            memory
        )

        self.reflection = (
            ReflectionSynthesizer(
                llm=llm
            )
            if llm is not None
            else None
        )

    def _run_id(
        self,
        objective: LearningObjective,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"aura-learning-run:{objective.objective_id}",
            )
        )

    def runtime_state(
        self,
        run_id: str,
    ) -> LearningRuntimeState:
        try:
            return self.runtime_states[run_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown learning run: {run_id}"
            ) from exc

    async def _reflect(
        self,
        *,
        objective: LearningObjective,
        run: LearningRun,
        facts: list[str],
    ) -> None:
        if self.reflection is None:
            return

        episode = ReflectionInput(
            run_id=run.run_id,
            objective_id=objective.objective_id,
            objective_title=(
                objective.title
                or objective.description
            ),
            objective_description=(
                objective.description
            ),
            status=run.status.value,
            steps=run.steps,
            sources=run.sources,
            records=run.records,
            error=run.error,
            facts=tuple(facts),
        )

        try:
            result = await self.reflection.reflect(
                episode
            )

            await self.episodic_memory.remember(
                reflection_memory_record(
                    result,
                    objective_id=objective.objective_id,
                )
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            # Reflection is post-run learning. A reflection failure
            # must never invalidate already persisted knowledge.
            pass

    async def _recall_reflections(
        self,
        objective: LearningObjective,
    ) -> list[str]:
        try:
            entries = await self.episodic_memory.recall(
                objective.description
            )

            return [
                entry.record.content
                for entry in entries
            ]

        except Exception:
            return []

    async def _extract_facts(
        self,
        *,
        source: KnowledgeSource,
        content: str,
    ) -> list[KnowledgeFact]:
        if self.llm is None:
            return []

        prompt = f"""
Extract only directly supported facts from the source.
Return ONLY JSON:
{{"facts":[{{"subject":"string","predicate":"string","object":"string","confidence":0.0,"quote":"exact source quote"}}]}}

Do not invent facts.
Do not infer unsupported facts.
quote must occur verbatim in the source.

SOURCE:
{content}
""".strip()

        raw = await self.llm.generate(
            prompt,
            options={
                "temperature": 0,
                "format": "json",
            },
        )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []

        values = (
            data.get("facts", [])
            if isinstance(data, dict)
            else []
        )

        facts: list[KnowledgeFact] = []

        for item in values:
            if not isinstance(item, dict):
                continue

            subject = str(
                item.get("subject", "")
            ).strip()
            predicate = str(
                item.get("predicate", "")
            ).strip()
            object_value = str(
                item.get("object", "")
            ).strip()
            quote = str(
                item.get("quote", "")
            ).strip()

            if not all(
                (
                    subject,
                    predicate,
                    object_value,
                    quote,
                )
            ):
                continue

            if quote not in content:
                continue

            try:
                confidence = float(
                    item.get(
                        "confidence",
                        0.5,
                    )
                )
            except (TypeError, ValueError):
                confidence = 0.5

            confidence = max(
                0.0,
                min(1.0, confidence),
            )

            fact_id = str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        "aura-fact:"
                        f"{subject}|{predicate}|"
                        f"{object_value}"
                    ),
                )
            )

            facts.append(
                KnowledgeFact(
                    fact_id=fact_id,
                    subject=subject,
                    predicate=predicate,
                    object=object_value,
                    confidence=confidence,
                    evidence=[
                        KnowledgeEvidence(
                            source_id=source.source_id,
                            locator=source.uri,
                            quote=quote,
                            confidence=confidence,
                        )
                    ],
                )
            )

        return facts

    async def run(
        self,
        objective: LearningObjective,
        *,
        principal_id: str = "aura-learning",
        resource_scope: str = "research",
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> LearningRun:
        run_id = self._run_id(objective)

        run = LearningRun(
            run_id=run_id,
            objective_id=objective.objective_id,
            status=LearningStatus.RUNNING,
        )

        runtime_state = LearningRuntimeState(
            run_id=run_id,
            objective_id=objective.objective_id,
        )

        runtime_state.budget.units = (
            self.policy.max_budget_units
        )

        self.runtime_states[run_id] = runtime_state
        runtime_state.start()

        facts_for_reflection: list[str] = []

        try:
            await self.knowledge.initialize()
            await self.episodic_memory.initialize()

            previous_reflections = (
                await self._recall_reflections(
                    objective
                )
            )

            queries = self.planner.plan_queries(
                objective.description,
                self.policy.max_steps,
            )

            if previous_reflections:
                query_context = " ".join(
                    previous_reflections[:3]
                )

                if query_context:
                    extra = self.planner.plan_queries(
                        (
                            f"{objective.description}\n"
                            f"Previous lessons:\n"
                            f"{query_context}"
                        ),
                        max(
                            1,
                            self.policy.max_steps
                            - len(queries),
                        ),
                    )

                    queries = list(
                        dict.fromkeys(
                            queries + extra
                        )
                    )

            for query in queries:
                if run.steps >= self.policy.max_steps:
                    break

                if (
                    time.monotonic()
                    >= time.monotonic()
                    + self.policy.max_runtime_seconds
                ):
                    break

                if not runtime_state.budget.can_spend():
                    break

                runtime_state.budget.spend()
                runtime_state.budget.queries += 1

                request = MCPGatewayRequest(
                    request_id=(
                        f"learning:{run_id}:search:"
                        f"{runtime_state.steps}"
                    ),
                    principal_id=principal_id,
                    capability_id=(
                        self.tool_spec.search_capability_id
                    ),
                    operation_id=(
                        self.tool_spec.search_operation_id
                    ),
                    resource_scope=resource_scope,
                    risk_level=risk_level,
                    tool_name=(
                        self.tool_spec.search_tool_name
                    ),
                    arguments={"query": query},
                    session_id=f"learning:{run_id}",
                    task_id=run_id,
                )

                response = await self.gateway.invoke(
                    request
                )

                if (
                    getattr(
                        response,
                        "decision",
                        AuthorizationDecision.ALLOW,
                    )
                    is not AuthorizationDecision.ALLOW
                ):
                    raise PermissionError(
                        getattr(
                            response,
                            "reason",
                            "Learning research denied",
                        )
                    )

                run.steps += 1
                runtime_state.consume_step()

                payload = getattr(
                    response,
                    "result",
                    response,
                )

                if isinstance(payload, dict):
                    items = payload.get(
                        "results",
                        payload.get(
                            "items",
                            [],
                        ),
                    )
                elif isinstance(payload, list):
                    items = payload
                else:
                    items = []

                for item in items:
                    if run.sources >= self.policy.max_sources:
                        break

                    uri = str(
                        item.get(
                            "url",
                            item.get(
                                "uri",
                                item.get(
                                    "link",
                                    "",
                                ),
                            ),
                        )
                    )

                    if not uri:
                        continue

                    if not runtime_state.budget.can_spend():
                        break

                    runtime_state.budget.spend()
                    runtime_state.budget.fetches += 1

                    fetch_request = MCPGatewayRequest(
                        request_id=(
                            f"learning:{run_id}:fetch:"
                            f"{run.sources}"
                        ),
                        principal_id=principal_id,
                        capability_id=(
                            self.tool_spec.fetch_capability_id
                        ),
                        operation_id=(
                            self.tool_spec.fetch_operation_id
                        ),
                        resource_scope=resource_scope,
                        risk_level=risk_level,
                        tool_name=(
                            self.tool_spec.fetch_tool_name
                        ),
                        arguments={"url": uri},
                        session_id=f"learning:{run_id}",
                        task_id=run_id,
                    )

                    fetched_response = (
                        await self.gateway.invoke(
                            fetch_request
                        )
                    )

                    if (
                        getattr(
                            fetched_response,
                            "decision",
                            AuthorizationDecision.ALLOW,
                        )
                        is not AuthorizationDecision.ALLOW
                    ):
                        continue

                    fetched = getattr(
                        fetched_response,
                        "result",
                        fetched_response,
                    )

                    if isinstance(fetched, str):
                        content = fetched
                    elif isinstance(fetched, dict):
                        content = str(
                            fetched.get(
                                "content",
                                fetched.get(
                                    "text",
                                    fetched.get(
                                        "body",
                                        "",
                                    ),
                                ),
                            )
                        )
                    else:
                        content = ""

                    content = content.strip()

                    if not content:
                        continue

                    admission = (
                        self.admission.evaluate(
                            content
                        )
                    )

                    if (
                        admission.decision
                        is not AdmissionDecision.ACCEPT
                    ):
                        continue

                    if (
                        runtime_state.budget.new_records
                        >= self.policy.max_new_records
                    ):
                        break

                    title = str(
                        item.get(
                            "title",
                            uri,
                        )
                    )

                    source_id = str(
                        uuid5(
                            NAMESPACE_URL,
                            f"aura-source:{uri}",
                        )
                    )

                    source = KnowledgeSource(
                        source_id=source_id,
                        uri=uri,
                        source_type="mcp",
                        title=title,
                        metadata={
                            "objective_id": (
                                objective.objective_id
                            ),
                            "learning_run_id": run_id,
                            "content_hash": (
                                admission.content_hash
                            ),
                        },
                    )

                    self.admission.commit(admission)

                    await self.knowledge.ingest_source(
                        source,
                        content.encode("utf-8"),
                    )

                    extracted = await self._extract_facts(
                        source=source,
                        content=content,
                    )

                    for fact in extracted:
                        await self.knowledge.ingest_fact(
                            fact
                        )

                        facts_for_reflection.append(
                            (
                                f"{fact.subject} "
                                f"{fact.predicate} "
                                f"{fact.object}"
                            )
                        )

                    record = KnowledgeRecord.create(
                        namespace="research",
                        content=content,
                        source_id=source.source_id,
                        kind="research",
                        title=title,
                        confidence=0.5,
                        metadata={
                            "objective_id": (
                                objective.objective_id
                            ),
                            "learning_run_id": run_id,
                            "content_hash": (
                                admission.content_hash
                            ),
                        },
                    )

                    await self.knowledge.ingest_record(
                        record
                    )

                    await self.memory.put(
                        MemoryRecord(
                            record_id=record.record_id,
                            namespace="research",
                            content=content,
                            source=uri,
                            metadata={
                                "objective_id": (
                                    objective.objective_id
                                ),
                                "learning_run_id": run_id,
                                "content_hash": (
                                    admission.content_hash
                                ),
                            },
                            created_at=record.created_at,
                        )
                    )

                    run.sources += 1
                    run.records += 1
                    runtime_state.consume_source()
                    runtime_state.consume_record()
                    runtime_state.budget.new_records += 1

            run.status = LearningStatus.COMPLETED
            runtime_state.succeed()

            await self._reflect(
                objective=objective,
                run=run,
                facts=facts_for_reflection,
            )

            return run

        except asyncio.CancelledError:
            run.status = LearningStatus.STOPPED
            runtime_state.stop()

            await self._reflect(
                objective=objective,
                run=run,
                facts=facts_for_reflection,
            )

            raise

        except Exception as exc:
            run.status = LearningStatus.FAILED
            run.error = (
                f"{type(exc).__name__}: {exc}"
            )

            runtime_state.fail(
                run.error,
                cooldown_seconds=(
                    self.policy.cooldown_seconds
                ),
                max_consecutive_failures=(
                    self.policy.max_consecutive_failures
                ),
            )

            await self._reflect(
                objective=objective,
                run=run,
                facts=facts_for_reflection,
            )

            return run
