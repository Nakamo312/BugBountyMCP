from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from api.infrastructure.orchestration import action_command_store


class _DuplicateActionRequestOrig:
    diag = type("Diag", (), {"constraint_name": "action_requests_pkey"})()
    pgcode = "23505"

    def __str__(self) -> str:
        return 'duplicate key value violates unique constraint "action_requests_pkey"'


class _ForeignKeyOrig:
    diag = type("Diag", (), {"constraint_name": "action_requests_program_id_fkey"})()
    pgcode = "23503"

    def __str__(self) -> str:
        return "insert or update on table action_requests violates foreign key constraint"


class _OtherUniqueOrig:
    diag = type("Diag", (), {"constraint_name": "uq_action_request_options_action_key"})()
    pgcode = "23505"

    def __str__(self) -> str:
        return 'duplicate key value violates unique constraint "uq_action_request_options_action_key"'


def test_duplicate_action_request_integrity_error_is_submission_conflict() -> None:
    classifier = getattr(
        action_command_store,
        "is_duplicate_action_request_integrity_error",
        None,
    )
    assert classifier is not None

    assert classifier(IntegrityError("INSERT INTO action_requests", {}, _DuplicateActionRequestOrig()))
    assert not classifier(IntegrityError("INSERT INTO action_requests", {}, _ForeignKeyOrig()))
    assert not classifier(IntegrityError("INSERT INTO action_request_options", {}, _OtherUniqueOrig()))
