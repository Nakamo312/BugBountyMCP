"""Policy evaluation helpers for action submissions."""
from __future__ import annotations

from uuid import UUID

from api.application.action_catalog import CatalogDetail
from api.application.contracts import (
    ActionRequest,
    PolicyDecision,
    PolicyDecisionStatus,
)
from api.application.ports.action import ScopeRuleProvider
from api.application.services.action_errors import ActionApprovalStateError
from api.application.services.policy import PolicyService
from api.domain.models import ScopeRuleModel


class ActionPolicyEvaluator:
    """Apply action policy and attach catalog metadata to decisions."""

    def __init__(
        self,
        *,
        policy: PolicyService,
        scope_rules: ScopeRuleProvider | None = None,
    ) -> None:
        self.policy = policy
        self.scope_rules = scope_rules

    async def evaluate(
        self,
        action: ActionRequest,
        detail: CatalogDetail,
    ) -> PolicyDecision:
        decision = self.policy.evaluate(
            action,
            detail,
            scope_rules=await self._scope_rules_for(action.program_id),
        )
        self.attach_catalog(action, decision)
        return decision

    async def approve(
        self,
        action: ActionRequest,
        detail: CatalogDetail,
        *,
        approved_by: str,
        reason: str | None,
    ) -> PolicyDecision:
        decision = self.policy.approve(
            action,
            detail,
            approved_by=approved_by,
            reason=reason,
            scope_rules=await self._scope_rules_for(action.program_id),
        )
        self.attach_catalog(action, decision)
        if decision.status != PolicyDecisionStatus.ALLOWED:
            raise ActionApprovalStateError(
                "Action approval failed policy re-check: " + "; ".join(decision.reasons)
            )
        return decision

    def reject(
        self,
        action: ActionRequest,
        *,
        rejected_by: str,
        reason: str | None,
    ) -> PolicyDecision:
        decision = self.policy.reject(action, rejected_by=rejected_by, reason=reason)
        self.attach_catalog(action, decision)
        return decision

    async def _scope_rules_for(self, program_id: UUID) -> list[ScopeRuleModel]:
        if self.scope_rules is None:
            return []
        return await self.scope_rules.find_by_program(program_id)

    @staticmethod
    def attach_catalog(action: ActionRequest, decision: PolicyDecision) -> None:
        decision.metadata = {
            **decision.metadata,
            "catalog_entry_id": str(action.catalog_id),
            "catalog_snapshot_id": action.metadata.get("catalog_snapshot_id"),
        }
