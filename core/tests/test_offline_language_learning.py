"""Principal-scoped, persistent language-learning scheduling and privacy tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest

from aura_core.application.language_learning import SQLiteVocabularyReview


T0 = datetime(2026, 11, 15, 12, tzinfo=UTC)


def test_persistent_scheduling_and_grade_progression(tmp_path):
    path = tmp_path / "vocabulary.sqlite3"
    store = SQLiteVocabularyReview(path)
    card = store.add_card(
        principal_id="alice", language="de",
        prompt="Haus", answer="house", now=T0,
    )
    assert card.revision == 0
    assert store.due_cards(principal_id="alice", now=T0)[0].card_id == card.card_id
    first = store.review(
        principal_id="alice", card_id=card.card_id,
        grade=5, expected_revision=0, now=T0,
    )
    assert first.interval_days == 1
    assert first.repetitions == 1
    assert first.revision == 1
    assert store.due_cards(principal_id="alice", now=T0) == ()
    second = store.review(
        principal_id="alice", card_id=card.card_id,
        grade=5, expected_revision=1, now=T0 + timedelta(days=1),
    )
    assert second.interval_days == 6
    assert second.repetitions == 2
    assert SQLiteVocabularyReview(path).due_cards(
        principal_id="alice", now=T0 + timedelta(days=7)
    )[0].card_id == card.card_id


def test_wrong_principal_and_stale_revision_fail_closed(tmp_path):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    card = store.add_card(principal_id="owner", language="tr",
                          prompt="merhaba", answer="hello", now=T0)
    assert store.due_cards(principal_id="other", now=T0) == ()
    with pytest.raises(ValueError):
        store.review(principal_id="other", card_id=card.card_id,
                     grade=5, expected_revision=0, now=T0)
    store.review(principal_id="owner", card_id=card.card_id,
                 grade=5, expected_revision=0, now=T0)
    with pytest.raises(ValueError, match="stale"):
        store.review(principal_id="owner", card_id=card.card_id,
                     grade=5, expected_revision=0, now=T0)


def test_failed_card_resets_spaced_repetition(tmp_path):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    card = store.add_card(principal_id="owner", language="en",
                          prompt="apple", answer="elma", now=T0)
    failed = store.review(principal_id="owner", card_id=card.card_id,
                          grade=0, expected_revision=0, now=T0)
    assert failed.repetitions == 0
    assert failed.interval_days == 1
    assert failed.ease_factor >= 1.3


def test_delete_requires_confirmation_and_stays_in_principal_scope(tmp_path):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    a = store.add_card(principal_id="alice", language="de",
                       prompt="eins", answer="one", now=T0)
    b = store.add_card(principal_id="bob", language="de",
                       prompt="zwei", answer="two", now=T0)
    with pytest.raises(PermissionError):
        store.forget_card(principal_id="alice", card_id=a.card_id)
    assert store.forget_card(principal_id="bob", card_id=a.card_id,
                             confirmed=True) is False
    assert store.forget_card(principal_id="alice", card_id=a.card_id,
                             confirmed=True) is True
    assert store.due_cards(principal_id="alice", now=T0) == ()
    assert store.due_cards(principal_id="bob", now=T0)[0].card_id == b.card_id


@pytest.mark.parametrize("params", [
    {"principal_id": " owner", "language": "de", "prompt": "q", "answer": "a"},
    {"principal_id": "", "language": "de", "prompt": "q", "answer": "a"},
    {"principal_id": "owner", "language": "de/../../", "prompt": "q", "answer": "a"},
    {"principal_id": "owner", "language": "de", "prompt": "q", "answer": "x\ninjection"},
    {"principal_id": "owner", "language": "de", "prompt": "", "answer": "a"},
])
def test_invalid_card_input_rejected(tmp_path, params):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    with pytest.raises(ValueError):
        store.add_card(**params)


@pytest.mark.parametrize("grade, revision", [(True, 0), (-1, 0), (6, 0), (5, True)])
def test_invalid_grade_and_revision_rejected(tmp_path, grade, revision):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    card = store.add_card(principal_id="owner", language="de",
                          prompt="q", answer="a", now=T0)
    with pytest.raises(ValueError):
        store.review(principal_id="owner", card_id=card.card_id,
                     grade=grade, expected_revision=revision, now=T0)


def test_unauthorized_caller_needs_application_boundary(tmp_path):
    store = SQLiteVocabularyReview(tmp_path / "cards.sqlite3")
    with pytest.raises(ValueError):
        store.due_cards(principal_id="owner", limit=False)
    with pytest.raises(ValueError):
        store.add_card(principal_id="owner", language="de",
                       prompt="q", answer="a", now=datetime(2026, 1, 1))
