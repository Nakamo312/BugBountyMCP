"""Research inbox transport contracts and result models.

This module is the stable application boundary for the research inbox handoff.
The inbox owns delivery and leasing; graph implementations own execution after a
message is handed off.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from api.application.hypotheses import HypothesisBuildRequest
from api.application.projections import ProjectionKey


class ResearchExecutionGraph(Protocol):
    async def ainvoke(
        self,
        request: HypothesisBuildRequest,
        *,
        thread_id: str,
        required_projections: tuple[ProjectionKey, ...] = (),
    ) -> dict[str, Any]: ...

    async def aresume(self, *, thread_id: str) -> dict[str, Any]: ...

    async def aget_state(self, *, thread_id: str) -> Any: ...


class AgentInboxAckStore(Protocol):
    async def ack_inbox_message(self, *, message_id: Any) -> None: ...


class AgentWorkflowRunStatusReader(Protocol):
    async def get_workflow_run_status(self, *, run_id: Any) -> str | None: ...


class AgentInboxFailureStore(Protocol):
    async def record_inbox_handoff_error(
        self,
        *,
        message_id: Any,
        error: str,
    ) -> None: ...


class AgentInboxClaimStore(
    AgentInboxAckStore,
    AgentInboxFailureStore,
    AgentWorkflowRunStatusReader,
    Protocol,
):
    async def claim_inbox(
        self,
        *,
        program_id: Any | None = None,
        consumer_id: str,
        lease_seconds: int = 300,
        campaign_id: Any | None = None,
        correlation_id: Any | None = None,
        inbox_key: str | None = None,
        message_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class ResearchInboxBridgeResult:
    message_id: UUID
    thread_id: str
    outcome: str
    acknowledged: bool
    graph_result: dict[str, Any] | None = None
    action: str | None = None
    reason_code: str | None = None
    workflow_status: str | None = None

    @property
    def mode(self) -> str:
        """Compatibility alias for older callers.

        New code should use ``outcome`` and ``reason_code``.
        """

        if self.outcome == "started":
            return "start"
        if self.outcome == "resumed":
            return "resume"
        if self.outcome == "skipped_terminal_workflow" and self.reason_code:
            return self.reason_code
        return self.outcome


@dataclass(frozen=True, slots=True)
class ResearchInboxProcessorSweep:
    claimed: int = 0
    handed_off: int = 0
    acknowledged: int = 0
    started: int = 0
    resumed: int = 0
    already_started: int = 0
    skipped_terminal_workflow: int = 0
    failed: int = 0

    @property
    def processed(self) -> int:
        """Compatibility count for older callers that only need success count."""

        return self.handed_off

    def with_result(self, result: ResearchInboxBridgeResult) -> "ResearchInboxProcessorSweep":
        outcome_updates = {
            "started": self.started,
            "resumed": self.resumed,
            "already_started": self.already_started,
            "skipped_terminal_workflow": self.skipped_terminal_workflow,
        }
        if result.outcome in outcome_updates:
            outcome_updates[result.outcome] += 1
        return ResearchInboxProcessorSweep(
            claimed=self.claimed,
            handed_off=self.handed_off + 1,
            acknowledged=self.acknowledged + int(result.acknowledged),
            started=outcome_updates["started"],
            resumed=outcome_updates["resumed"],
            already_started=outcome_updates["already_started"],
            skipped_terminal_workflow=outcome_updates["skipped_terminal_workflow"],
            failed=self.failed,
        )

    def with_failure(self) -> "ResearchInboxProcessorSweep":
        return ResearchInboxProcessorSweep(
            claimed=self.claimed,
            handed_off=self.handed_off,
            acknowledged=self.acknowledged,
            started=self.started,
            resumed=self.resumed,
            already_started=self.already_started,
            skipped_terminal_workflow=self.skipped_terminal_workflow,
            failed=self.failed + 1,
        )

    def log_fields(self) -> dict[str, int]:
        """Return stable numeric fields for one-line sweep logging."""

        return {
            "claimed": self.claimed,
            "handed_off": self.handed_off,
            "acknowledged": self.acknowledged,
            "started": self.started,
            "resumed": self.resumed,
            "already_started": self.already_started,
            "skipped_terminal_workflow": self.skipped_terminal_workflow,
            "failed": self.failed,
        }
