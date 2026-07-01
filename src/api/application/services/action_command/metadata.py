"""Resolved action command metadata assembly."""
from __future__ import annotations

from typing import Any

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionRequest
from api.application.execution_limits import ExecutionBudget


def command_metadata(
    *,
    action: ActionRequest,
    detail: CatalogDetail,
    budget: ExecutionBudget,
) -> dict[str, Any]:
    """Build persisted metadata for a resolved action command."""
    return {
        **action.metadata,
        "catalog_entry_id": str(detail.id),
        "catalog_snapshot_id": str(detail.snapshot_id),
        "effective_budget": budget.model_dump(mode="json"),
    }
