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

from .contracts import ResearchToolSpec
from .models import (
    LearningObjective,
    LearningPolicy,
    LearningRun,
    LearningStatus,
)
from .planner import ResearchPlanner


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

    # --------------------------------------------------------
    # Deterministic IDs
    # --------------------------------------------------------

    @staticmethod
    def _source_id(uri: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"aura-source:{uri.strip()}",
            )
        )

    @staticmethod
    def _fact_id(
        subject: str,
        predicate: str,
        object_value: str,
    ) -> str:
        digest = hashlib.sha256(
            "|".join(
                (
                    subject.strip(),
                    predicate.strip(),
                    object_value.strip(),
                )
            ).encode("utf-8")
        ).hexdigest()

        return str(
            uuid5(
                NAMESPACE_URL,
                f"aura-fact:{digest}",
            )
        )

    @staticmethod
    def _run_id(
        objective: LearningObjective,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                f"aura-learning-run:{objective.objective_id}",
            )
        )

    # --------------------------------------------------------
    # Persistent checkpoint
    # --------------------------------------------------------

    def _checkpoint_path(
        self,
        objective_id: str,
    ) -> Path:
        digest = hashlib.sha256(
            objective_id.encode("utf-8")
        ).hexdigest()

        return (
            self.checkpoint_root
            / f"{digest}.json"
        )

    def _load_checkpoint(
        self,
        objective_id: str,
    ) -> dict[str, Any]:
        path = self._checkpoint_path(
            objective_id
        )

        if not path.exists():
            return {
                "objective_id": objective_id,
                "queries": [],
                "sources": [],
                "records": [],
                "facts": [],
                "completed": False,
            }

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(data, dict):
                raise ValueError

            return data
        except Exception:
            return {
                "objective_id": objective_id,
                "queries": [],
                "sources": [],
                "records": [],
                "facts": [],
                "completed": False,
            }

    def _save_checkpoint(
        self,
        objective_id: str,
        state: dict[str, Any],
    ) -> None:
        path = self._checkpoint_path(
            objective_id
        )

        tmp = path.with_suffix(
            ".tmp"
        )

        tmp.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        tmp.replace(path)

    # --------------------------------------------------------
    # MCP
    # --------------------------------------------------------

    async def _invoke(
        self,
        *,
        principal_id: str,
        capability_id: str,
        operation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        resource_scope: str,
        risk_level: RiskLevel,
        task_id: str,
    ) -> Any:
        request = MCPGatewayRequest(
            request_id=(
                f"learning:{task_id}:"
                f"{capability_id}:"
                f"{operation_id}"
            ),
            principal_id=principal_id,
            capability_id=capability_id,
            operation_id=operation_id,
            resource_scope=resource_scope,
            risk_level=risk_level,
            tool_name=tool_name,

            # IMPORTANT:
            # MCPGatewayRequest uses "arguments".
            # Never use "args".
            arguments=arguments,

            session_id=f"learning:{task_id}",
            task_id=task_id,
        )

        return await self.gateway.invoke(
            request
        )

    @staticmethod
    def _payload(
        response: Any,
    ) -> Any:
        if hasattr(response, "result"):
            decision = getattr(
                response,
                "decision",
                None,
            )

            if (
                decision is not None
                and decision
                is not AuthorizationDecision.ALLOW
            ):
                reason = getattr(
                    response,
                    "reason",
                    "MCP invocation denied",
                )

                raise PermissionError(
                    reason
                )

            response = response.result

        structured = getattr(
            response,
            "structuredContent",
            None,
        )

        if structured is not None:
            return structured

        content = getattr(
            response,
            "content",
            None,
        )

        if content:
            for item in content:
                text = getattr(
                    item,
                    "text",
                    None,
                )

                if not text:
                    continue

                try:
                    return json.loads(text)
                except (TypeError, ValueError):
                    return text

        return response

    # --------------------------------------------------------
    # Result normalization
    # --------------------------------------------------------

    @staticmethod
    def _search_items(
        payload: Any,
    ) -> list[Any]:
        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            for key in (
                "results",
                "items",
                "hits",
                "data",
            ):
                value = payload.get(key)

                if isinstance(value, list):
                    return value

        return []

    @staticmethod
    def _candidate(
        item: Any,
    ) -> tuple[str, str]:
        if not isinstance(item, dict):
            return "", ""

        uri = (
            item.get("url")
            or item.get("uri")
            or item.get("link")
            or item.get("href")
            or ""
        )

        title = (
            item.get("title")
            or item.get("name")
            or uri
        )

        return str(uri), str(title)

    @staticmethod
    def _fetch_text(
        payload: Any,
    ) -> str:
        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in (
                "content",
                "text",
                "body",
                "data",
                "result",
            ):
                value = payload.get(key)

                if isinstance(value, str):
                    return value

                if isinstance(value, dict):
                    nested = LearningEngine._fetch_text(
                        value
                    )

                    if nested:
                        return nested

                if isinstance(value, list):
                    parts = []

                    for item in value:
                        if isinstance(item, dict):
                            text = item.get(
                                "text"
                            )

                            if isinstance(
                                text,
                                str,
                            ):
                                parts.append(
                                    text
                                )
                        elif isinstance(
                            item,
                            str,
                        ):
                            parts.append(item)

                    if parts:
                        return "\n".join(parts)

        return ""

    # --------------------------------------------------------
    # LLM fact extraction
    # --------------------------------------------------------

    async def _extract_facts(
        self,
        *,
        source: KnowledgeSource,
        content: str,
    ) -> list[KnowledgeFact]:
        if self.llm is None:
            return []

        prompt = f"""
You are AURA's deterministic knowledge extraction component.

Extract ONLY facts directly supported by the supplied source.

Return ONLY valid JSON.

Schema:
{{
  "facts": [
    {{
      "subject": "string",
      "predicate": "string",
      "object": "string",
      "confidence": 0.0,
      "quote": "exact source quote"
    }}
  ]
}}

Rules:
- Do not invent facts.
- Do not infer facts not supported by the text.
- quote MUST occur verbatim in the source.
- confidence must be between 0 and 1.
- If no reliable facts exist return {{"facts":[]}}.

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

        if not isinstance(values, list):
            return []

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
            except (
                TypeError,
                ValueError,
            ):
                confidence = 0.5

            confidence = max(
                0.0,
                min(1.0, confidence),
            )

            facts.append(
                KnowledgeFact(
                    fact_id=self._fact_id(
                        subject,
                        predicate,
                        object_value,
                    ),
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

        unique: dict[str, KnowledgeFact] = {
            fact.fact_id: fact
            for fact in facts
        }

        return [
            unique[key]
            for key in sorted(unique)
        ]

    # --------------------------------------------------------
    # Main learning run
    # --------------------------------------------------------

    async def run(
        self,
        objective: LearningObjective,
        *,
        principal_id: str = "aura-learning",
        resource_scope: str = "research",
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> LearningRun:

        run = LearningRun(
            run_id=self._run_id(objective),
            objective_id=objective.objective_id,
            status=LearningStatus.RUNNING,
        )

        checkpoint = self._load_checkpoint(
            objective.objective_id
        )

        if checkpoint.get("completed"):
            run.status = LearningStatus.COMPLETED
            return run

        started = time.monotonic()

        try:
            await self.knowledge.initialize()
            await self.memory.initialize()

            queries = self.planner.plan_queries(
                objective.description,
                self.policy.max_steps,
            )

            processed_queries = set(
                checkpoint.get(
                    "queries",
                    [],
                )
            )

            processed_sources = set(
                checkpoint.get(
                    "sources",
                    [],
                )
            )

            checkpoint["objective_id"] = (
                objective.objective_id
            )

            for query in queries:
                if run.steps >= self.policy.max_steps:
                    break

                if (
                    time.monotonic()
                    - started
                    >= self.policy.max_runtime_seconds
                ):
                    break

                if query in processed_queries:
                    continue

                processed_queries.add(query)
                checkpoint["queries"] = sorted(
                    processed_queries
                )

                response = await self._invoke(
                    principal_id=principal_id,
                    capability_id=(
                        self.tool_spec.search_capability_id
                    ),
                    operation_id=(
                        self.tool_spec.search_operation_id
                    ),
                    tool_name=(
                        self.tool_spec.search_tool_name
                    ),
                    arguments={
                        "query": query,
                    },
                    resource_scope=resource_scope,
                    risk_level=risk_level,
                    task_id=run.run_id,
                )

                payload = self._payload(
                    response
                )

                items = self._search_items(
                    payload
                )

                run.steps += 1

                for item in items:
                    if run.sources >= self.policy.max_sources:
                        break

                    uri, title = self._candidate(
                        item
                    )

                    if not uri:
                        continue

                    source_id = self._source_id(
                        uri
                    )

                    if source_id in processed_sources:
                        continue

                    fetch_response = await self._invoke(
                        principal_id=principal_id,
                        capability_id=(
                            self.tool_spec.fetch_capability_id
                        ),
                        operation_id=(
                            self.tool_spec.fetch_operation_id
                        ),
                        tool_name=(
                            self.tool_spec.fetch_tool_name
                        ),
                        arguments={
                            "url": uri,
                        },
                        resource_scope=resource_scope,
                        risk_level=risk_level,
                        task_id=run.run_id,
                    )

                    fetched = self._fetch_text(
                        self._payload(
                            fetch_response
                        )
                    ).strip()

                    if not fetched:
                        continue

                    source = KnowledgeSource(
                        source_id=source_id,
                        uri=uri,
                        source_type="mcp",
                        title=title,
                        metadata={
                            "objective_id":
                                objective.objective_id,
                            "learning_run_id":
                                run.run_id,
                        },
                    )

                    payload_bytes = fetched.encode(
                        "utf-8"
                    )

                    await self.knowledge.ingest_source(
                        source,
                        payload_bytes,
                    )

                    record = KnowledgeRecord.create(
                        namespace="research",
                        content=fetched,
                        source_id=source.source_id,
                        kind="research",
                        title=title,
                        confidence=0.5,
                        metadata={
                            "objective_id":
                                objective.objective_id,
                            "learning_run_id":
                                run.run_id,
                            "uri": uri,
                        },
                    )

                    facts = await self._extract_facts(
                        source=source,
                        content=fetched,
                    )

                    for fact in facts:
                        await self.knowledge.ingest_fact(
                            fact
                        )

                    record.facts = [
                        fact.fact_id
                        for fact in facts
                    ]

                    record.evidence = [
                        evidence
                        for fact in facts
                        for evidence in fact.evidence
                    ]

                    await self.knowledge.ingest_record(
                        record
                    )

                    await self.memory.put(
                        MemoryRecord(
                            record_id=record.record_id,
                            namespace=record.namespace,
                            content=record.content,
                            source=source.uri,
                            metadata={
                                "source_id":
                                    source.source_id,
                                "objective_id":
                                    objective.objective_id,
                                "learning_run_id":
                                    run.run_id,
                                "fact_count":
                                    str(len(facts)),
                            },
                            created_at=record.created_at,
                        )
                    )

                    processed_sources.add(
                        source_id
                    )

                    checkpoint["sources"] = sorted(
                        processed_sources
                    )

                    checkpoint["records"] = sorted(
                        set(
                            checkpoint.get(
                                "records",
                                [],
                            )
                        )
                        | {record.record_id}
                    )

                    checkpoint["facts"] = sorted(
                        set(
                            checkpoint.get(
                                "facts",
                                [],
                            )
                        )
                        | {
                            fact.fact_id
                            for fact in facts
                        }
                    )

                    self._save_checkpoint(
                        objective.objective_id,
                        checkpoint,
                    )

                    run.sources += 1
                    run.records += 1

            checkpoint["completed"] = True
            self._save_checkpoint(
                objective.objective_id,
                checkpoint,
            )

            run.status = LearningStatus.COMPLETED
            return run

        except asyncio.CancelledError:
            run.status = LearningStatus.STOPPED
            self._save_checkpoint(
                objective.objective_id,
                checkpoint,
            )
            raise

        except Exception as exc:
            run.status = LearningStatus.FAILED
            run.error = (
                f"{type(exc).__name__}: {exc}"
            )

            self._save_checkpoint(
                objective.objective_id,
                checkpoint,
            )

            return run
