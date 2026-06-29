"""Deterministic policy checks for control-plane action requests."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from api.application.action_catalog import CatalogDetail
from api.application.contracts import (
    ActionRequest,
    PolicyDecision,
    PolicyDecisionStatus,
    SafetyLevel,
)
from api.application.utils.scope_checker import ScopeChecker
from api.domain.models import ScopeRuleModel


FORBIDDEN_OPTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "exec",
    "raw_command",
    "nmap" + "_cli",
}


@dataclass(frozen=True)
class CapabilityPolicyResult:
    """Catalog entry validation result plus errors."""

    detail: CatalogDetail | None
    reasons: list[str]

    @property
    def is_allowed(self) -> bool:
        return self.detail is not None and not self.reasons


@dataclass(frozen=True)
class ScopePolicyResult:
    """Target allow/block result for a catalog scope policy."""

    allowed_targets: list[str]
    blocked_targets: list[str]
    reasons: list[str]


@dataclass(frozen=True)
class RiskPolicyResult:
    """Resolved safety class for the requested catalog entry."""

    safety_level: SafetyLevel
    reasons: list[str]


@dataclass(frozen=True)
class ApprovalPolicyResult:
    """Approval requirement produced from catalog/profile/scope/risk state."""

    requires_approval: bool
    reasons: list[str]


class CapabilityPolicy:
    """Validate active catalog selection and allowlisted options."""

    def __init__(self, forbidden_option_keys: set[str] | None = None):
        self.forbidden_option_keys = forbidden_option_keys or FORBIDDEN_OPTION_KEYS

    def evaluate(self, request: ActionRequest, detail: CatalogDetail) -> CapabilityPolicyResult:
        reasons: list[str] = []
        profile = request.profile

        if profile.capability_id != detail.capability:
            reasons.append(
                "Resolved capability mismatch: "
                f"request={profile.capability_id} catalog={detail.capability}"
            )
        if profile.profile_id != detail.profile:
            reasons.append(
                "Resolved profile mismatch: "
                f"request={profile.profile_id} catalog={detail.profile}"
            )

        allowed_options = (
            set(detail.option_schema)
            if detail.option_schema
            else set(detail.allowed_options)
        )
        unknown_options = set(profile.options) - allowed_options
        forbidden_options = set(profile.options) & self.forbidden_option_keys
        if unknown_options:
            reasons.append(
                "Unsupported options for "
                f"{detail.capability}/{detail.profile}: {sorted(unknown_options)}"
            )
        if forbidden_options:
            reasons.append(f"Forbidden command-like options: {sorted(forbidden_options)}")
        if not profile.targets:
            reasons.append("No targets provided")

        return CapabilityPolicyResult(detail=detail, reasons=reasons)


class ScopePolicyService:
    """Apply catalog scope policy to requested targets."""

    def evaluate(
        self,
        request: ActionRequest,
        detail: CatalogDetail,
        *,
        scope_rules: Sequence[ScopeRuleModel] | None = None,
    ) -> ScopePolicyResult:
        targets = list(request.profile.targets)
        if detail.scope_policy == "strict":
            if not scope_rules:
                return ScopePolicyResult(
                    allowed_targets=[],
                    blocked_targets=targets,
                    reasons=["strict scope requires at least one scope rule"],
                )
            allowed, blocked = ScopeChecker.filter_in_scope(targets, list(scope_rules or []))
            reasons = []
            if blocked:
                reasons.append(f"strict scope blocked targets: {blocked}")
            return ScopePolicyResult(
                allowed_targets=allowed,
                blocked_targets=blocked,
                reasons=reasons,
            )
        return ScopePolicyResult(allowed_targets=targets, blocked_targets=[], reasons=[])


class RiskPolicy:
    """Resolve safety class from active catalog metadata."""

    def evaluate(self, detail: CatalogDetail) -> RiskPolicyResult:
        return RiskPolicyResult(
            safety_level=SafetyLevel(detail.safety_level),
            reasons=[],
        )


class ApprovalPolicy:
    """Determine whether the action requires human approval."""

    def evaluate(
        self,
        detail: CatalogDetail,
        risk: RiskPolicyResult,
        scope: ScopePolicyResult,
    ) -> ApprovalPolicyResult:
        reasons: list[str] = []
        if detail.requires_approval:
            reasons.append(f"Profile requires human approval: {detail.profile}")
        if risk.safety_level in {SafetyLevel.ACTIVE, SafetyLevel.SENSITIVE} and detail.scope_policy == "strict":
            reasons.append(f"Safety level requires review: {risk.safety_level.value}")
        if scope.blocked_targets and not scope.allowed_targets:
            return ApprovalPolicyResult(requires_approval=False, reasons=[])
        return ApprovalPolicyResult(requires_approval=bool(reasons), reasons=reasons)


class PolicyService:
    """Compose capability, scope, risk, and approval policy checks."""

    def __init__(
        self,
        *,
        capability_policy: CapabilityPolicy | None = None,
        scope_policy: ScopePolicyService | None = None,
        risk_policy: RiskPolicy | None = None,
        approval_policy: ApprovalPolicy | None = None,
    ):
        self.capability_policy = capability_policy or CapabilityPolicy()
        self.scope_policy = scope_policy or ScopePolicyService()
        self.risk_policy = risk_policy or RiskPolicy()
        self.approval_policy = approval_policy or ApprovalPolicy()

    def approve(
        self,
        request: ActionRequest,
        detail: CatalogDetail,
        *,
        approved_by: str,
        reason: str | None = None,
        scope_rules: Sequence[ScopeRuleModel] | None = None,
    ) -> PolicyDecision:
        reasons = [f"Approved by {approved_by}"]
        if reason:
            reasons.append(reason)

        scope = self.scope_policy.evaluate(request, detail, scope_rules=scope_rules)
        reasons.extend(scope.reasons)
        if scope.blocked_targets and not scope.allowed_targets:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=reasons,
                allowed_targets=[],
                blocked_targets=scope.blocked_targets,
                safety_level=SafetyLevel(detail.safety_level),
                metadata=self._metadata(detail, approved_by=approved_by),
            )

        return PolicyDecision(
            action_id=request.action_id,
            status=PolicyDecisionStatus.ALLOWED,
            reasons=reasons,
            allowed_targets=scope.allowed_targets,
            blocked_targets=scope.blocked_targets,
            safety_level=SafetyLevel(detail.safety_level),
            metadata=self._metadata(detail, approved_by=approved_by),
        )

    def reject(
        self,
        request: ActionRequest,
        *,
        rejected_by: str,
        reason: str | None = None,
    ) -> PolicyDecision:
        reasons = [f"Rejected by {rejected_by}"]
        if reason:
            reasons.append(reason)
        return PolicyDecision(
            action_id=request.action_id,
            status=PolicyDecisionStatus.REJECTED,
            reasons=reasons,
            blocked_targets=request.profile.targets,
            metadata={"rejected_by": rejected_by},
        )

    def evaluate(
        self,
        request: ActionRequest,
        detail: CatalogDetail,
        *,
        scope_rules: Sequence[ScopeRuleModel] | None = None,
    ) -> PolicyDecision:
        capability = self.capability_policy.evaluate(request, detail)
        risk = self.risk_policy.evaluate(detail)
        if not capability.is_allowed:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=capability.reasons,
                blocked_targets=request.profile.targets,
                safety_level=risk.safety_level,
                metadata=self._metadata(detail),
            )

        scope = self.scope_policy.evaluate(request, detail, scope_rules=scope_rules)
        if scope.blocked_targets and not scope.allowed_targets:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=scope.reasons,
                allowed_targets=[],
                blocked_targets=scope.blocked_targets,
                safety_level=risk.safety_level,
                metadata=self._metadata(detail),
            )

        approval = self.approval_policy.evaluate(detail, risk, scope)
        if approval.requires_approval:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.REQUIRES_APPROVAL,
                reasons=approval.reasons + scope.reasons,
                allowed_targets=scope.allowed_targets,
                blocked_targets=scope.blocked_targets,
                safety_level=risk.safety_level,
                metadata=self._metadata(detail),
            )

        return PolicyDecision(
            action_id=request.action_id,
            status=PolicyDecisionStatus.ALLOWED,
            reasons=scope.reasons,
            allowed_targets=scope.allowed_targets,
            blocked_targets=scope.blocked_targets,
            safety_level=risk.safety_level,
            metadata=self._metadata(detail),
        )

    @staticmethod
    def _metadata(
        detail: CatalogDetail,
        *,
        approved_by: str | None = None,
    ) -> dict[str, str]:
        metadata = {
            "capability_id": detail.capability,
            "profile_id": detail.profile,
            "scope_policy": detail.scope_policy,
            "catalog_hash": str(detail.snapshot_id),
        }
        if approved_by is not None:
            metadata["approved_by"] = approved_by
        return metadata
