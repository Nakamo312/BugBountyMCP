from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("services/search-indexer").resolve()))

from search_indexer.postgres_reader import (  # noqa: E402
    SURFACE_COMPONENT_COUNT_SQL,
    SURFACE_DELTA_COUNT_SQL,
    _count_query_and_parameters,
    _validate_pagination,
    batched_offsets,
)
from search_indexer.target_contracts import normalize_target_filters, validate_search_target  # noqa: E402


def test_count_target_query_rejects_unknown_targets_instead_of_keyerror() -> None:
    with pytest.raises(ValueError, match="unsupported search-indexer target"):
        _count_query_and_parameters(target="missing-target", program_id="program-1", filters=None)


def test_count_target_query_rejects_filters_outside_target_contract() -> None:
    with pytest.raises(ValueError, match="unsupported filter"):
        _count_query_and_parameters(
            target="http-observations",
            program_id="program-1",
            filters={"snapshot_id": "snapshot-1"},
        )


def test_surface_component_count_query_uses_only_allowlisted_filters() -> None:
    sql, parameters = _count_query_and_parameters(
        target="surface-components",
        program_id="program-1",
        filters={"analysis_run_id": " run-1 ", "snapshot_id": "snapshot-1"},
    )

    assert sql == SURFACE_COMPONENT_COUNT_SQL
    assert parameters == ("program-1", "run-1", "run-1", "snapshot-1", "snapshot-1")


def test_surface_delta_count_query_uses_snapshot_filter_contract() -> None:
    sql, parameters = _count_query_and_parameters(
        target="surface-deltas",
        program_id="program-1",
        filters={"snapshot_id": "snapshot-1"},
    )

    assert sql == SURFACE_DELTA_COUNT_SQL
    assert parameters == ("program-1", "snapshot-1", "snapshot-1")


def test_normalize_filters_drops_empty_values_but_keeps_target_contract() -> None:
    assert normalize_target_filters(
        target="surface-components",
        filters={"analysis_run_id": " ", "snapshot_id": "snapshot-1"},
    ) == {"snapshot_id": "snapshot-1"}


def test_validate_pagination_rejects_invalid_fetch_windows() -> None:
    with pytest.raises(ValueError, match="limit"):
        _validate_pagination(limit=0, offset=0)
    with pytest.raises(ValueError, match="offset"):
        _validate_pagination(limit=1, offset=-1)


def test_batched_offsets_rejects_non_positive_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        list(batched_offsets(limit=10, batch_size=0))


def test_validate_search_target_accepts_only_contract_targets() -> None:
    assert validate_search_target("surface-components") == "surface-components"
    assert validate_search_target(" all ", allow_all=True) == "all"
    with pytest.raises(ValueError, match="unsupported search-indexer target"):
        validate_search_target("missing-target")
