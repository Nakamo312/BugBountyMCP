from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID

from .surface_component_materialization import SurfaceComponentMaterializationResult


class SurfaceAnalysisEventCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchone(self) -> Mapping[str, Any] | None: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class SurfaceAnalysisEventConnection(Protocol):
    def cursor(self) -> SurfaceAnalysisEventCursor: ...
    def commit(self) -> object: ...
    def rollback(self) -> object: ...


@dataclass(frozen=True)
class SurfaceComponentAnalysisEvent:
    id: UUID
    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    event_type: str
    analysis_version: str
    settings_json: dict[str, Any]
    attempts: int


@dataclass(frozen=True)
class ClaimedSurfaceComponentAnalysisEvent:
    event: SurfaceComponentAnalysisEvent
    attempts: int


@dataclass(frozen=True)
class SurfaceComponentAnalysisEventProcessResult:
    status: str
    event_id: UUID | None = None
    materialization: SurfaceComponentMaterializationResult | None = None
    error: str | None = None


@dataclass(frozen=True)
class SurfaceComponentAnalysisEventLoopResult:
    processed: int = 0
    failed: int = 0
    dead: int = 0
    empty: int = 0
    iterations: int = 0
    last_status: str | None = None
