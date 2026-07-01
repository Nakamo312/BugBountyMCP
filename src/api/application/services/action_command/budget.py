"""Action command execution budget resolution."""
from __future__ import annotations

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionRequest
from api.application.execution_limits import (
    ActionInputValidationError,
    ExecutionBudget,
    resolve_execution_budget,
)


def resolved_budget(
    *,
    action: ActionRequest,
    detail: CatalogDetail,
    system_budget: ExecutionBudget,
) -> ExecutionBudget:
    """Resolve the effective budget from system, catalog profile, and request layers."""
    return resolve_execution_budget(
        system=system_budget,
        profile=detail.execution_budget,
        requested=action.budget,
    )


def validate_target_budget(action: ActionRequest, budget: ExecutionBudget) -> None:
    """Reject requests that exceed the effective target count limit."""
    if budget.max_targets is not None and len(action.targets) > budget.max_targets:
        raise ActionInputValidationError(
            f"target count {len(action.targets)} exceeds max_targets {budget.max_targets}"
        )
