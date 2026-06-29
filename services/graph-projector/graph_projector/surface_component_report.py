from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from .surface_gds import (
    SurfaceComponentActionCandidate,
    SurfaceComponentBridgeProfile,
    SurfaceComponentCoverageProfile,
    SurfaceComponentDrift,
    SurfaceComponentOutlierProfile,
    SurfaceComponentProfile,
    SurfaceGraphMathReader,
)


class Neo4jDriver(Protocol):
    def session(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SurfaceComponentReport:
    """Read-only surface component analytics for CLI/UI display.

    The report is intentionally advisory. It runs graph math over the current
    Neo4j projection and returns component profiles, drift, bridge/outlier,
    coverage and candidate views. It does not create proposals, actions, graph
    facts, projection events, or durable analytical rows.
    """

    program_id: str
    snapshot_id: str
    previous_snapshot_id: str | None
    profiles: tuple[SurfaceComponentProfile, ...]
    drift: tuple[SurfaceComponentDrift, ...]
    bridges: tuple[SurfaceComponentBridgeProfile, ...]
    outliers: tuple[SurfaceComponentOutlierProfile, ...]
    coverage: tuple[SurfaceComponentCoverageProfile, ...]
    action_candidates: tuple[SurfaceComponentActionCandidate, ...]

    @property
    def component_count(self) -> int:
        return len({item.component_id for item in self.profiles})

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "snapshot_id": self.snapshot_id,
            "previous_snapshot_id": self.previous_snapshot_id,
            "component_count": self.component_count,
            "profiles": [asdict(item) for item in self.profiles],
            "drift": [asdict(item) for item in self.drift],
            "bridges": [asdict(item) for item in self.bridges],
            "outliers": [asdict(item) for item in self.outliers],
            "coverage": [asdict(item) for item in self.coverage],
            "action_candidates": [asdict(item) for item in self.action_candidates],
        }


class SurfaceComponentReportReader:
    """Build a read-only surface component report from Neo4j/GDS readers."""

    def __init__(
        self,
        neo4j_driver: Neo4jDriver,
        *,
        neo4j_database: str = "neo4j",
        surface_math_reader: SurfaceGraphMathReader | None = None,
    ) -> None:
        self._neo4j_driver = neo4j_driver
        self._neo4j_database = neo4j_database
        self._surface_math_reader = surface_math_reader or SurfaceGraphMathReader()

    def read(
        self,
        *,
        program_id: str,
        snapshot_id: str,
        previous_snapshot_id: str | None = None,
        limit: int = 10,
        include_action_candidates: bool = True,
        candidate_limit: int = 10,
        component_limit: int = 10,
        similarity_cutoff: float = 0.03,
    ) -> SurfaceComponentReport:
        if not program_id:
            raise ValueError("program_id must not be empty")
        if not snapshot_id:
            raise ValueError("snapshot_id must not be empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if component_limit <= 0:
            raise ValueError("component_limit must be positive")
        if not 0.0 <= similarity_cutoff <= 1.0:
            raise ValueError("similarity_cutoff must be between 0 and 1")

        session_kwargs = {"database": self._neo4j_database} if self._neo4j_database else {}
        with self._neo4j_driver.session(**session_kwargs) as session:
            profiles = self._surface_math_reader.component_profiles(
                session,
                program_id=program_id,
                snapshot_id=snapshot_id,
                limit=limit,
            )
            bridges = self._surface_math_reader.component_bridges(
                session,
                program_id=program_id,
                snapshot_id=snapshot_id,
                limit=limit,
            )
            outliers = self._surface_math_reader.component_outliers(
                session,
                program_id=program_id,
                snapshot_id=snapshot_id,
                limit=limit,
                similarity_cutoff=similarity_cutoff,
            )
            coverage = self._surface_math_reader.component_coverage(
                session,
                program_id=program_id,
                snapshot_id=snapshot_id,
                limit=limit,
            )
            drift: tuple[SurfaceComponentDrift, ...] = ()
            if previous_snapshot_id:
                drift = self._surface_math_reader.component_drift(
                    session,
                    program_id=program_id,
                    previous_snapshot_id=previous_snapshot_id,
                    current_snapshot_id=snapshot_id,
                    limit=limit,
                )
            action_candidates: tuple[SurfaceComponentActionCandidate, ...] = ()
            if include_action_candidates:
                action_candidates = self._surface_math_reader.component_action_candidates(
                    session,
                    program_id=program_id,
                    snapshot_id=snapshot_id,
                    limit=candidate_limit,
                    component_limit=component_limit,
                    similarity_cutoff=similarity_cutoff,
                )
        return SurfaceComponentReport(
            program_id=program_id,
            snapshot_id=snapshot_id,
            previous_snapshot_id=previous_snapshot_id,
            profiles=profiles,
            drift=drift,
            bridges=bridges,
            outliers=outliers,
            coverage=coverage,
            action_candidates=action_candidates,
        )
