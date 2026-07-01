from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_action_submission_workflow_does_not_own_review_decisions() -> None:
    submission_source = (ROOT / "src/api/application/services/action_submission.py").read_text()
    approval_source = (ROOT / "src/api/application/services/action_approval.py").read_text()

    assert "class ActionSubmissionWorkflow" in submission_source
    assert "def request_action" in submission_source
    assert "def request_scan" in submission_source
    assert "def approve_action" not in submission_source
    assert "def reject_action" not in submission_source
    assert "ApprovalDecisionWriter" not in submission_source
    assert "ApprovalRequestReader" not in submission_source

    assert "class ActionApprovalWorkflow" in approval_source
    assert "def approve_action" in approval_source
    assert "def reject_action" in approval_source
    assert "ApprovalDecisionWriter" in approval_source
    assert "ApprovalRequestReader" in approval_source


def test_action_submission_workflow_requires_prebuilt_collaborators() -> None:
    submission_source = (ROOT / "src/api/application/services/action_submission.py").read_text()

    assert "command_compiler: ActionCommandCompiler" in submission_source
    assert "policy_evaluator: ActionPolicyEvaluator" in submission_source
    assert "recorder: ActionSubmissionRecorder" in submission_source
    assert "command_compiler or" not in submission_source
    assert "policy_evaluator or" not in submission_source
    assert "ActionCommandCompiler(" not in submission_source
    assert "ActionPolicyEvaluator(" not in submission_source
    assert "ActionSubmissionRecorder(" not in submission_source
    assert "commands: ActionCommandPort" not in submission_source
    assert "ActionCommandPort" not in submission_source
    assert "catalog: ActionCatalogService" not in submission_source
    assert "policy: PolicyService" not in submission_source
    assert "system_budget" not in submission_source


def test_action_service_does_not_compose_runtime_collaborators() -> None:
    service_source = (ROOT / "src/api/application/services/action.py").read_text()
    composition_source = (ROOT / "src/api/application/services/action_composition.py").read_text()

    assert "class ActionService" in service_source
    assert "ActionCommandCompiler(" not in service_source
    assert "ActionPolicyEvaluator(" not in service_source
    assert "ActionSubmissionRecorder(" not in service_source
    assert "ActionReadService(" not in service_source
    assert "ActionOutcomeFeedbackService(" not in service_source
    assert "commands: ActionCommandPort" not in service_source
    assert "ActionCommandPort" not in service_source
    assert "catalog: ActionCatalogService" not in service_source
    assert "policy: PolicyService" not in service_source

    assert "def build_action_service" in composition_source
    assert "ActionCommandCompiler(" in composition_source
    assert "ActionPolicyEvaluator(" in composition_source
    assert "ActionSubmissionRecorder(" in composition_source
    assert "ActionReadService(" in composition_source
