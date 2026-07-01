"""Read-side contract for materialized Surface Component analysis.

This application boundary exposes persisted component analytics. It does not
run Neo4j/GDS, materialize reports, create proposals, or submit actions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


SURFACE_COMPONENT_SIGNAL_FORMULA_VERSION = "surface-gds-heuristic-signal.v1"
SURFACE_COMPONENT_SIGNAL_KIND = "heuristic"
SURFACE_COMPONENT_SIGNAL_CALIBRATION = "uncalibrated"


class SurfaceComponentAnalysisNotFound(Exception):
    """Raised when no materialized analysis exists for the requested snapshot."""


class SurfaceComponentHeuristicSignals(BaseModel):
    """Uncalibrated graph-derived signals exposed by the read API.

    The materialized PostgreSQL table still uses historical ``*_score`` column
    names. This application DTO intentionally does not. API consumers should
    treat these values as rank-aiding features, not as calibrated priority,
    severity, risk, or learned utility.
    """

    model_config = ConfigDict(extra="forbid")

    formula_version: str = SURFACE_COMPONENT_SIGNAL_FORMULA_VERSION
    kind: str = SURFACE_COMPONENT_SIGNAL_KIND
    calibration_status: str = SURFACE_COMPONENT_SIGNAL_CALIBRATION
    structural_pressure: int | None = None
    drift: int | None = None
    bridge_pressure: int | None = None
    outlier: int | None = None
    coverage: int | None = None
    exploration_pressure: int | None = None


class SurfaceComponentAnalysisItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    component_id: int
    node_count: int
    changed_node_count: int
    signals: SurfaceComponentHeuristicSignals = Field(default_factory=SurfaceComponentHeuristicSignals)
    action_candidate_count: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    action_candidates: list[dict[str, Any]] = Field(default_factory=list)


class SurfaceComponentAnalysisReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_run_id: UUID
    program_id: UUID
    snapshot_id: UUID
    previous_snapshot_id: UUID | None = None
    report_fingerprint: str
    algorithm: str
    algorithm_version: str
    stats: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    item_count: int
    items: list[SurfaceComponentAnalysisItem] = Field(default_factory=list)


class SurfaceComponentAnalysisStore(Protocol):
    async def latest(
        self,
        *,
        program_id: UUID,
        snapshot_id: UUID,
        previous_snapshot_id: UUID | None = None,
    ) -> SurfaceComponentAnalysisReport | None: ...

    async def latest_for_program(
        self,
        *,
        program_id: UUID,
    ) -> SurfaceComponentAnalysisReport | None: ...


class SurfaceComponentAnalysisService:
    """Return persisted Surface Component analytics for UI/API consumers."""

    def __init__(self, store: SurfaceComponentAnalysisStore) -> None:
        self.store = store

    async def latest(
        self,
        *,
        program_id: UUID,
        snapshot_id: UUID,
        previous_snapshot_id: UUID | None = None,
    ) -> SurfaceComponentAnalysisReport:
        report = await self.store.latest(
            program_id=program_id,
            snapshot_id=snapshot_id,
            previous_snapshot_id=previous_snapshot_id,
        )
        if report is None:
            raise SurfaceComponentAnalysisNotFound(
                "Surface component analysis not found for "
                f"program={program_id} snapshot={snapshot_id} previous_snapshot={previous_snapshot_id}"
            )
        return report

    async def latest_for_program(self, *, program_id: UUID) -> SurfaceComponentAnalysisReport:
        report = await self.store.latest_for_program(program_id=program_id)
        if report is None:
            raise SurfaceComponentAnalysisNotFound(
                f"Surface component analysis not found for program={program_id}"
            )
        return report


def surface_component_analysis_boundary() -> dict[str, Any]:
    return {
        "surface": "materialized_read_model",
        "gds_execution": "not_available_from_api_read_endpoint",
        "neo4j_write": "forbidden",
        "postgres_write": "forbidden",
        "proposal_creation": "forbidden",
        "action_submission": "forbidden",
        "tool_execution": "forbidden",
        "source_of_truth": "surface_component_analysis_runs/surface_component_analysis_items",
        "signal_contract": {
            "formula_version": SURFACE_COMPONENT_SIGNAL_FORMULA_VERSION,
            "kind": SURFACE_COMPONENT_SIGNAL_KIND,
            "calibration_status": SURFACE_COMPONENT_SIGNAL_CALIBRATION,
            "not_semantics": ["priority", "severity", "risk", "learned_utility"],
        },
    }
