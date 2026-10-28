import pytest

from aura_core.enterprise.postgresql_workflow_store import PostgreSQLWorkflowStore


def test_postgresql_workflow_store_rejects_missing_or_local_database_url() -> None:
    with pytest.raises(ValueError, match="AURA_DATABASE_URL is required"):
        PostgreSQLWorkflowStore("")
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        PostgreSQLWorkflowStore("sqlite:///local.db")
