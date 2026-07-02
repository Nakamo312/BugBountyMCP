"""Action control-plane transition records."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ActionCancelResult:
    action_id: UUID
    cancelled: bool
    message: str
    campaign_id: UUID | None = None
    correlation_id: UUID | None = None
    workflow_id: UUID | None = None
