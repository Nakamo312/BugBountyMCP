"""Action submission conflict helpers."""
from __future__ import annotations

import uuid

from sqlalchemy.exc import IntegrityError

from api.application.services.action_errors import ActionSubmissionConflict


def is_duplicate_action_request_integrity_error(exc: IntegrityError) -> bool:
    """Return true only for duplicate action_requests primary-key conflicts."""
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    message = str(orig).lower() if orig is not None else ""
    return constraint_name == "action_requests_pkey" or (
        getattr(orig, "pgcode", None) == "23505"
        and "action_requests" in message
        and "action_requests_pkey" in message
    )


def raise_submission_conflict_for_duplicate_action(
    action_id: uuid.UUID,
    exc: IntegrityError,
) -> None:
    if is_duplicate_action_request_integrity_error(exc):
        raise ActionSubmissionConflict(str(action_id)) from exc
