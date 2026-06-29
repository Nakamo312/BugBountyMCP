from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from api.infrastructure.orchestration.event_store import is_duplicate_event_integrity_error


class _Diag:
    constraint_name = "event_store_event_id_key"


class _DuplicateOrig:
    diag = _Diag()
    pgcode = "23505"

    def __str__(self) -> str:
        return "duplicate key value violates unique constraint event_store_event_id_key"


class _ForeignKeyOrig:
    diag = type("Diag", (), {"constraint_name": "event_store_program_id_fkey"})()
    pgcode = "23503"

    def __str__(self) -> str:
        return "insert or update on table event_store violates foreign key constraint"


class _GenericUniqueOrig:
    diag = type("Diag", (), {"constraint_name": "other_table_event_id_key"})()
    pgcode = "23505"

    def __str__(self) -> str:
        return "duplicate key value violates unique constraint other_table_event_id_key"


def test_duplicate_event_integrity_error_is_idempotent_boundary() -> None:
    exc = IntegrityError("INSERT INTO event_store", {}, _DuplicateOrig())

    assert is_duplicate_event_integrity_error(exc) is True


def test_non_event_integrity_error_is_not_swallowed() -> None:
    assert (
        is_duplicate_event_integrity_error(
            IntegrityError("INSERT INTO event_store", {}, _ForeignKeyOrig())
        )
        is False
    )
    assert (
        is_duplicate_event_integrity_error(
            IntegrityError("INSERT INTO other_table", {}, _GenericUniqueOrig())
        )
        is False
    )
