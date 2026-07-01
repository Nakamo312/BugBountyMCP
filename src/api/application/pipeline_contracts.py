from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from api.application.contract_enums import ExecutionMode, ExecutionStatus, TerminalOutcome


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
class NodeRunClaimRequest:
    """Single command for claiming a pipeline node run."""

    claim_key: str
    job_id: UUID
    program_id: UUID
    node_id: str
    event_name: str
    trigger_event_id: UUID
    input_fingerprint: str
    target_fingerprint: str
    execution_mode: ExecutionMode = ExecutionMode.INLINE
    next_run_at: datetime | None = None
    target_count: int | None = None
    run_payload: Mapping[str, Any] | None = None
    work_key: str | None = None
    coalesced_trigger: Mapping[str, Any] | None = None
    retry_policy: dict | None = None
    campaign_id: UUID | None = None
    expansion_depth: int = 0
    max_expansion_depth: int | None = None
    cooldown_seconds: int | float = 0
    token_cost: int | float = 1


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
