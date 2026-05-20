"""Deterministic policy checks for control-plane action requests."""
from __future__ import annotations

from api.application.capabilities import CAPABILITY_BY_ID
from api.application.contracts import ActionRequest, PolicyDecision, PolicyDecisionStatus


FORBIDDEN_OPTION_KEYS = {
    "cmd",
    "command",
    "shell",
    "exec",
    "raw_command",
    "nmap" + "_cli",
}


class PolicyService:
    """Small deterministic policy layer before orchestration publishes work."""

    def approve(
        self,
        request: ActionRequest,
        *,
        approved_by: str,
        reason: str | None = None,
    ) -> PolicyDecision:
        reasons = [f"Approved by {approved_by}"]
        if reason:
            reasons.append(reason)
        return PolicyDecision(
            action_id=request.action_id,
            status=PolicyDecisionStatus.ALLOWED,
            reasons=reasons,
            allowed_targets=request.profile.targets,
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
        )

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        reasons: list[str] = []
        profile = request.profile
        capability = CAPABILITY_BY_ID.get(profile.capability_id)

        if capability is None:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=[f"Unknown capability: {profile.capability_id}"],
                blocked_targets=profile.targets,
            )

        profile_spec = next(
            (item for item in capability.profiles if item.id == profile.profile_id),
            None,
        )
        if profile_spec is None:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=[f"Unknown profile for {capability.id}: {profile.profile_id}"],
                blocked_targets=profile.targets,
            )

        unknown_options = set(profile.options) - profile_spec.allowed_options
        forbidden_options = set(profile.options) & FORBIDDEN_OPTION_KEYS
        if unknown_options:
            reasons.append(
                "Unsupported options for "
                f"{capability.id}/{profile_spec.id}: {sorted(unknown_options)}"
            )
        if forbidden_options:
            reasons.append(f"Forbidden command-like options: {sorted(forbidden_options)}")
        if not profile.targets:
            reasons.append("No targets provided")

        if reasons:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.BLOCKED,
                reasons=reasons,
                blocked_targets=profile.targets,
            )

        if profile_spec.requires_approval:
            return PolicyDecision(
                action_id=request.action_id,
                status=PolicyDecisionStatus.REQUIRES_APPROVAL,
                reasons=[f"Profile requires human approval: {profile_spec.id}"],
                blocked_targets=profile.targets,
            )

        return PolicyDecision(
            action_id=request.action_id,
            status=PolicyDecisionStatus.ALLOWED,
            reasons=[],
            allowed_targets=profile.targets,
        )
