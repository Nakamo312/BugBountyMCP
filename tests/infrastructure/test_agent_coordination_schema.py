from __future__ import annotations

from pathlib import Path

from api.infrastructure.adapters.orm import metadata


AGENT_COORDINATION_TABLES = {
    "agent_workflows",
    "agent_workflow_runs",
    "agent_subscriptions",
    "agent_inbox",
    "agent_wait_conditions",
    "agent_result_sets",
}


def test_agent_coordination_tables_are_declared_in_orm() -> None:
    assert AGENT_COORDINATION_TABLES.issubset(metadata.tables)


def test_agent_subscriptions_are_scoped_for_campaign_correlation_delivery() -> None:
    subscriptions = metadata.tables["agent_subscriptions"]

    for column in ("program_id", "campaign_id", "correlation_id", "event_type", "dedupe_key"):
        assert column in subscriptions.c

    assert "uq_agent_subscriptions_dedupe_key" in {
        constraint.name for constraint in subscriptions.constraints
    }
    assert "idx_agent_subscriptions_scope_event_status" in {
        index.name for index in subscriptions.indexes
    }


def test_agent_inbox_writes_are_idempotent_and_claimable() -> None:
    inbox = metadata.tables["agent_inbox"]

    for column in (
        "program_id",
        "campaign_id",
        "correlation_id",
        "event_id",
        "message_type",
        "payload",
        "dedupe_key",
        "status",
        "attempts",
        "available_at",
        "locked_by",
        "locked_until",
    ):
        assert column in inbox.c

    assert "uq_agent_inbox_dedupe_key" in {
        constraint.name for constraint in inbox.constraints
    }
    assert "idx_agent_inbox_status_available" in {index.name for index in inbox.indexes}


def test_agent_wait_conditions_cover_mvp_wait_types() -> None:
    wait_conditions = metadata.tables["agent_wait_conditions"]
    wait_status_check = "\n".join(
        str(constraint.sqltext)
        for constraint in wait_conditions.constraints
        if constraint.name == "ck_agent_wait_conditions_type_valid"
    )

    for wait_type in (
        "tool_run_completed",
        "ingestion_completed",
        "projections_ready",
        "new_facts_available",
        "campaign_quiescent",
    ):
        assert wait_type in wait_status_check

    assert "uq_agent_wait_conditions_run_key" in {
        constraint.name for constraint in wait_conditions.constraints
    }


def test_agent_coordination_migration_follows_projection_watermark_head() -> None:
    migration = Path("alembic/versions/d0e1f2g3h4i6_add_agent_coordination.py")
    source = migration.read_text(encoding="utf-8")

    assert 'down_revision = "c9d0e1f2g3h5"' in source
    for table_name in AGENT_COORDINATION_TABLES:
        assert f'"{table_name}"' in source
    assert "uq_agent_inbox_dedupe_key" in source
    assert "uq_agent_subscriptions_dedupe_key" in source
