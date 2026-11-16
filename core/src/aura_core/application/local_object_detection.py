"""Bounded object-location extraction through the real governed local Ollama model.

Model-generated boxes are explicitly UNTRUSTED hypotheses. This layer never
captures images, moves a pointer, labels a person as an identity, grants
permissions, or performs actions. Real HTTP inference uses feature #77's
MCP Gateway-protected model provider.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

from aura_core.providers.ollama_vision_mcp import (
    GovernedImageUnderstanding, ImageUnderstandingDenied,
    ImageUnderstandingUnavailable,
)

_MAX_OBJECTS = 16
_MAX_LABEL = 64
_PROMPT = (
    "Detect up to 16 clearly visible physical objects. Return ONLY a JSON "
    'object exactly shaped as {"objects":[{"label":"lamp",'
    '"box":[0.1,0.2,0.3,0.4]}]}. '
    "Coordinates are normalized [left, top, right, bottom] in image space "
    "between 0 and 1, strictly positive width and height. "
    "Use concise generic object names, do not infer identities, "
    "feelings, secret data or hidden objects. Empty list when uncertain. "
    "Do not include Markdown or explanations."
)


class ObjectDetectionUnavailable(ValueError):
    """Model output was unsupported; no invented or clickable boxes returned."""


@dataclass(frozen=True, slots=True)
class DetectedObject:
    label: str
    box: tuple[float, float, float, float]
    trust: str = "UNTRUSTED_MODEL_LOCATION"


@dataclass(frozen=True, slots=True)
class ObjectDetectionEvidence:
    objects: tuple[DetectedObject, ...]
    image_sha256: str
    provider_id: str
    trust: str = "UNTRUSTED_MODEL_LOCATION"
    safe_for_automated_input: bool = False


def _parse_model_boxes(text: str) -> tuple[DetectedObject, ...]:
    if not isinstance(text, str) or not 1 <= len(text) <= 8000:
        raise ObjectDetectionUnavailable("Image model returned no bounded object data")
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ObjectDetectionUnavailable("Image model did not return valid object JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"objects"}:
        raise ObjectDetectionUnavailable("Object JSON schema mismatch")
    raw = payload["objects"]
    if not isinstance(raw, list) or len(raw) > _MAX_OBJECTS:
        raise ObjectDetectionUnavailable("Too many model-generated objects")
    objects: list[DetectedObject] = []
    seen: set[tuple[str, tuple[float, ...]]] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"label", "box"}:
            raise ObjectDetectionUnavailable("Unexpected object fields")
        label = item.get("label")
        if (
            not isinstance(label, str) or not 1 <= len(label) <= _MAX_LABEL
            or label != label.strip()
            or any(not (c.isalnum() or c in " _.-") for c in label)
        ):
            raise ObjectDetectionUnavailable("Unsafe object label")
        coords = item.get("box")
        if (
            not isinstance(coords, list) or len(coords) != 4
            or any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 1
                   for n in coords)
        ):
            raise ObjectDetectionUnavailable("Invalid normalized model box")
        x1, y1, x2, y2 = tuple(float(v) for v in coords)
        if not x1 < x2 or not y1 < y2:
            raise ObjectDetectionUnavailable("Empty or inverted object box")
        box = (x1, y1, x2, y2)
        key = (label.casefold(), box)
        if key in seen:
            raise ObjectDetectionUnavailable("Duplicate generated object")
        seen.add(key)
        objects.append(DetectedObject(label=label, box=box))
    objects.sort(key=lambda x: (x.label.casefold(), x.box))
    return tuple(objects)


class GovernedLocalObjectDetector:
    """Compose a real Gateway-bound image model, never a second model tool."""

    def __init__(self, vision: GovernedImageUnderstanding) -> None:
        if not isinstance(vision, GovernedImageUnderstanding):
            raise TypeError("Existing principal-bound governed Ollama vision is required")
        self._vision = vision

    async def detect(
        self,
        image: bytes,
        *,
        capture_confirmed: bool,
    ) -> ObjectDetectionEvidence:
        # This call independently enforces consent, Core permission,
        # MCP Gateway tool validation and current local-provider dispatch.
        evidence = await self._vision.describe(
            image, prompt=_PROMPT,
            capture_confirmed=capture_confirmed,
        )
        if evidence.trust != "UNTRUSTED_LOCAL_MODEL_OUTPUT":
            raise ObjectDetectionUnavailable("Incorrect upstream image evidence trust")
        return ObjectDetectionEvidence(
            objects=_parse_model_boxes(evidence.description),
            image_sha256=evidence.image_sha256,
            provider_id=evidence.provider_id,
        )
