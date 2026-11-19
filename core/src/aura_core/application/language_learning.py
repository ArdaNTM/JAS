"""Principal-scoped, local SQLite spaced-repetition vocabulary cards.

This internal store has NO network/API/tool authority. Authentication and
Owner consent must be enforced by its future application/API caller.
"""
from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterator

LANGUAGE = re.compile(r"[a-z]{2}(?:-[a-z]{2})?\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class VocabularyCard:
    card_id: str
    principal_id: str
    language: str
    prompt: str
    answer: str
    due_at: str
    interval_days: int
    repetitions: int
    ease_factor: float
    revision: int
    untrusted: bool = True


def _principal(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 128
            or value != value.strip() or any(ord(ch) < 32 for ch in value)):
        raise ValueError("invalid exact principal identity")
    return value


def _text(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value.strip()) <= 1000
            or any(ord(ch) < 32 for ch in value)):
        raise ValueError("invalid vocabulary text")
    return value.strip()


def _time(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return now.astimezone(UTC)


class SQLiteVocabularyReview:
    """Offline learning schedule, with exact principal scoping and CAS updates."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(Path(path).expanduser())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS vocabulary_cards (
                card_id TEXT PRIMARY KEY,
                principal_id TEXT NOT NULL,
                language TEXT NOT NULL,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                due_at TEXT NOT NULL,
                interval_days INTEGER NOT NULL,
                repetitions INTEGER NOT NULL,
                ease_factor REAL NOT NULL,
                revision INTEGER NOT NULL
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS idx_vocabulary_due
                ON vocabulary_cards(principal_id, due_at, card_id)""")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5.0)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _card(row: sqlite3.Row) -> VocabularyCard:
        return VocabularyCard(**dict(row))

    def add_card(
        self, *, principal_id: str, language: str,
        prompt: str, answer: str, now: datetime | None = None,
    ) -> VocabularyCard:
        principal = _principal(principal_id)
        if type(language) is not str or not LANGUAGE.fullmatch(language.lower()):
            raise ValueError("invalid language code")
        question, solution = _text(prompt), _text(answer)
        due = _time(now).isoformat()
        card_id = str(uuid.uuid4())
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute(
                "SELECT COUNT(*) FROM vocabulary_cards WHERE principal_id = ?",
                (principal,),
            ).fetchone()[0]
            if count >= 10000:
                raise ValueError("card limit reached")
            db.execute("""INSERT INTO vocabulary_cards
                (card_id, principal_id, language, prompt, answer, due_at,
                 interval_days, repetitions, ease_factor, revision)
                VALUES (?, ?, ?, ?, ?, ?, 0, 0, 2.5, 0)""",
                (card_id, principal, language.lower(), question, solution, due),
            )
            row = db.execute(
                "SELECT * FROM vocabulary_cards WHERE card_id = ?", (card_id,),
            ).fetchone()
        return self._card(row)

    def due_cards(
        self, *, principal_id: str, now: datetime | None = None, limit: int = 20
    ) -> tuple[VocabularyCard, ...]:
        principal = _principal(principal_id)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        timestamp = _time(now).isoformat()
        with self._db() as db:
            rows = db.execute(
                """SELECT * FROM vocabulary_cards
                   WHERE principal_id = ? AND due_at <= ?
                   ORDER BY due_at, card_id LIMIT ?""",
                (principal, timestamp, limit),
            ).fetchall()
        return tuple(self._card(row) for row in rows)

    def review(
        self, *, principal_id: str, card_id: str, grade: int,
        expected_revision: int, now: datetime | None = None,
    ) -> VocabularyCard:
        principal = _principal(principal_id)
        if type(card_id) is not str or len(card_id) != 36:
            raise ValueError("invalid card ID")
        if type(grade) is not int or not 0 <= grade <= 5:
            raise ValueError("grade must be 0..5")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("invalid revision")
        timestamp = _time(now)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                """SELECT * FROM vocabulary_cards
                   WHERE principal_id = ? AND card_id = ?""",
                (principal, card_id),
            ).fetchone()
            if previous is None or previous["revision"] != expected_revision:
                raise ValueError("card missing or stale revision")
            ease = float(previous["ease_factor"])
            if grade < 3:
                repetitions, interval = 0, 1
            else:
                repetitions = previous["repetitions"] + 1
                interval = (
                    1 if repetitions == 1 else
                    6 if repetitions == 2 else
                    max(1, round(previous["interval_days"] * ease))
                )
            ease = max(1.3, ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
            due = (timestamp + timedelta(days=interval)).isoformat()
            cursor = db.execute(
                """UPDATE vocabulary_cards
                   SET due_at = ?, interval_days = ?, repetitions = ?,
                       ease_factor = ?, revision = revision + 1
                   WHERE principal_id = ? AND card_id = ? AND revision = ?""",
                (due, interval, repetitions, round(ease, 4),
                 principal, card_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError("concurrent review conflict")
            current = db.execute(
                "SELECT * FROM vocabulary_cards WHERE principal_id = ? AND card_id = ?",
                (principal, card_id),
            ).fetchone()
        return self._card(current)

    def forget_card(
        self, *, principal_id: str, card_id: str, confirmed: bool = False,
    ) -> bool:
        principal = _principal(principal_id)
        if confirmed is not True:
            raise PermissionError("explicit deletion confirmation required")
        if type(card_id) is not str or len(card_id) != 36:
            raise ValueError("invalid card ID")
        with self._db() as db:
            result = db.execute(
                "DELETE FROM vocabulary_cards WHERE principal_id = ? AND card_id = ?",
                (principal, card_id),
            )
        return result.rowcount == 1
