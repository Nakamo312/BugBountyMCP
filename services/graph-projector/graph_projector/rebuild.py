from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from .batch_store import GraphFactBatchStore
from .producers.action_outcomes import ActionOutcomeGraphFactProducer, action_outcome_dedupe_key
from .producers.canonical_inventory import (
    CanonicalInventoryGraphFactProducer,
    canonical_inventory_dedupe_key,
)
from .producers.http_observations import (
    HttpObservationGraphFactProducer,
    http_observations_dedupe_key,
)
from .producers.javascript_references import (
    JavaScriptReferenceGraphFactProducer,
    javascript_reference_dedupe_key,
)
from .producers.raw_artifacts import RawArtifactGraphFactProducer, raw_artifact_dedupe_key
from .producers.surface_map import SurfaceMapGraphFactProducer, surface_map_dedupe_key
from .rebuild_fetches import (
    RebuildConnection,
    fetch_action_outcomes,
    fetch_canonical_inventory,
    fetch_http_observations,
    fetch_javascript_references,
    fetch_raw_artifacts,
    fetch_surface_map,
)
from .rebuild_source_runner import RebuildSourceResult, rebuild_grouped_source, rebuild_row_source

GRAPH_REBUILD_SOURCES = frozenset({
    "raw_artifacts",
    "canonical_inventory",
    "http_observations",
    "javascript_references",
    "action_outcomes",
    "surface_map",
})


@dataclass(frozen=True)
class GraphRebuildResult:
    raw_artifacts_scanned: int = 0
    canonical_inventory_programs_scanned: int = 0
    http_observation_sources_scanned: int = 0
    javascript_reference_sources_scanned: int = 0
    action_outcomes_scanned: int = 0
    surface_snapshots_scanned: int = 0
    enqueued: int = 0
    skipped: int = 0


class GraphRebuildService:
    """Requeue GraphFact batches from canonical PostgreSQL data."""

    def __init__(
        self,
        *,
        connection: RebuildConnection,
        store: GraphFactBatchStore,
        raw_artifact_producer: RawArtifactGraphFactProducer | None = None,
        canonical_inventory_producer: CanonicalInventoryGraphFactProducer | None = None,
        http_observation_producer: HttpObservationGraphFactProducer | None = None,
        javascript_reference_producer: JavaScriptReferenceGraphFactProducer | None = None,
        action_outcome_producer: ActionOutcomeGraphFactProducer | None = None,
        surface_map_producer: SurfaceMapGraphFactProducer | None = None,
    ) -> None:
        self._connection = connection
        self._store = store
        self._raw_artifact_producer = raw_artifact_producer or RawArtifactGraphFactProducer()
        self._canonical_inventory_producer = canonical_inventory_producer or CanonicalInventoryGraphFactProducer()
        self._http_observation_producer = http_observation_producer or HttpObservationGraphFactProducer()
        self._javascript_reference_producer = javascript_reference_producer or JavaScriptReferenceGraphFactProducer()
        self._action_outcome_producer = action_outcome_producer or ActionOutcomeGraphFactProducer()
        self._surface_map_producer = surface_map_producer or SurfaceMapGraphFactProducer()

    def rebuild(
        self,
        *,
        limit: int = 1000,
        program_id: UUID | str | None = None,
        sources: set[str] | frozenset[str] | tuple[str, ...] | list[str] | None = None,
        reset_existing: bool = True,
    ) -> GraphRebuildResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        selected_sources = _normalize_sources(sources)
        results = self._rebuild_selected_sources(
            limit=limit,
            program_id=program_id,
            sources=selected_sources,
            reset_existing=reset_existing,
        )
        return _graph_rebuild_result(results)

    def _rebuild_selected_sources(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> dict[str, RebuildSourceResult]:
        return {
            "raw_artifacts": self._rebuild_raw_artifacts(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
            "canonical_inventory": self._rebuild_canonical_inventory(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
            "http_observations": self._rebuild_http_observations(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
            "javascript_references": self._rebuild_javascript_references(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
            "action_outcomes": self._rebuild_action_outcomes(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
            "surface_map": self._rebuild_surface_map(
                limit=limit,
                program_id=program_id,
                sources=sources,
                reset_existing=reset_existing,
            ),
        }

    def _rebuild_raw_artifacts(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "raw_artifacts" not in sources:
            return RebuildSourceResult()
        rows = fetch_raw_artifacts(self._connection, limit=limit, program_id=program_id)
        return rebuild_row_source(
            rows=rows,
            producer=self._raw_artifact_producer,
            store=self._store,
            dedupe_key=lambda row, parser_version: raw_artifact_dedupe_key(row["id"], parser_version),
            reset_existing=reset_existing,
        )

    def _rebuild_canonical_inventory(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "canonical_inventory" not in sources:
            return RebuildSourceResult()
        rows = fetch_canonical_inventory(self._connection, limit=limit, program_id=program_id)
        return rebuild_grouped_source(
            rows=rows,
            group_key=lambda row: row["program_id"],
            producer=self._canonical_inventory_producer,
            store=self._store,
            dedupe_key=canonical_inventory_dedupe_key,
            reset_existing=reset_existing,
        )

    def _rebuild_http_observations(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "http_observations" not in sources:
            return RebuildSourceResult()
        rows = fetch_http_observations(self._connection, limit=limit, program_id=program_id)
        return rebuild_grouped_source(
            rows=rows,
            group_key=lambda row: row["raw_artifact_id"],
            producer=self._http_observation_producer,
            store=self._store,
            dedupe_key=http_observations_dedupe_key,
            reset_existing=reset_existing,
        )

    def _rebuild_javascript_references(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "javascript_references" not in sources:
            return RebuildSourceResult()
        rows = fetch_javascript_references(self._connection, limit=limit, program_id=program_id)
        return rebuild_grouped_source(
            rows=rows,
            group_key=lambda row: row["raw_artifact_id"],
            producer=self._javascript_reference_producer,
            store=self._store,
            dedupe_key=javascript_reference_dedupe_key,
            reset_existing=reset_existing,
        )

    def _rebuild_action_outcomes(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "action_outcomes" not in sources:
            return RebuildSourceResult()
        rows = fetch_action_outcomes(self._connection, limit=limit, program_id=program_id)
        return rebuild_row_source(
            rows=rows,
            producer=self._action_outcome_producer,
            store=self._store,
            dedupe_key=lambda row, parser_version: action_outcome_dedupe_key(
                row["id"],
                row.get("updated_at"),
                parser_version,
            ),
            reset_existing=reset_existing,
        )

    def _rebuild_surface_map(
        self,
        *,
        limit: int,
        program_id: UUID | str | None,
        sources: frozenset[str],
        reset_existing: bool,
    ) -> RebuildSourceResult:
        if "surface_map" not in sources:
            return RebuildSourceResult()
        rows = fetch_surface_map(self._connection, limit=limit, program_id=program_id)
        return rebuild_grouped_source(
            rows=rows,
            group_key=_surface_snapshot_group_key,
            producer=self._surface_map_producer,
            store=self._store,
            dedupe_key=lambda key, parser_version: surface_map_dedupe_key(key[0], key[1], parser_version),
            reset_existing=reset_existing,
        )


def _surface_snapshot_group_key(row: Mapping[str, Any]) -> tuple[Any, Any]:
    return row["program_id"], row["snapshot_id"]


def _graph_rebuild_result(results: Mapping[str, RebuildSourceResult]) -> GraphRebuildResult:
    return GraphRebuildResult(
        raw_artifacts_scanned=results["raw_artifacts"].rows_scanned,
        canonical_inventory_programs_scanned=results["canonical_inventory"].groups_scanned,
        http_observation_sources_scanned=results["http_observations"].groups_scanned,
        javascript_reference_sources_scanned=results["javascript_references"].groups_scanned,
        action_outcomes_scanned=results["action_outcomes"].rows_scanned,
        surface_snapshots_scanned=results["surface_map"].groups_scanned,
        enqueued=sum(result.enqueued for result in results.values()),
        skipped=sum(result.skipped for result in results.values()),
    )


def _normalize_sources(sources: set[str] | frozenset[str] | tuple[str, ...] | list[str] | None) -> frozenset[str]:
    if sources is None:
        return GRAPH_REBUILD_SOURCES
    selected = frozenset(str(source) for source in sources)
    if not selected:
        raise ValueError("sources must not be empty")
    unknown = selected - GRAPH_REBUILD_SOURCES
    if unknown:
        raise ValueError(f"unknown graph rebuild sources: {', '.join(sorted(unknown))}")
    return selected
