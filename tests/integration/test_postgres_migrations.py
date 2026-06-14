from __future__ import annotations

import pytest
from sqlalchemy import inspect, text


pytestmark = pytest.mark.integration


def test_alembic_upgrade_head_creates_control_plane_tables(integration_sync_engine) -> None:
    inspector = inspect(integration_sync_engine)

    required_tables = {
        "action_requests",
        "action_request_targets",
        "action_request_options",
        "policy_decisions",
        "scope_decisions",
        "approval_requests",
        "approval_decisions",
        "campaigns",
        "jobs",
        "runs",
        "event_store",
        "event_dispatches",
    }

    assert required_tables.issubset(set(inspector.get_table_names()))


def test_alembic_upgrade_head_creates_graph_projection_tables(integration_sync_engine) -> None:
    inspector = inspect(integration_sync_engine)

    required_tables = {
        "graph_fact_batches",
        "graph_projection_events",
    }

    assert required_tables.issubset(set(inspector.get_table_names()))


def test_integration_database_guard_uses_test_database(
    integration_sync_engine,
    integration_postgres_settings,
) -> None:
    with integration_sync_engine.connect() as connection:
        database = connection.execute(text("select current_database()")).scalar_one()

    assert database == integration_postgres_settings["database"]
    assert "test" in database or "integration" in database
