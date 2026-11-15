"""Review-only fact-candidate detection: principal isolation and no auto-resolution."""
from __future__ import annotations

import pytest
from aura_core.application.episodic_memory import EpisodicMemoryStore


def test_only_explicit_same_key_differences_are_reviewed(tmp_path):
    store = EpisodicMemoryStore(tmp_path / "mem.sqlite")
    older = store.remember(
        principal_id="alice", kind="fact", content="City: Berlin",
        tags=("fact:home.city",),
    )
    store.remember(
        principal_id="alice", kind="fact", content="City: Berlin",
        tags=("fact:home.city",),
    )
    newest = store.remember(
        principal_id="alice", kind="fact", content="City: Munich",
        tags=("fact:home.city",),
    )
    store.remember(
        principal_id="alice", kind="fact", content="I like coffee",
        tags=("other:coffee",),
    )
    store.remember(
        principal_id="alice", kind="fact", content="I like tea",
        tags=("other:coffee",),
    )
    store.remember(
        principal_id="bob", kind="fact", content="City: Hamburg",
        tags=("fact:home.city",),
    )
    result = store.find_conflict_candidates(principal_id="alice")
    assert len(result) == 1
    candidate = result[0]
    assert candidate["fact_key"] == "home.city"
    assert candidate["newest_memory_id"] == newest.memory_id
    assert candidate["older_memory_id"] != newest.memory_id
    assert candidate["status"] == "NEEDS_HUMAN_REVIEW"
    assert candidate["untrusted"] is True
    assert "Hamburg" not in str(result)
    assert store.count(principal_id="alice") == 5
    assert store.count(principal_id="bob") == 1
    assert older.memory_id in {
        item.memory_id for item in store.recall(principal_id="alice", kind="fact")
    }


def test_ambiguous_tags_and_equivalent_literal_values_do_not_trigger(tmp_path):
    store = EpisodicMemoryStore(tmp_path / "mem.sqlite")
    for content, tags in (
        ("BERLIN", ("fact:home.city",)),
        ("berlin", ("fact:home.city",)),
        ("Paris", ("fact:home.city", "fact:work.city")),
        ("London", ("fact:home.city", "fact:work.city")),
        ("Madrid", ("fact:bad key",)),
        ("Rome", ("fact:bad key",)),
    ):
        store.remember(principal_id="owner", kind="fact", content=content, tags=tags)
    assert store.find_conflict_candidates(principal_id="owner") == []


def test_conflict_review_is_strictly_read_only_and_scoped(tmp_path):
    store = EpisodicMemoryStore(tmp_path / "mem.sqlite")
    older = store.remember(
        principal_id="owner", kind="fact", content="Alice", tags=("fact:alias",),
    )
    store.remember(
        principal_id="owner", kind="fact", content="Bob", tags=("fact:alias",),
    )
    store.remember(
        principal_id="other", kind="fact", content="Charlie", tags=("fact:alias",),
    )
    previous = store.recall(principal_id="owner")
    assert len(store.find_conflict_candidates(principal_id="owner")) == 1
    assert store.find_conflict_candidates(principal_id="other") == []
    assert store.count(principal_id="owner") == 2
    assert store.recall(principal_id="owner") == previous
    assert older.memory_id in [x.memory_id for x in previous]


@pytest.mark.parametrize("options", [
    {"principal_id": ""}, {"principal_id": "owner", "limit": 0},
    {"principal_id": "owner", "limit": True},
    {"principal_id": "owner", "scan_limit": 1},
    {"principal_id": "owner", "scan_limit": 1001},
])
def test_bad_boundaries_fail_closed(tmp_path, options):
    store = EpisodicMemoryStore(tmp_path / "mem.sqlite")
    with pytest.raises(ValueError):
        store.find_conflict_candidates(**options)
