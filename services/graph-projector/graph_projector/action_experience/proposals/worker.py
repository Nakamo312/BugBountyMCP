from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from ...action_experience_probe import ActionExperienceProbeRanker, ActionExperienceProbeRanking
from ...proposal_payloads import ActionExperienceProposalWorkerResult
from ...proposal_review_priors import ActionExperienceProposalReviewPrior
from ...proposal_row_codec import _optional_int, _optional_text, _optional_uuid, _required_uuid
from ...proposal_source_features import _source_probe_feature_keys
from ...surface_gds import SurfaceGraphMathReader
from .constants import ACTION_EXPERIENCE_PROPOSAL_SOURCE, SURFACE_COMPONENT_PROPOSAL_SOURCE
from .protocols import Neo4jDriver
from .store import ActionExperienceProposalStore


class ActionExperienceProposalWorker:
    """Build internal next-action proposals from graph experience.

    The worker reads completed action outcomes, asks Neo4j-backed experience
    readers for capability/profile candidates using current-state feature keys,
    and persists advisory proposals. It never creates ToolActionRequest rows and
    never executes tools.
    """

    def __init__(
        self,
        *,
        store: ActionExperienceProposalStore,
        neo4j_driver: Neo4jDriver,
        neo4j_database: str = "neo4j",
        ranker: ActionExperienceProbeRanker | None = None,
        surface_math_reader: SurfaceGraphMathReader | None = None,
        candidate_limit: int = 5,
        similarity_cutoff: float = 0.1,
        candidate_profile_limit: int = 100,
        surface_component_candidate_limit: int = 5,
        surface_component_limit: int = 10,
        surface_similarity_cutoff: float = 0.03,
    ) -> None:
        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if not 0 <= similarity_cutoff <= 1:
            raise ValueError("similarity_cutoff must be between 0 and 1")
        if candidate_profile_limit <= 0:
            raise ValueError("candidate_profile_limit must be positive")
        if surface_component_candidate_limit <= 0:
            raise ValueError("surface_component_candidate_limit must be positive")
        if surface_component_limit <= 0:
            raise ValueError("surface_component_limit must be positive")
        if not 0 <= surface_similarity_cutoff <= 1:
            raise ValueError("surface_similarity_cutoff must be between 0 and 1")
        self._store = store
        self._neo4j_driver = neo4j_driver
        self._neo4j_database = neo4j_database
        self._ranker = ranker or ActionExperienceProbeRanker()
        self._surface_math_reader = surface_math_reader or SurfaceGraphMathReader()
        self._candidate_limit = candidate_limit
        self._similarity_cutoff = similarity_cutoff
        self._candidate_profile_limit = candidate_profile_limit
        self._surface_component_candidate_limit = surface_component_candidate_limit
        self._surface_component_limit = surface_component_limit
        self._surface_similarity_cutoff = surface_similarity_cutoff

    def propose_once(self, *, limit: int = 100, program_id: UUID | str | None = None) -> ActionExperienceProposalWorkerResult:
        if limit <= 0:
            raise ValueError("limit must be positive")
        sources = self._store.list_sources_without_proposal_run(limit=limit, program_id=program_id)
        proposal_runs = proposals = no_candidates = failed = 0
        for source in sources:
            try:
                ranking = self._rank_source(source)
                base_review_priors = self._load_review_priors(
                    source=source,
                    proposal_source=ACTION_EXPERIENCE_PROPOSAL_SOURCE,
                )
                if base_review_priors:
                    proposal_run_id, proposal_count = self._store.record_ranking(
                        source=source,
                        ranking=ranking,
                        review_priors=base_review_priors,
                    )
                else:
                    proposal_run_id, proposal_count = self._store.record_ranking(source=source, ranking=ranking)
                proposal_count += self._append_surface_component_candidates(
                    source=source,
                    proposal_run_id=proposal_run_id,
                    start_rank=len(ranking.candidates) + 1,
                )
                self._record_decision_shift(source=source, proposal_run_id=proposal_run_id)
                proposal_runs += 1
                proposals += proposal_count
                if proposal_count == 0:
                    no_candidates += 1
            except Exception as exc:
                self._store.record_failed_generation(source=source, error=str(exc))
                failed += 1
        return ActionExperienceProposalWorkerResult(
            scanned=len(sources),
            proposal_runs=proposal_runs,
            proposals=proposals,
            no_candidates=no_candidates,
            failed=failed,
        )

    def _record_decision_shift(
        self,
        *,
        source: Mapping[str, Any],
        proposal_run_id: UUID,
    ) -> None:
        recorder = getattr(self._store, "record_decision_shift", None)
        if recorder is None:
            return
        recorder(proposal_run_id=proposal_run_id, source=source)

    def _load_review_priors(
        self,
        *,
        source: Mapping[str, Any],
        proposal_source: str,
    ) -> dict[tuple[str, str], ActionExperienceProposalReviewPrior]:
        loader = getattr(self._store, "load_review_priors", None)
        if loader is None:
            return {}
        return loader(
            program_id=_required_uuid(source, "program_id"),
            campaign_id=source.get("campaign_id"),
            proposal_source=proposal_source,
        )

    def _rank_source(self, source: Mapping[str, Any]) -> ActionExperienceProbeRanking:
        session_kwargs = {"database": self._neo4j_database} if self._neo4j_database else {}
        with self._neo4j_driver.session(**session_kwargs) as session:
            return self._ranker.rank_for_current_graph_state(
                session,
                program_id=str(_required_uuid(source, "program_id")),
                node_id=_optional_text(source.get("node_id")),
                event_name=_optional_text(source.get("event_name")),
                target_count=_optional_int(source.get("target_count")),
                base_feature_keys=_source_probe_feature_keys(source),
                probe_id=f"outcome-{_required_uuid(source, 'id')}",
                limit=self._candidate_limit,
                similarity_cutoff=self._similarity_cutoff,
                candidate_profile_limit=self._candidate_profile_limit,
            )

    def _append_surface_component_candidates(
        self,
        *,
        source: Mapping[str, Any],
        proposal_run_id: UUID,
        start_rank: int,
    ) -> int:
        snapshot_id = _optional_uuid(source.get("after_surface_snapshot_id"))
        if snapshot_id is None:
            return 0
        session_kwargs = {"database": self._neo4j_database} if self._neo4j_database else {}
        with self._neo4j_driver.session(**session_kwargs) as session:
            candidates = self._surface_math_reader.component_action_candidates(
                session,
                program_id=str(_required_uuid(source, "program_id")),
                snapshot_id=str(snapshot_id),
                probe_id=f"surface-component-outcome-{_required_uuid(source, 'id')}",
                limit=self._surface_component_candidate_limit,
                component_limit=self._surface_component_limit,
                similarity_cutoff=self._surface_similarity_cutoff,
            )
        if not candidates:
            return 0
        review_priors = self._load_review_priors(
            source=source,
            proposal_source=SURFACE_COMPONENT_PROPOSAL_SOURCE,
        )
        if review_priors:
            return self._store.append_component_action_candidates(
                proposal_run_id=proposal_run_id,
                source=source,
                snapshot_id=snapshot_id,
                candidates=candidates,
                start_rank=start_rank,
                review_priors=review_priors,
            )
        return self._store.append_component_action_candidates(
            proposal_run_id=proposal_run_id,
            source=source,
            snapshot_id=snapshot_id,
            candidates=candidates,
            start_rank=start_rank,
        )
