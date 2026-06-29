from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from .row_codec import (
    CursorLike,
    adapt_json_parameters_for_cursor,
    optional_int as _optional_int,
    optional_text as _optional_text,
    optional_uuid as _optional_uuid,
    optional_uuid_text as _optional_uuid_text,
    required_text_value as _required_text,
    required_uuid_value as _required_uuid_value,
)

_PROPOSAL_JSON_KEYS = frozenset(
    {
        "feature_keys",
        "graph_counts",
        "explanation",
        "review_payload",
        "decision_graph_counts",
        "decision_distribution",
        "decision_shift",
    }
)


def _required_uuid(row: Mapping[str, Any], key: str) -> UUID:
    value = _optional_uuid(row.get(key))
    if value is None:
        raise ValueError(f"missing required UUID field: {key}")
    return value


def _adapt_json_parameters_for_cursor(cursor: CursorLike, parameters: dict[str, object]) -> dict[str, object]:
    return adapt_json_parameters_for_cursor(cursor, parameters, json_keys=_PROPOSAL_JSON_KEYS)
