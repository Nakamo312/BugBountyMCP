"""Compile action requests into resolved immutable commands."""
from __future__ import annotations

from api.application.action_catalog import CatalogDetail
from api.application.contracts import ActionRequest, ResolvedActionCommand
from api.application.execution_limits import ExecutionBudget
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.action_command.budget import resolved_budget, validate_target_budget
from api.application.services.action_command.metadata import command_metadata
from api.application.services.action_command.options import normalized_options


class ActionCommandCompiler:
    """Apply catalog profile, option schema, and budget limits to an action request."""

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
        options = normalized_options(action, detail)
        budget = resolved_budget(
            action=action,
            detail=detail,
            system_budget=self.system_budget,
        )
        validate_target_budget(action, budget)
        return ResolvedActionCommand.from_request(
            action,
            capability_id=detail.capability,
            profile_id=detail.profile,
            options=options,
            execution_budget=budget,
            metadata=command_metadata(action=action, detail=detail, budget=budget),
        )
