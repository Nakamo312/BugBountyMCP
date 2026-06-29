from __future__ import annotations

from pathlib import Path

from api.infrastructure.adapters.orm import metadata


def test_cypher_query_audits_table_is_declared_in_orm() -> None:
    table = metadata.tables["cypher_query_audits"]

    for column in (
        "program_id",
        "workflow_id",
        "actor",
        "query_hash",
        "params_hash",
        "allowed",
        "reason",
        "row_count",
        "timeout_seconds",
        "created_at",
    ):
        assert column in table.c

    assert "idx_cypher_query_audits_program_created" in {index.name for index in table.indexes}
    assert "ck_cypher_query_audits_actor_not_empty" in {
        constraint.name for constraint in table.constraints
    }


def test_cypher_gateway_migration_follows_agent_coordination_head() -> None:
    source = Path("alembic/versions/e1f2g3h4i5j6_add_cypher_query_audits.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "d0e1f2g3h4i6"' in source
    assert '"cypher_query_audits"' in source
    assert "idx_cypher_query_audits_program_created" in source
