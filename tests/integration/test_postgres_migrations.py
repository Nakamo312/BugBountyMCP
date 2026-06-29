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


def test_campaigns_have_bounded_expansion_budget_columns(
    integration_sync_engine,
) -> None:
    inspector = inspect(integration_sync_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("campaigns")
    }

    assert {
        "max_runs",
        "max_targets",
        "runs_consumed",
        "targets_consumed",
        "token_capacity",
        "tokens_available",
        "token_refill_per_second",
        "tokens_refilled_at",
    }.issubset(columns)


def test_raw_artifacts_have_m2_storage_safety_and_lineage_columns(
    integration_sync_engine,
) -> None:
    inspector = inspect(integration_sync_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("raw_artifacts")
    }

    assert {
        "storage_size_bytes",
        "content_encoding",
        "retention_class",
        "preview",
        "sanitized_preview",
        "sanitizer_version",
        "redaction_policy_version",
        "raw_safe_for_llm",
        "sanitized_safe_for_llm",
        "parser_name",
        "parser_version",
        "scope_decision_id",
        "source_targets",
        "parent_artifact_id",
    }.issubset(columns)


def test_alembic_upgrade_head_creates_graph_projection_tables(integration_sync_engine) -> None:
    inspector = inspect(integration_sync_engine)

    required_tables = {
        "graph_fact_batches",
        "graph_projection_events",
        "projection_watermarks",
    }

    assert required_tables.issubset(set(inspector.get_table_names()))


def test_alembic_upgrade_head_creates_agent_coordination_tables(integration_sync_engine) -> None:
    inspector = inspect(integration_sync_engine)

    required_tables = {
        "agent_workflows",
        "agent_workflow_runs",
        "agent_subscriptions",
        "agent_inbox",
        "agent_wait_conditions",
        "agent_result_sets",
        "cypher_query_audits",
    }

    assert required_tables.issubset(set(inspector.get_table_names()))


def test_alembic_upgrade_head_creates_langgraph_checkpoint_tables(
    integration_sync_engine,
) -> None:
    inspector = inspect(integration_sync_engine)

    required_tables = {
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
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
