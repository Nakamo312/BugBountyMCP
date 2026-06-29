"""Small transport-facing contracts for the agent-task inbox bridge."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID


class AgentTaskInboxStore(Protocol):
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

    async def ack_inbox_message(self, *, message_id: Any) -> None: ...

    async def record_inbox_handoff_error(self, *, message_id: Any, error: str) -> None: ...


@dataclass(frozen=True, slots=True)
class AgentTaskInboxBridgeResult:
    message_id: UUID
    task_id: UUID | None
    outcome: str
    acknowledged: bool
    reply_message_id: UUID | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class AgentTaskInboxProcessorSweep:
    claimed: int = 0
    processed: int = 0
    acknowledged: int = 0
    skipped: int = 0
    failed: int = 0

    def with_result(self, result: AgentTaskInboxBridgeResult) -> "AgentTaskInboxProcessorSweep":
        return AgentTaskInboxProcessorSweep(
            claimed=self.claimed,
            processed=self.processed + int(result.outcome == "processed"),
            acknowledged=self.acknowledged + int(result.acknowledged),
            skipped=self.skipped + int(result.outcome == "skipped"),
            failed=self.failed,
        )

    def with_failure(self) -> "AgentTaskInboxProcessorSweep":
        return AgentTaskInboxProcessorSweep(
            claimed=self.claimed,
            processed=self.processed,
            acknowledged=self.acknowledged,
            skipped=self.skipped,
            failed=self.failed + 1,
        )

    def log_fields(self) -> dict[str, int]:
        return {
            "claimed": self.claimed,
            "processed": self.processed,
            "acknowledged": self.acknowledged,
            "skipped": self.skipped,
            "failed": self.failed,
        }
