"""Declarative scheduler for periodic control-plane actions."""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.application.contracts import ActionKind, ActionRequest
from api.application.services.action import ActionService
from api.application.services.action_catalog import ActionCatalogService

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_CONFIG_PATH = Path(__file__).with_name("scheduler.yaml")
_DURATION_RE = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>s|m|h|d)$")
_DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}


class ScheduledActionSpec(BaseModel):
    """One periodic action declaration loaded from YAML."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    interval: int = Field(gt=0)
    run_on_start: bool = False
    event: str = Field(min_length=1)
    program_id: UUID
    targets: list[str] = Field(min_length=1)
    profile_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = "scheduler"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("interval", mode="before")
    @classmethod
    def parse_interval(cls, value: Any) -> int:
        if isinstance(value, int):
            return value
        if not isinstance(value, str):
            raise ValueError("interval must be seconds or a duration string like 15m")
        match = _DURATION_RE.match(value.strip())
        if not match:
            raise ValueError("interval must use s, m, h, or d units, e.g. 30m")
        return int(match.group("value")) * _DURATION_UNITS[match.group("unit")]

    @field_validator("targets")
    @classmethod
    def targets_must_be_non_blank(cls, value: list[str]) -> list[str]:
        normalized = [target.strip() for target in value if isinstance(target, str) and target.strip()]
        if not normalized:
            raise ValueError("targets must contain at least one non-empty target")
        return normalized


class SchedulerConfig(BaseModel):
    """Root scheduler configuration."""

    model_config = ConfigDict(extra="forbid")

    schedules: dict[str, ScheduledActionSpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def schedule_names_must_be_non_blank(self) -> "SchedulerConfig":
        blank = [name for name in self.schedules if not name.strip()]
        if blank:
            raise ValueError("schedule names must be non-empty")
        return self


def load_scheduler_config(path: str | Path | None = None) -> SchedulerConfig:
    config_path = Path(path) if path else DEFAULT_SCHEDULER_CONFIG_PATH
    if not config_path.exists():
        return SchedulerConfig()
    raw: dict[str, Any] | None = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    return SchedulerConfig.model_validate(raw)


class ActionScheduler:
    """Small in-process scheduler that submits actions through policy."""

    def __init__(
        self,
        action_service: ActionService,
        catalog_service: ActionCatalogService,
        config: SchedulerConfig,
        *,
        tick_seconds: float = 5.0,
    ):
        self.action_service = action_service
        self.catalog_service = catalog_service
        self.config = config
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None
        self._next_due: dict[str, float] = {}

    def start(self) -> None:
        if self._task is not None:
            return

        now = monotonic()
        self._next_due = {
            name: now if spec.run_on_start else now + spec.interval
            for name, spec in self.config.schedules.items()
            if spec.enabled
        }
        if not self._next_due:
            logger.info("ActionScheduler has no enabled schedules")
            return
        self._task = asyncio.create_task(self._run(), name="action-scheduler")
        logger.info("ActionScheduler started with %d enabled schedules", len(self._next_due))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        logger.info("ActionScheduler stopped")

    async def tick_once(self, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        if not self._next_due:
            self._next_due = {
                name: current if spec.run_on_start else current + spec.interval
                for name, spec in self.config.schedules.items()
                if spec.enabled
            }

        for name, spec in self.config.schedules.items():
            if not spec.enabled:
                continue
            if self._next_due.get(name, current + spec.interval) > current:
                continue
            self._next_due[name] = current + spec.interval
            await self._submit(name, spec)

    async def _run(self) -> None:
        while True:
            await self.tick_once()
            await asyncio.sleep(self.tick_seconds)

    async def _submit(self, name: str, spec: ScheduledActionSpec) -> None:
        logger.info("Submitting scheduled action '%s' event=%s", name, spec.event)
        try:
            catalog_item = await self.catalog_service.find_detail_by_event(
                event=spec.event,
                profile=spec.profile_id,
            )
            action = ActionRequest(
                kind=ActionKind.SCAN,
                program_id=spec.program_id,
                catalog_id=catalog_item.id,
                targets=spec.targets,
                options=spec.options,
                requested_by=spec.requested_by,
            )
            submission = await self.action_service.request_action(
                action,
                confidence=spec.confidence,
            )
            logger.info(
                "Scheduled action '%s' submitted with status=%s action_id=%s",
                name,
                submission.status.value,
                submission.action_id,
            )
        except Exception:
            logger.exception("Scheduled action '%s' failed", name)
