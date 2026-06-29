from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Protocol
from uuid import UUID


class MaterializationCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchone(self) -> Mapping[str, Any] | None: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class MaterializationConnection(Protocol):
    def cursor(self) -> Any: ...
    def commit(self) -> object: ...
    def rollback(self) -> object: ...


@dataclass(frozen=True)
class SurfaceComponentMaterializationResult:
    analysis_run_id: UUID
    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    report_fingerprint: str
    item_count: int
    action_candidate_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_run_id": str(self.analysis_run_id),
            "program_id": self.program_id,
            "snapshot_id": self.snapshot_id,
            "previous_snapshot_id": self.previous_snapshot_id,
            "report_fingerprint": self.report_fingerprint,
            "item_count": self.item_count,
            "action_candidate_count": self.action_candidate_count,
        }


@dataclass(frozen=True)
class SurfaceComponentMaterializedItem:
    component_id: int
    node_count: int
    changed_node_count: int
    structural_pressure_score: int | None
    drift_score: int | None
    bridge_pressure_score: int | None
    outlier_score: int | None
    coverage_score: int | None
    exploration_priority_score: int | None
    action_candidate_count: int
    metrics_json: dict[str, Any]
    action_candidates_json: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SurfaceComponentMaterializedReport:
    analysis_run_id: UUID
    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    report_fingerprint: str
    algorithm: str
    algorithm_version: str
    stats_json: dict[str, Any]
    settings_json: dict[str, Any]
    created_at: Any
    items: tuple[SurfaceComponentMaterializedItem, ...]

    @property
    def item_count(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_run_id": str(self.analysis_run_id),
            "program_id": self.program_id,
            "snapshot_id": self.snapshot_id,
            "previous_snapshot_id": self.previous_snapshot_id,
            "report_fingerprint": self.report_fingerprint,
            "algorithm": self.algorithm,
            "algorithm_version": self.algorithm_version,
            "stats_json": self.stats_json,
            "settings_json": self.settings_json,
            "created_at": self.created_at.isoformat() if hasattr(self.created_at, "isoformat") else self.created_at,
            "item_count": self.item_count,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class SurfaceComponentMaterializationPayload:
    run_id: UUID
    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    algorithm: str
    algorithm_version: str
    report_fingerprint: str
    settings_json: dict[str, Any]
    stats_json: dict[str, Any]
    items: tuple[SurfaceComponentMaterializedItem, ...]
    action_candidate_count: int

    @property
    def item_count(self) -> int:
        return len(self.items)

    def result(self, analysis_run_id: UUID) -> SurfaceComponentMaterializationResult:
        return SurfaceComponentMaterializationResult(
            analysis_run_id=analysis_run_id,
            program_id=self.program_id,
            snapshot_id=self.snapshot_id,
            previous_snapshot_id=self.previous_snapshot_id,
            report_fingerprint=self.report_fingerprint,
            item_count=self.item_count,
            action_candidate_count=self.action_candidate_count,
        )
