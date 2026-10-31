"""Bounded, read-only AURA architecture and operational gap discovery.

This service never executes Python, writes to its checkout, reads environment
files, or copies raw log/source text into proposals. Its results are *evidence
for human review*, not instructions or authority grants.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

SCOPES = ("core/src/aura_core", "aura-ui/src", "docs")
SKIP_PARTS = frozenset({
    ".git", ".venv", "__pycache__", "node_modules", ".cache", "dist",
    "build", "data", "secrets", "credentials", "private", ".pytest_cache",
})
SENSITIVE = re.compile(r"(?i)(?:^\.|\.env|secret|credential|password|token|\.key$|\.pem$)")
MARKERS = re.compile(r"\b(TODO|FIXME)\b", re.I)
LOG_MARKERS = {
    "timeout": re.compile(rb"(?i)\b(?:timeout|timed\s*out)\b"),
    "exception": re.compile(rb"(?i)\b(?:exception|traceback)\b"),
    "startup_failure": re.compile(rb"(?i)(?:startup failed|lifespan startup failed)"),
}


@dataclass(frozen=True, slots=True)
class GoalProposal:
    proposal_id: str
    category: str
    summary: str
    evidence_path: str
    evidence_line: int
    evidence_sha256: str
    priority: str = "review"
    review_required: bool = True
    execution_performed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    scanned_files: int
    skipped_files: int
    proposals: tuple[GoalProposal, ...]
    source: str = "local_static_evidence"
    status: str = "review_only"

    def to_dict(self) -> dict:
        return {
            "scanned_files": self.scanned_files,
            "skipped_files": self.skipped_files,
            "proposals": [p.to_dict() for p in self.proposals],
            "source": self.source,
            "status": self.status,
            "writes_performed": False,
            "tools_executed": False,
        }


class AutonomousAnalyzer:
    def __init__(
        self, checkout: str | Path, *, max_files: int = 240,
        max_file_bytes: int = 128_000, max_proposals: int = 40,
        log_tail_bytes: int = 32_768,
    ) -> None:
        self.root = Path(checkout).resolve(strict=True)
        if not (self.root / "core/src/aura_core").is_dir():
            raise ValueError("JAS checkout root is required")
        if not 1 <= max_files <= 1000 or not 1024 <= max_file_bytes <= 262_144:
            raise ValueError("Invalid file budgets")
        if not 1 <= max_proposals <= 100 or not 1024 <= log_tail_bytes <= 65_536:
            raise ValueError("Invalid result budgets")
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_proposals = max_proposals
        self.log_tail_bytes = log_tail_bytes

    def _allowed(self, path: Path) -> bool:
        try:
            relative = path.relative_to(self.root)
            return (
                path.is_file() and not path.is_symlink()
                and path.resolve().is_relative_to(self.root)
                and all(part not in SKIP_PARTS and not SENSITIVE.search(part)
                        for part in relative.parts)
            )
        except (ValueError, OSError):
            return False

    def _iter_sources(self):
        for scope in SCOPES:
            directory = self.root / scope
            if not directory.is_dir() or directory.is_symlink():
                continue
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() in {".py", ".ts", ".tsx", ".md"} and self._allowed(path):
                    yield path

    @staticmethod
    def _find_source_gaps(path: Path, source: str):
        for line_number, line in enumerate(source.splitlines(), 1):
            if line.lstrip().startswith(("#", "//", "*", "<!--")):
                match = MARKERS.search(line)
                if match:
                    yield "maintenance_marker", line_number, (
                        match.group(1).upper() + " marker needs review"
                    )
        if path.suffix == ".py":
            try:
                tree = ast.parse(source)
            except SyntaxError as exc:
                yield "syntax_error", exc.lineno or 1, "Python syntax needs review"
            else:
                for node in ast.walk(tree):
                    if not isinstance(node, ast.ExceptHandler):
                        continue
                    if node.type is None or (
                        isinstance(node.type, ast.Name) and node.type.id == "Exception"
                    ):
                        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                            yield "silent_failure", node.lineno, "Exception silently ignored"

    @staticmethod
    def _proposal(path: str, line: int, digest: str, category: str, summary: str):
        identity = f"{path}:{line}:{digest}:{category}"
        return GoalProposal(
            proposal_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
            category=category, summary=summary,
            evidence_path=path, evidence_line=line, evidence_sha256=digest,
        )

    def scan(self) -> AnalysisReport:
        scanned = skipped = 0
        proposals: list[GoalProposal] = []
        for path in self._iter_sources():
            if scanned >= self.max_files or len(proposals) >= self.max_proposals:
                break
            try:
                if path.stat().st_size > self.max_file_bytes:
                    skipped += 1
                    continue
                with path.open("rb") as stream:
                    payload = stream.read(self.max_file_bytes + 1)
                if len(payload) > self.max_file_bytes:
                    skipped += 1
                    continue
                text = payload.decode("utf-8-sig")
            except (OSError, UnicodeError):
                skipped += 1
                continue
            scanned += 1
            relative = path.relative_to(self.root).as_posix()
            digest = hashlib.sha256(payload).hexdigest()
            for category, line, summary in self._find_source_gaps(path, text):
                proposals.append(self._proposal(relative, line, digest, category, summary))
                if len(proposals) >= self.max_proposals:
                    break

        # The log scanner returns *counts of known error classes only*.
        # It does not emit raw log lines, request contents, or stack traces.
        logs = self.root / "logs"
        if logs.is_dir() and not logs.is_symlink():
            for path in sorted(logs.glob("*.log"))[:12]:
                if len(proposals) >= self.max_proposals:
                    break
                if not self._allowed(path):
                    continue
                try:
                    with path.open("rb") as stream:
                        stream.seek(0, 2)
                        stream.seek(max(0, stream.tell() - self.log_tail_bytes))
                        payload = stream.read(self.log_tail_bytes)
                except OSError:
                    skipped += 1
                    continue
                digest = hashlib.sha256(payload).hexdigest()
                for category, pattern in LOG_MARKERS.items():
                    count = min(len(pattern.findall(payload)), 100)
                    if count:
                        proposals.append(self._proposal(
                            path.relative_to(self.root).as_posix(), 0, digest,
                            "log_" + category, f"{category}: {count} occurrences in bounded log tail",
                        ))
                        if len(proposals) >= self.max_proposals:
                            break
        return AnalysisReport(scanned, skipped, tuple(proposals))
