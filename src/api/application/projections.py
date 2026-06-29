"""Typed projection lag contracts used by workflow wait conditions."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Sequence
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ProjectionKey:
    projection_type: str
    projection_name: str


@dataclass(frozen=True, slots=True)
class ProjectionLagState:
    key: ProjectionKey
    status: str
    source_watermark: str
    applied_watermark: str | None
    lag_count: int


@dataclass(frozen=True, slots=True)
class ProjectionReadiness:
    ready: bool
    missing: tuple[ProjectionKey, ...]
    lagging: tuple[ProjectionKey, ...]
    failed: tuple[ProjectionKey, ...]


class ProjectionStateReader(Protocol):
    async def list_states(
        self,
        *,
        program_id: Any,
        required: Sequence[ProjectionKey],
    ) -> list[ProjectionLagState]: ...


class ProjectionReadinessService:
    def __init__(self, reader: ProjectionStateReader) -> None:
        self.reader = reader

    async def evaluate(
        self,
        *,
        program_id: Any,
        required: Sequence[ProjectionKey],
    ) -> ProjectionReadiness:
        states = await self.reader.list_states(program_id=program_id, required=required)
        return evaluate_projection_readiness(states=states, required=required)


def evaluate_projection_readiness(
    *,
    states: Iterable[ProjectionLagState],
    required: Iterable[ProjectionKey],
) -> ProjectionReadiness:
    """Return a deterministic readiness result for named read projections."""
    by_key = {state.key: state for state in states}
    missing: list[ProjectionKey] = []
    lagging: list[ProjectionKey] = []
    failed: list[ProjectionKey] = []

    for key in required:
        state = by_key.get(key)
        if state is None:
            missing.append(key)
        elif state.status == "failed":
            failed.append(key)
        elif (
            state.status != "ready"
            or state.lag_count != 0
            or state.source_watermark != state.applied_watermark
        ):
            lagging.append(key)

    return ProjectionReadiness(
        ready=not missing and not lagging and not failed,
        missing=tuple(missing),
        lagging=tuple(lagging),
        failed=tuple(failed),
    )
