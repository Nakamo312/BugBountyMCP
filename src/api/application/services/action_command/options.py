"""Action command option normalization."""
from __future__ import annotations

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionRequest
from api.application.execution_limits import normalize_options


def normalized_options(action: ActionRequest, detail: CatalogDetail) -> dict:
    """Return request options after catalog schema normalization."""
    if not detail.option_schema:
        return dict(action.options)
    return normalize_options(detail.option_schema, action.options)
