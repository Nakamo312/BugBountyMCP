from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from api.infrastructure.adapters.orm import metadata


def _constraint_names(table_name: str, constraint_type: type) -> set[str]:
    table = metadata.tables[table_name]
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def _index_names(table_name: str) -> set[str]:
    table = metadata.tables[table_name]
    return {index.name for index in table.indexes if index.name is not None}


def test_surface_map_tables_are_part_of_orm_metadata() -> None:
    expected_tables = {
        "surface_snapshots",
        "surface_nodes",
        "surface_edges",
        "surface_clusters",
        "surface_cluster_members",
        "surface_cluster_labels",
        "surface_deltas",
    }

    assert expected_tables <= set(metadata.tables)
    assert "features_json" in metadata.tables["surface_nodes"].c
    assert "evidence_json" in metadata.tables["surface_edges"].c
    assert "details_json" in metadata.tables["surface_deltas"].c
    assert "uq_surface_nodes_snapshot_fingerprint" in _constraint_names("surface_nodes", UniqueConstraint)
    assert "ck_surface_edges_no_self_edge" in _constraint_names("surface_edges", CheckConstraint)
    assert "idx_surface_deltas_program_to_snapshot" in _index_names("surface_deltas")


def test_surface_component_analysis_tables_are_part_of_orm_metadata() -> None:
    expected_tables = {
        "surface_component_analysis_runs",
        "surface_component_analysis_items",
        "surface_component_analysis_events",
    }

    assert expected_tables <= set(metadata.tables)
    assert "report_fingerprint" in metadata.tables["surface_component_analysis_runs"].c
    assert "exploration_priority_score" in metadata.tables["surface_component_analysis_items"].c
    assert "dedupe_key" in metadata.tables["surface_component_analysis_events"].c
    assert "uq_surface_component_analysis_runs_program_fingerprint" in _constraint_names(
        "surface_component_analysis_runs",
        UniqueConstraint,
    )
    assert "uq_surface_component_analysis_events_dedupe_key" in _index_names("surface_component_analysis_events")


def test_search_projection_events_table_is_part_of_orm_metadata() -> None:
    table = metadata.tables["search_projection_events"]

    assert "target" in table.c
    assert "source_type" in table.c
    assert "filters_json" in table.c
    assert "result_json" in table.c
    assert "uq_search_projection_events_dedupe_key" in _index_names("search_projection_events")
    assert "ck_search_projection_events_status_valid" in _constraint_names("search_projection_events", CheckConstraint)
