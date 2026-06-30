from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


_ENVELOPE_FIELDS = {
    "event",
    "event_id",
    "program_id",
    "targets",
    "target",
    "source",
    "confidence",
    "job_id",
    "run_id",
    "campaign_id",
    "correlation_id",
    "causation_id",
    "expansion_depth",
    "profile",
    "payload",
    "created_at",
}


class EventEnvelope(BaseModel):
    """Stable event envelope for RabbitMQ and future event-store replay."""

    model_config = ConfigDict(extra="allow")

    event_id: UUID = Field(default_factory=uuid4)
    event: str = Field(..., min_length=1)
    program_id: UUID
    targets: list[str] = Field(default_factory=list)
    source: str = "unknown"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    job_id: UUID = Field(default_factory=uuid4)
    run_id: UUID = Field(default_factory=uuid4)
    campaign_id: UUID | None = None
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    expansion_depth: int = Field(default=0, ge=0)
    profile: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("targets")
    @classmethod
    def targets_must_be_strings(cls, value: list[str]) -> list[str]:
        return [target for target in value if isinstance(target, str) and target.strip()]

    @classmethod
    def from_legacy(cls, event: dict[str, Any]) -> "EventEnvelope":
        """Normalize the current loose event dict into a typed envelope."""
        payload = dict(event)
        extra_payload = {
            key: payload.pop(key)
            for key in list(payload)
            if key not in _ENVELOPE_FIELDS
        }
        if "target" in extra_payload and "targets" not in event:
            payload["targets"] = [extra_payload["target"]]
        payload["payload"] = {**extra_payload, **payload.get("payload", {})}
        return cls(**payload)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return a legacy dict without letting payload overwrite envelope fields."""
        data = self.model_dump(mode="json")
        data["target"] = self.targets[0] if self.targets else None
        legacy_payload = {
            str(key): value
            for key, value in self.payload.items()
            if key not in _ENVELOPE_FIELDS
        }
        data.update(legacy_payload)
        return data


@dataclass(frozen=True)
class EventDispatchRecord:
    """Leased delivery work for one stored event and one destination."""

    dispatch_id: UUID
    event_id: UUID
    destination: str
    routing_key: str
    attempts: int
    envelope: EventEnvelope
