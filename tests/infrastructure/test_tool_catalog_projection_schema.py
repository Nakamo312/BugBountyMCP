import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.adapters.orm import tool_catalog_entries, tool_catalog_snapshots


def test_tool_catalog_tables_are_snapshot_projection_not_relational_source_of_truth() -> None:
    snapshot_columns = set(tool_catalog_snapshots.c.keys())
    entry_columns = set(tool_catalog_entries.c.keys())

    assert {"catalog_hash", "source_hash", "manifest_json", "activated_at"}.issubset(
        snapshot_columns
    )
    assert {"snapshot_id", "manifest_fragment", "active", "allowed_options"}.issubset(
        entry_columns
    )
    assert "command_template" not in entry_columns


def test_tool_catalog_entries_are_tied_to_snapshot_version() -> None:
    constraint_names = {
        constraint.name for constraint in tool_catalog_entries.constraints if constraint.name
    }

    assert "uq_tool_catalog_entries_snapshot_profile" in constraint_names
    assert tool_catalog_entries.c.snapshot_id.foreign_keys
