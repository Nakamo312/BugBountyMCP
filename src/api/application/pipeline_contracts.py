from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID
from typing import Any

from api.application.contract_enums import ExecutionStatus, TerminalOutcome


@dataclass(frozen=True)
class NodeRunClaim:
    """Durable ownership claim for one pipeline node handling one trigger."""

    run_id: UUID | None
    claim_key: str
    status: ExecutionStatus
    terminal_outcome: TerminalOutcome | None = None
    created: bool = False
    blocked_reason: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.terminal_outcome in {
            TerminalOutcome.COMPLETED,
            TerminalOutcome.PARTIAL,
            TerminalOutcome.TOOL_FAILED,
            TerminalOutcome.SKIPPED,
            TerminalOutcome.POLICY_BLOCKED,
        }

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None


@dataclass(frozen=True)
class ScheduledNodeRun:
    """Leased scheduled node run plus reconstructed input event."""

    run_id: UUID
    node_id: str
    event: dict[str, Any]


@dataclass(frozen=True)
class IngestContext:
    """Run and artifact identity supplied to result ingestors."""

    job_id: UUID | None = None
    run_id: UUID | None = None
    correlation_id: UUID | None = None
    raw_artifact_id: UUID | None = None
