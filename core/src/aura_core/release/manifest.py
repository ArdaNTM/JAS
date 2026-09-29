"""Canonical version and artifact inventory for reproducible releases."""

from dataclasses import asdict, dataclass
from hashlib import sha256
from json import dumps
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    version: str
    components: dict[str, str]
    dependencies: dict[str, str]

    def canonical_json(self) -> str:
        return dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def write(self, path: Path) -> None:
        path.write_text(self.canonical_json() + "\n", encoding="utf-8")
