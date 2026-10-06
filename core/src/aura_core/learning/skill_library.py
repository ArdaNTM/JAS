from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True, slots=True)
class SkillStep:
    action: str
    capability_id: str | None = None
    operation_id: str | None = None
    arguments_template: dict[str, object] = field(
        default_factory=dict
    )


@dataclass(slots=True)
class Skill:
    skill_id: str
    name: str
    description: str
    steps: list[SkillStep]
    preconditions: list[str] = field(
        default_factory=list
    )
    postconditions: list[str] = field(
        default_factory=list
    )
    tags: list[str] = field(
        default_factory=list
    )
    source_run_ids: list[str] = field(
        default_factory=list
    )
    success_count: int = 0
    failure_count: int = 0
    confidence: float = 0.5
    version: int = 1
    enabled: bool = False
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    @property
    def success_rate(self) -> float:
        total = (
            self.success_count
            + self.failure_count
        )

        if total == 0:
            return self.confidence

        return self.success_count / total

    def record_success(
        self,
        run_id: str | None = None,
    ) -> None:
        self.success_count += 1

        if (
            run_id
            and run_id not in self.source_run_ids
        ):
            self.source_run_ids.append(
                run_id
            )

        self.confidence = min(
            1.0,
            self.confidence * 0.8 + 0.2,
        )

        self.updated_at = datetime.now(UTC)

    def record_failure(
        self,
        run_id: str | None = None,
    ) -> None:
        self.failure_count += 1

        if (
            run_id
            and run_id not in self.source_run_ids
        ):
            self.source_run_ids.append(
                run_id
            )

        self.confidence = max(
            0.0,
            self.confidence * 0.8,
        )

        self.updated_at = datetime.now(UTC)

        if self.success_rate < 0.5:
            self.enabled = False

    def can_execute(self) -> bool:
        return (
            self.enabled
            and bool(self.steps)
            and self.confidence > 0.0
        )


@dataclass(frozen=True, slots=True)
class SkillMatch:
    skill: Skill
    score: float
    reason: str


class SkillLibrary:
    """
    Persistent reusable workflow library.

    Skills are declarative data, not arbitrary executable Python.
    Promotion is controlled separately by SkillPromotionManager.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_skills: int = 1000,
    ) -> None:
        if max_skills < 1:
            raise ValueError(
                "max_skills must be positive"
            )

        self.root = root
        self.max_skills = max_skills
        self.path = root / "skills.json"
        self._skills: dict[str, Skill] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.path.exists():
            return

        async with self._lock:
            try:
                payload = json.loads(
                    self.path.read_text(
                        encoding="utf-8"
                    )
                )
            except (
                OSError,
                json.JSONDecodeError,
            ):
                return

            if not isinstance(
                payload,
                list,
            ):
                return

            self._skills.clear()

            for item in payload:
                skill = self._deserialize(
                    item
                )

                if skill is not None:
                    self._skills[
                        skill.skill_id
                    ] = skill

    @staticmethod
    def _deserialize(
        payload: object,
    ) -> Skill | None:
        if not isinstance(
            payload,
            dict,
        ):
            return None

        try:
            steps = [
                SkillStep(
                    action=str(
                        item.get(
                            "action",
                            "",
                        )
                    ),
                    capability_id=item.get(
                        "capability_id"
                    ),
                    operation_id=item.get(
                        "operation_id"
                    ),
                    arguments_template=dict(
                        item.get(
                            "arguments_template",
                            {},
                        )
                    ),
                )
                for item in payload.get(
                    "steps",
                    [],
                )
                if isinstance(
                    item,
                    dict,
                )
            ]

            return Skill(
                skill_id=str(
                    payload["skill_id"]
                ),
                name=str(
                    payload["name"]
                ),
                description=str(
                    payload["description"]
                ),
                steps=steps,
                preconditions=[
                    str(item)
                    for item in payload.get(
                        "preconditions",
                        [],
                    )
                ],
                postconditions=[
                    str(item)
                    for item in payload.get(
                        "postconditions",
                        [],
                    )
                ],
                tags=[
                    str(item)
                    for item in payload.get(
                        "tags",
                        [],
                    )
                ],
                source_run_ids=[
                    str(item)
                    for item in payload.get(
                        "source_run_ids",
                        [],
                    )
                ],
                success_count=int(
                    payload.get(
                        "success_count",
                        0,
                    )
                ),
                failure_count=int(
                    payload.get(
                        "failure_count",
                        0,
                    )
                ),
                confidence=float(
                    payload.get(
                        "confidence",
                        0.5,
                    )
                ),
                version=int(
                    payload.get(
                        "version",
                        1,
                    )
                ),
                enabled=bool(
                    payload.get(
                        "enabled",
                        False,
                    )
                ),
                created_at=datetime.fromisoformat(
                    str(
                        payload.get(
                            "created_at",
                            datetime.now(
                                UTC
                            ).isoformat(),
                        )
                    )
                ),
                updated_at=datetime.fromisoformat(
                    str(
                        payload.get(
                            "updated_at",
                            datetime.now(
                                UTC
                            ).isoformat(),
                        )
                    )
                ),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return None

    async def _persist(self) -> None:
        payload = [
            asdict(skill)
            for skill in self._skills.values()
        ]

        temporary = self.path.with_suffix(
            ".tmp"
        )

        temporary.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        temporary.replace(
            self.path
        )

    @staticmethod
    def make_id(
        name: str,
        description: str,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (
                    "aura-skill:"
                    f"{name.strip().casefold()}:"
                    f"{description.strip().casefold()}"
                ),
            )
        )

    async def register(
        self,
        skill: Skill,
    ) -> Skill:
        if not skill.steps:
            raise ValueError(
                "A skill must contain at least one step"
            )

        if not skill.name.strip():
            raise ValueError(
                "Skill name cannot be empty"
            )

        if not skill.description.strip():
            raise ValueError(
                "Skill description cannot be empty"
            )

        async with self._lock:
            existing = self._skills.get(
                skill.skill_id
            )

            if existing is not None:
                existing.steps = skill.steps
                existing.preconditions = (
                    skill.preconditions
                )
                existing.postconditions = (
                    skill.postconditions
                )
                existing.tags = skill.tags
                existing.source_run_ids = (
                    skill.source_run_ids
                )
                existing.success_count = (
                    skill.success_count
                )
                existing.failure_count = (
                    skill.failure_count
                )
                existing.confidence = (
                    skill.confidence
                )
                existing.enabled = (
                    skill.enabled
                )
                existing.version += 1
                existing.updated_at = (
                    datetime.now(UTC)
                )

                await self._persist()
                return existing

            if len(
                self._skills
            ) >= self.max_skills:
                raise RuntimeError(
                    "Skill library capacity exhausted"
                )

            skill.enabled = False

            self._skills[
                skill.skill_id
            ] = skill

            await self._persist()

            return skill

    async def get(
        self,
        skill_id: str,
    ) -> Skill | None:
        async with self._lock:
            return self._skills.get(
                skill_id
            )

    async def remove(
        self,
        skill_id: str,
    ) -> bool:
        async with self._lock:
            if skill_id not in self._skills:
                return False

            del self._skills[
                skill_id
            ]

            await self._persist()
            return True

    async def record_success(
        self,
        skill_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        async with self._lock:
            skill = self._skills.get(
                skill_id
            )

            if skill is None:
                raise KeyError(
                    f"Unknown skill: {skill_id}"
                )

            skill.record_success(
                run_id
            )

            await self._persist()

    async def record_failure(
        self,
        skill_id: str,
        *,
        run_id: str | None = None,
    ) -> None:
        async with self._lock:
            skill = self._skills.get(
                skill_id
            )

            if skill is None:
                raise KeyError(
                    f"Unknown skill: {skill_id}"
                )

            skill.record_failure(
                run_id
            )

            await self._persist()

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
    ) -> list[SkillMatch]:
        if limit < 1:
            return []

        query_tokens = set(
            re.findall(
                r"[a-zA-Z0-9_ğüşöçıİĞÜŞÖÇ]+",
                query.casefold(),
            )
        )

        if not query_tokens:
            return []

        async with self._lock:
            candidates: list[
                SkillMatch
            ] = []

            for skill in self._skills.values():
                if not skill.can_execute():
                    continue

                searchable = " ".join(
                    [
                        skill.name,
                        skill.description,
                        *skill.tags,
                    ]
                ).casefold()

                skill_tokens = set(
                    re.findall(
                        r"[a-zA-Z0-9_ğüşöçıİĞÜŞÖÇ]+",
                        searchable,
                    )
                )

                overlap = (
                    len(
                        query_tokens
                        & skill_tokens
                    )
                    / max(
                        1,
                        len(query_tokens),
                    )
                )

                if overlap <= 0:
                    continue

                score = (
                    overlap * 0.7
                    + skill.confidence * 0.2
                    + skill.success_rate * 0.1
                )

                candidates.append(
                    SkillMatch(
                        skill=skill,
                        score=score,
                        reason=(
                            "token overlap + "
                            "confidence + "
                            "success rate"
                        ),
                    )
                )

            candidates.sort(
                key=lambda item: (
                    -item.score,
                    item.skill.skill_id,
                )
            )

            return candidates[:limit]

    async def list(
        self,
        *,
        enabled_only: bool = True,
    ) -> list[Skill]:
        async with self._lock:
            values = list(
                self._skills.values()
            )

            if enabled_only:
                values = [
                    skill
                    for skill in values
                    if skill.enabled
                ]

            return sorted(
                values,
                key=lambda item: (
                    -item.confidence,
                    -item.success_rate,
                    item.name,
                ),
            )

    async def snapshot(
        self,
    ) -> dict[str, object]:
        async with self._lock:
            return {
                "count": len(
                    self._skills
                ),
                "capacity": self.max_skills,
                "skills": [
                    {
                        "skill_id": skill.skill_id,
                        "name": skill.name,
                        "version": skill.version,
                        "confidence": skill.confidence,
                        "success_rate": (
                            skill.success_rate
                        ),
                        "success_count": (
                            skill.success_count
                        ),
                        "failure_count": (
                            skill.failure_count
                        ),
                        "enabled": skill.enabled,
                    }
                    for skill in self._skills.values()
                ],
            }


class SkillExtractor:
    @staticmethod
    def from_run(
        *,
        run_id: str,
        objective: str,
        capability_id: str,
        operation_id: str,
        tool_name: str,
        success: bool,
        confidence: float = 0.7,
    ) -> Skill | None:
        if not success:
            return None

        normalized = " ".join(
            objective.split()
        ).strip()

        if not normalized:
            return None

        name = (
            f"Research: "
            f"{normalized[:72]}"
        )

        skill_id = SkillLibrary.make_id(
            name,
            normalized,
        )

        return Skill(
            skill_id=skill_id,
            name=name,
            description=(
                "Reusable research workflow for: "
                f"{normalized}"
            ),
            steps=[
                SkillStep(
                    action=(
                        "invoke research tool"
                    ),
                    capability_id=(
                        capability_id
                    ),
                    operation_id=(
                        operation_id
                    ),
                    arguments_template={
                        "tool_name": tool_name,
                        "objective": normalized,
                    },
                )
            ],
            preconditions=[
                "Research capability is authorized",
                "Required tool is available",
            ],
            postconditions=[
                "Research result is collected",
                "Result passes normal admission control",
            ],
            tags=[
                "research",
                "learning",
                "reusable",
            ],
            source_run_ids=[
                run_id
            ],
            confidence=max(
                0.0,
                min(1.0, confidence),
            ),
            enabled=False,
        )
