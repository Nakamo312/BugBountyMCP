"""Composition helpers for the action control-plane service."""
from __future__ import annotations

from api.application.execution_limits import DEFAULT_SYSTEM_EXECUTION_BUDGET, ExecutionBudget
from api.application.ports.action import (
    ActionOutcomeFeedbackWriter,
    ActionPolicyResultWriter,
    ActionQueryPort,
    ActionResultPort,
    AllowedActionQueueWriter,
    ApprovalDecisionWriter,
    ApprovalRequestReader,
    ScopeRuleProvider,
)
from api.application.services.action import ActionService
from api.application.services.action_approval import ActionApprovalWorkflow
from api.application.services.action_catalog import ActionCatalogService
from api.application.services.action_command import ActionCommandCompiler
from api.application.services.action_envelope import ActionEnvelopeBuilder
from api.application.services.action_outcome_feedback import ActionOutcomeFeedbackService
from api.application.services.action_policy_evaluator import ActionPolicyEvaluator
from api.application.services.action_read import ActionReadService
from api.application.services.action_submission import ActionSubmissionWorkflow
from api.application.services.action_submission_recorder import ActionSubmissionRecorder
from api.application.services.policy import PolicyService


def build_action_service(
    *,
    policy_results: ActionPolicyResultWriter,
    allowed_actions: AllowedActionQueueWriter,
    queries: ActionQueryPort,
    results: ActionResultPort,
    approval_requests: ApprovalRequestReader,
    approval_decisions: ApprovalDecisionWriter,
    policy: PolicyService,
    catalog: ActionCatalogService,
    scope_rules: ScopeRuleProvider | None = None,
    outcome_feedback: ActionOutcomeFeedbackWriter | None = None,
    system_budget: ExecutionBudget | None = None,
) -> ActionService:
    """Assemble action use cases once at the composition boundary."""

    budget = system_budget or DEFAULT_SYSTEM_EXECUTION_BUDGET
    reads = ActionReadService(queries=queries, results=results)
    feedback = ActionOutcomeFeedbackService(
        queries=queries,
        outcome_feedback=outcome_feedback,
    )
    command_compiler = ActionCommandCompiler(
        catalog=catalog,
        system_budget=budget,
    )
    policy_evaluator = ActionPolicyEvaluator(
        policy=policy,
        scope_rules=scope_rules,
    )
    envelopes = ActionEnvelopeBuilder()
    recorder = ActionSubmissionRecorder(
        policy_results=policy_results,
        allowed_actions=allowed_actions,
        submission_lookup=reads.get_action_submission,
    )
    return ActionService(
        reads=reads,
        feedback=feedback,
        submissions=ActionSubmissionWorkflow(
            command_compiler=command_compiler,
            policy_evaluator=policy_evaluator,
            envelopes=envelopes,
            recorder=recorder,
            submission_lookup=reads.get_action_submission,
        ),
        approvals=ActionApprovalWorkflow(
            approval_requests=approval_requests,
            approval_decisions=approval_decisions,
            command_compiler=command_compiler,
            policy_evaluator=policy_evaluator,
            envelopes=envelopes,
        ),
    )
