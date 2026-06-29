from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping, Protocol
from uuid import UUID

from .proposal_row_codec import _adapt_json_parameters_for_cursor, _optional_uuid, _required_uuid
from .proposal_store_statements import (
    ACTION_EXPERIENCE_PROPOSAL_ROWS_SQL,
    ACTION_EXPERIENCE_PROPOSAL_RUN_UPSERT_SQL,
    PREVIOUS_ACTION_EXPERIENCE_PROPOSAL_RUN_SQL,
    UPDATE_ACTION_EXPERIENCE_DECISION_SHIFT_SQL,
    decision_shift_values,
    previous_proposal_run_values,
    proposal_distribution_values,
)


class Cursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...
    def fetchone(self) -> Mapping[str, Any] | None: ...


def upsert_proposal_run(cursor: Cursor, values: dict[str, Any]) -> UUID:
    cursor.execute(
        ACTION_EXPERIENCE_PROPOSAL_RUN_UPSERT_SQL,
        _adapt_json_parameters_for_cursor(cursor, values),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("action_experience_proposal_runs insert did not return an id")
    return UUID(str(row["id"]))


def fetch_proposal_distribution_rows(
    cursor: Cursor,
    *,
    proposal_run_id: UUID,
    top_k: int,
) -> list[Mapping[str, Any]]:
    cursor.execute(
        ACTION_EXPERIENCE_PROPOSAL_ROWS_SQL,
        proposal_distribution_values(proposal_run_id=proposal_run_id, top_k=top_k),
    )
    return list(cursor.fetchall())


def fetch_previous_proposal_run_id(cursor: Cursor, *, source: Mapping[str, Any]) -> UUID | None:
    cursor.execute(
        PREVIOUS_ACTION_EXPERIENCE_PROPOSAL_RUN_SQL,
        previous_proposal_run_values(
            program_id=_required_uuid(source, "program_id"),
            campaign_id=_optional_uuid(source.get("campaign_id")),
            source_outcome_id=_required_uuid(source, "id"),
        ),
    )
    row = cursor.fetchone()
    return None if row is None else _required_uuid(row, "proposal_run_id")


def persist_decision_shift(
    cursor: Cursor,
    *,
    proposal_run_id: UUID,
    payload: dict[str, object],
    now: datetime | None = None,
) -> None:
    cursor.execute(
        UPDATE_ACTION_EXPERIENCE_DECISION_SHIFT_SQL,
        _adapt_json_parameters_for_cursor(
            cursor,
            decision_shift_values(
                proposal_run_id=proposal_run_id,
                payload=payload,
                now=now or datetime.now(UTC),
            ),
        ),
    )
