"""Action service exception types."""
from __future__ import annotations


class ActionNotFoundError(Exception):
    """Raised when an action transition targets an unknown action."""


class ActionApprovalStateError(Exception):
    """Raised when an action cannot be approved from its current state."""


class ActionOutcomeNotFoundError(Exception):
    """Raised when feedback targets no recorded action outcome."""


class ActionOutcomeFeedbackUnavailable(Exception):
    """Raised when the outcome feedback writer is not configured."""
