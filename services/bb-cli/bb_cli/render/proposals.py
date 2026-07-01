from __future__ import annotations

from typing import Any

from .common import experience_proposal_line, one_line, proposal_line, section, title


def render_proposals_from_workspace(snapshot: dict[str, Any]) -> str:
    lines = [title("Pending proposals")]
    agent_proposals = snapshot.get("pending_agent_proposals") or []
    experience_proposals = snapshot.get("pending_experience_proposals") or []
    if not agent_proposals and not experience_proposals:
        lines.append("No pending proposals.")
        return "\n".join(lines)

    if agent_proposals:
        lines.append(section("Agent action proposals"))
        for proposal in agent_proposals:
            lines.append(proposal_line(proposal))
            summary = one_line(proposal.get("summary"), limit=260)
            if summary:
                lines.append(f"  {summary}")
            lines.append(f"  Next: bb proposal accept {proposal.get('proposal_id')} --target <target>")

    if experience_proposals:
        if agent_proposals:
            lines.append("")
        lines.append(section("Action experience proposals"))
        for proposal in experience_proposals:
            lines.append(experience_proposal_line(proposal))
            explanation = proposal.get("explanation") or {}
            source = one_line(explanation.get("source"), limit=180)
            if source:
                lines.append(f"  Source: {source}")
            lines.append(
                f"  Next: bb proposal accept {proposal.get('proposal_id')} --kind experience --target <target>"
            )
            lines.append(f"        bb proposal reject {proposal.get('proposal_id')} --kind experience --reason <reason>")
            lines.append(f"        bb proposal suppress {proposal.get('proposal_id')} --kind experience --reason <reason>")
    return "\n".join(lines)


def render_proposal_result(data: dict[str, Any], *, action: str) -> str:
    result = data.get("results") or data
    proposal = result.get("proposal") or {}
    lines = [title(f"Proposal {action}")]
    lines.append(f"Proposal: {proposal.get('proposal_id')}  Status: {proposal.get('status')}")
    if action == "accepted":
        submission = result.get("action_submission") or {}
        lines.append(f"Action status: {submission.get('status')}")
        if submission.get("action"):
            lines.append(f"Action: {submission.get('action', {}).get('action_id')}")
    else:
        lines.append("Feedback was stored as learning signal.")
    return "\n".join(lines)
