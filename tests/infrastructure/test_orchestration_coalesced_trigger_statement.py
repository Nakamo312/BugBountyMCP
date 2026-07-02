from __future__ import annotations

from sqlalchemy.sql.dml import Update

from api.infrastructure.orchestration.run_claim_statements import append_coalesced_trigger_statement


def test_append_coalesced_trigger_statement_uses_sqlalchemy_core() -> None:
    statement = append_coalesced_trigger_statement()

    assert isinstance(statement, Update)
    compiled = str(statement)
    assert "UPDATE runs" in compiled
    assert "coalesced_trigger_count" in compiled
    assert "jsonb_array_elements" in compiled
    assert "jsonb_agg" in compiled
    assert ":trigger_sample" in compiled
    assert ":sample_limit" in compiled
    assert ":run_id" in compiled
    assert ":now" in compiled


def test_append_coalesced_trigger_statement_preserves_tail_trim_contract() -> None:
    compiled = str(append_coalesced_trigger_statement())

    assert "ORDER BY" in compiled
    assert "LIMIT" in compiled
    assert "WITH ORDINALITY" in compiled


def test_append_coalesced_trigger_statement_names_ordinality_columns_for_postgres() -> None:
    from sqlalchemy.dialects.postgresql import dialect

    compiled = str(append_coalesced_trigger_statement().compile(dialect=dialect()))

    assert "WITH ORDINALITY AS" in compiled
    assert "(item, ord)" in compiled
