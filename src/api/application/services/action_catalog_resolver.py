"""Catalog resolution helpers for action submissions."""
from __future__ import annotations

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionRequest, ResolvedActionCommand
from api.application.execution_limits import (
    ActionInputValidationError,
    ExecutionBudget,
    normalize_options,
    resolve_execution_budget,
)
from api.application.services.action_catalog import ActionCatalogService


class ActionCatalogResolver:
    """Resolve catalog details into immutable action command data."""

    def __init__(
        self,
        *,
        catalog: ActionCatalogService,
        system_budget: ExecutionBudget,
    ) -> None:
        self.catalog = catalog
        self.system_budget = system_budget

    async def resolve_command(
        self,
        action: ActionRequest,
    ) -> tuple[ResolvedActionCommand, CatalogDetail]:
        detail = await self.catalog.get_detail(action.catalog_id)
        return self.command_for(action, detail), detail

    async def resolve(self, action: ActionRequest) -> CatalogDetail:
        """Legacy mutating API kept for old callers. New code uses resolve_command()."""
        detail = await self.catalog.get_detail(action.catalog_id)
        self.bind(action, detail)
        return detail

    async def resolve_scan_event(
        self,
        *,
        event: str,
        profile_id: str | None,
    ) -> CatalogDetail:
        return await self.catalog.find_detail_by_event(event=event, profile=profile_id)

    def command_for(
        self,
        action: ActionRequest,
        detail: CatalogDetail,
    ) -> ResolvedActionCommand:
        options = self._normalized_options(action, detail)
        budget = self._resolved_budget(action, detail)
        self._validate_target_budget(action, budget)
        metadata = {
            **action.metadata,
            "catalog_entry_id": str(detail.id),
            "catalog_snapshot_id": str(detail.snapshot_id),
            "effective_budget": budget.model_dump(mode="json"),
        }
        return ResolvedActionCommand.from_request(
            action,
            capability_id=detail.capability,
            profile_id=detail.profile,
            options=options,
            execution_budget=budget,
            metadata=metadata,
        )

    def bind(self, action: ActionRequest, detail: CatalogDetail) -> None:
        """Legacy mutating bind. Keep only for compatibility tests and old adapters."""
        command = self.command_for(action, detail)
        action.bind_profile(
            capability_id=command.profile.capability_id,
            profile_id=command.profile.profile_id,
            options=command.profile.options,
            execution_budget=command.effective_budget,
        )
        action.metadata = dict(command.metadata)

    @staticmethod
    def _validate_target_budget(
        action: ActionRequest,
        budget: ExecutionBudget,
    ) -> None:
        if budget.max_targets is not None and len(action.targets) > budget.max_targets:
            raise ActionInputValidationError(
                f"target count {len(action.targets)} exceeds "
                f"max_targets {budget.max_targets}"
            )

    @staticmethod
    def _normalized_options(
        action: ActionRequest,
        detail: CatalogDetail,
    ) -> dict:
        if not detail.option_schema:
            return dict(action.options)
        return normalize_options(detail.option_schema, action.options)

    def _resolved_budget(
        self,
        action: ActionRequest,
        detail: CatalogDetail,
    ) -> ExecutionBudget:
        return resolve_execution_budget(
            system=self.system_budget,
            profile=detail.execution_budget,
            requested=action.budget,
        )
