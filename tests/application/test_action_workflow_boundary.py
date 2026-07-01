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
    assert "ActionApprovalPort" not in submission_source

    assert "class ActionApprovalWorkflow" in approval_source
    assert "def approve_action" in approval_source
    assert "def reject_action" in approval_source
    assert "ActionApprovalPort" in approval_source
