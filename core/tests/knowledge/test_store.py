from pathlib import Path

from aura_core.knowledge.models import KnowledgeRecord
from aura_core.knowledge.store import KnowledgeStore


def test_knowledge_store(tmp_path: Path):
    store = KnowledgeStore(tmp_path)

    record = KnowledgeRecord.create(
        namespace="test",
        content="hello",
        source_id="source-1",
    )

    path = store.put_normalized(record)

    assert path.exists()
    assert path.parent.name == "normalized"
