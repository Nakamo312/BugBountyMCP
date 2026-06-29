from __future__ import annotations

from enum import Enum


class ActionKind(str, Enum):
    SCAN = "scan"
    ANALYSIS = "analysis"
    TRIAGE = "triage"


class PolicyDecisionStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    REJECTED = "rejected"


class ActionStatus(str, Enum):
    QUEUED = "queued"
    BLOCKED = "blocked"
    REQUIRES_APPROVAL = "requires_approval"
    REJECTED = "rejected"


class ExecutionStatus(str, Enum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    FLUSHING = "flushing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"


class ExecutionMode(str, Enum):
    INLINE = "inline"
    SCHEDULED = "scheduled"


class TerminalOutcome(str, Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    TOOL_FAILED = "tool_failed"
    SKIPPED = "skipped"
    POLICY_BLOCKED = "policy_blocked"


class SafetyLevel(str, Enum):
    PASSIVE = "passive"
    SAFE_ACTIVE = "safe_active"
    ACTIVE = "active"
    SENSITIVE = "sensitive"
