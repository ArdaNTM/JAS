import pytest

from aura_core.application.postgresql_episodic_memory import PostgreSQLEpisodicMemoryStore
from aura_core.enterprise.postgresql_approval_store import PostgreSQLApprovalStore


@pytest.mark.parametrize("factory", [PostgreSQLApprovalStore, PostgreSQLEpisodicMemoryStore])
def test_remote_store_rejects_missing_or_local_database_url(factory) -> None:
    with pytest.raises(ValueError, match="AURA_DATABASE_URL is required"):
        factory("")
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        factory("sqlite:///local.db")
