from __future__ import annotations

from pathlib import Path


def test_dashboard_feedback_clicks_do_not_invent_confidence_scores() -> None:
    for path in (
        Path("BugBountyDashBoard/src/hooks/useAgentWorkspace.js"),
        Path("BugBountyDashBoard/src/pages/AgentTaskDetail.jsx"),
    ):
        assert "confidence:" not in path.read_text(encoding="utf-8"), path
