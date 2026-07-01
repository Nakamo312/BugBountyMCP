from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping
from uuid import UUID, uuid4

from ...action_experience_probe import ActionExperienceProbeRanking
from ...action_outcome_gds import ActionOutcomeGdsCandidate
from ...proposal_decision_shift import (
    ActionExperienceDecisionShiftResult,
    _decision_distribution_from_rows,
    _decision_shift_payload,
)
from ...proposal_payloads import ActionExperienceProposalReviewResult
from ...proposal_review_priors import (
    ActionExperienceProposalReviewPrior,
    _apply_review_priors_to_surface_candidates,
    _ranked_action_candidates_with_review_priors,
    _review_prior_for_candidate,
    _review_prior_from_row,
    _review_status,
    _confidence,
)
from ...proposal_row_codec import (
    _adapt_json_parameters_for_cursor,
    _optional_text,
    _optional_uuid,
    _optional_uuid_text,
    _required_text,
    _required_uuid_value,
)
from ...proposal_source_features import _source_values
from ...proposal_store_statements import (
    ACTION_EXPERIENCE_FAILED_PROPOSAL_RUN_UPSERT_SQL,
    ACTION_EXPERIENCE_PROPOSAL_REVIEW_UPDATE_SQL,
    ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL,
    ACTION_EXPERIENCE_REVIEW_PRIORS_SQL,
    ACTION_EXPERIENCE_SOURCES_WITHOUT_PROPOSAL_RUN_SQL,
    UPDATE_ACTION_EXPERIENCE_PROPOSAL_RUN_CANDIDATE_COUNT_SQL,
    action_experience_proposal_values,
    failed_proposal_run_values,
    proposal_review_update_values,
    proposal_run_candidate_count_values,
    proposal_run_values,
    review_priors_values,
    sources_without_proposal_run_values,
    surface_component_proposal_values,
)
from ...proposal_store_persistence import (
    fetch_previous_proposal_run_id,
    fetch_proposal_distribution_rows,
    persist_decision_shift,
    upsert_proposal_run,
)
from ...row_codec import cursor_for
from ...surface_gds import SurfaceComponentActionCandidate
from .constants import ACTION_EXPERIENCE_PROPOSAL_SOURCE, SURFACE_COMPONENT_PROPOSAL_SOURCE
from .protocols import Connection, Cursor


_ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL = ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL



class ActionExperienceProposalStore:
    """Durable store for internal experience proposals.

    The store keeps proposals as advisory internal state. It does not enqueue or
    execute actions; future action creation must still pass through the control
    plane, policy, scope, approval, and budget boundaries.
    """

    def __init__(self, connection: Connection, *, produced_by: str = "action-experience-proposal-worker") -> None:
        self._connection = connection
        self._produced_by = _required_text(produced_by, "produced_by")

    def list_sources_without_proposal_run(
        self,
        *,
        limit: int = 100,
        program_id: UUID | str | None = None,
    ) -> list[Mapping[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        cursor = self._cursor()
        cursor.execute(
            ACTION_EXPERIENCE_SOURCES_WITHOUT_PROPOSAL_RUN_SQL,
            sources_without_proposal_run_values(
                limit=limit,
                program_id=_optional_uuid_text(program_id),
            ),
        )
        rows = list(cursor.fetchall())
        self._commit()
        return rows

    def record_ranking(
        self,
        *,
        source: Mapping[str, Any],
        ranking: ActionExperienceProbeRanking,
        review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None = None,
    ) -> tuple[UUID, int]:
        candidates = _ranked_action_candidates_with_review_priors(tuple(ranking.candidates), review_priors)
        source_values = _source_values(source)
        now = datetime.now(UTC)
        cursor = self._cursor()
        stored_run_id = upsert_proposal_run(
            cursor,
            proposal_run_values(
                proposal_run_id=uuid4(),
                source_values=source_values,
                status="completed" if candidates else "no_candidates",
                candidate_count=len(candidates),
                feature_builder_version=ranking.feature_set.builder_version,
                feature_keys=ranking.feature_set.feature_keys,
                graph_counts=ranking.feature_set.graph_counts,
                produced_by=self._produced_by,
                now=now,
            ),
        )
        proposal_count = self._upsert_ranked_proposals(
            cursor,
            proposal_run_id=stored_run_id,
            source_values=source_values,
            ranking=ranking,
            candidates=candidates,
            now=now,
            review_priors=review_priors,
        )
        self._commit()
        return stored_run_id, proposal_count

    def append_component_action_candidates(
        self,
        *,
        proposal_run_id: UUID,
        source: Mapping[str, Any],
        snapshot_id: UUID | str,
        candidates: tuple[SurfaceComponentActionCandidate, ...],
        start_rank: int = 1,
        feature_builder_version: str = "surface-component-action-candidates.v1",
        review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None = None,
    ) -> int:
        """Persist component-scoped advisory candidates into the proposal stream."""

        if start_rank <= 0:
            raise ValueError("start_rank must be positive")
        if not candidates:
            return 0
        cursor = self._cursor()
        proposal_count = self._upsert_surface_component_proposals(
            cursor,
            proposal_run_id=proposal_run_id,
            source_values=_source_values(source),
            snapshot_id=str(UUID(str(snapshot_id))),
            candidates=_apply_review_priors_to_surface_candidates(candidates, review_priors),
            start_rank=start_rank,
            feature_builder_version=feature_builder_version,
            review_priors=review_priors,
            now=datetime.now(UTC),
        )
        self._increment_proposal_run_candidate_count(cursor, proposal_run_id=proposal_run_id, proposal_count=proposal_count)
        self._commit()
        return proposal_count

    def record_decision_shift(
        self,
        *,
        proposal_run_id: UUID | str,
        source: Mapping[str, Any],
        top_k: int = 10,
    ) -> ActionExperienceDecisionShiftResult:
        """Persist decision-distribution drift for a generated proposal run.

        This keeps the qualitative-delta signal at the proposal/run layer. It
        does not execute proposals and does not rewrite ActionOutcome feedback.
        """

        if top_k <= 0:
            raise ValueError("top_k must be positive")
        safe_run_id = _required_uuid_value(proposal_run_id, "proposal_run_id")
        cursor = self._cursor()
        current_rows = fetch_proposal_distribution_rows(cursor, proposal_run_id=safe_run_id, top_k=top_k)
        previous_run_id = fetch_previous_proposal_run_id(cursor, source=source)
        previous_rows = (
            fetch_proposal_distribution_rows(cursor, proposal_run_id=previous_run_id, top_k=top_k)
            if previous_run_id is not None
            else []
        )
        result, payload = self._decision_shift_result(
            proposal_run_id=safe_run_id,
            current_rows=current_rows,
            previous_rows=previous_rows,
            previous_run_id=previous_run_id,
            top_k=top_k,
        )
        persist_decision_shift(cursor, proposal_run_id=safe_run_id, payload=payload)
        self._commit()
        return result

    def load_review_priors(
        self,
        *,
        program_id: UUID | str,
        campaign_id: UUID | str | None = None,
        proposal_source: str | None = None,
    ) -> dict[tuple[str, str], ActionExperienceProposalReviewPrior]:
        """Load operator review priors for advisory proposal ranking."""

        cursor = self._cursor()
        cursor.execute(
            ACTION_EXPERIENCE_REVIEW_PRIORS_SQL,
            review_priors_values(
                program_id=_required_uuid_value(program_id, "program_id"),
                campaign_id=_optional_uuid(campaign_id),
                proposal_source=_optional_text(proposal_source),
            ),
        )
        priors = self._review_priors_from_rows(cursor.fetchall())
        self._commit()
        return priors

    def record_proposal_review(
        self,
        *,
        proposal_id: UUID | str,
        status: str,
        actor: str = "human",
        reason: str | None = None,
        confidence: float = 1.0,
        source: str = "action-experience-proposal-review",
    ) -> ActionExperienceProposalReviewResult | None:
        """Record operator feedback on a pending advisory proposal."""

        cursor = self._cursor()
        values = proposal_review_update_values(
            proposal_id=_required_uuid_value(proposal_id, "proposal_id"),
            status=_review_status(status),
            actor=_required_text(actor, "actor"),
            reason=reason,
            confidence=_confidence(confidence),
            source=_required_text(source, "source"),
            now=datetime.now(UTC),
        )
        cursor.execute(
            ACTION_EXPERIENCE_PROPOSAL_REVIEW_UPDATE_SQL,
            _adapt_json_parameters_for_cursor(cursor, values),
        )
        row = cursor.fetchone()
        self._commit()
        return None if row is None else self._proposal_review_result(row, review_source=str(values["source"]))

    def _review_priors_from_rows(
        self,
        rows: list[Mapping[str, Any]],
    ) -> dict[tuple[str, str], ActionExperienceProposalReviewPrior]:
        priors: dict[tuple[str, str], ActionExperienceProposalReviewPrior] = {}
        for row in rows:
            prior = _review_prior_from_row(row)
            priors[(prior.capability_id, prior.profile_id)] = prior
        return priors

    def _proposal_review_result(
        self,
        row: Mapping[str, Any],
        *,
        review_source: str,
    ) -> ActionExperienceProposalReviewResult:
        return ActionExperienceProposalReviewResult(
            proposal_id=UUID(str(row["id"])),
            previous_status=str(row["previous_status"]),
            status=str(row["status"]),
            capability_id=str(row["capability_id"]),
            profile_id=str(row["profile_id"]),
            review_source=review_source,
        )

    def record_failed_generation(
        self,
        *,
        source: Mapping[str, Any],
        error: str,
        feature_builder_version: str = "action-experience-probe-features.v1",
    ) -> UUID:
        cursor = self._cursor()
        cursor.execute(
            ACTION_EXPERIENCE_FAILED_PROPOSAL_RUN_UPSERT_SQL,
            _adapt_json_parameters_for_cursor(
                cursor,
                failed_proposal_run_values(
                    proposal_run_id=uuid4(),
                    source_values=_source_values(source),
                    feature_builder_version=feature_builder_version,
                    error=error,
                    produced_by=self._produced_by,
                    now=datetime.now(UTC),
                ),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            self._rollback()
            raise RuntimeError("action_experience_proposal_runs failed insert did not return an id")
        self._commit()
        return UUID(str(row["id"]))

    def _upsert_ranked_proposals(
        self,
        cursor: Cursor,
        *,
        proposal_run_id: UUID,
        source_values: dict[str, Any],
        ranking: ActionExperienceProbeRanking,
        candidates: tuple[ActionOutcomeGdsCandidate, ...],
        now: datetime,
        review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None,
    ) -> int:
        for rank, candidate in enumerate(candidates, start=1):
            self._upsert_proposal(
                cursor,
                proposal_run_id=proposal_run_id,
                source_values=source_values,
                candidate=candidate,
                feature_builder_version=ranking.feature_set.builder_version,
                feature_count=len(ranking.feature_set.feature_keys),
                rank=rank,
                now=now,
                review_prior=_review_prior_for_candidate(review_priors, candidate.capability_id, candidate.profile_id),
            )
        return len(candidates)

    def _decision_shift_result(
        self,
        *,
        proposal_run_id: UUID,
        current_rows: list[Mapping[str, Any]],
        previous_rows: list[Mapping[str, Any]],
        previous_run_id: UUID | None,
        top_k: int,
    ) -> tuple[ActionExperienceDecisionShiftResult, dict[str, object]]:
        current_distribution = _decision_distribution_from_rows(current_rows)
        previous_distribution = _decision_distribution_from_rows(previous_rows) if previous_run_id is not None else None
        payload = _decision_shift_payload(
            current=current_distribution,
            previous=previous_distribution,
            previous_run_id=previous_run_id,
            top_k=top_k,
        )
        decision_shift = payload["decision_shift"]
        result = ActionExperienceDecisionShiftResult(
            proposal_run_id=proposal_run_id,
            candidate_count=int(current_distribution["candidate_count"]),
            previous_candidate_count=int(previous_distribution["candidate_count"]) if previous_distribution is not None else 0,
            entropy=float(current_distribution["entropy"]),
            previous_entropy=None if previous_distribution is None else float(previous_distribution["entropy"]),
            entropy_delta=decision_shift["entropy_delta"],
            focus_gain=decision_shift["focus_gain"],
            top_k_overlap=decision_shift["top_k_overlap"],
            total_variation_distance=decision_shift["total_variation_distance"],
            rank_movement_score=decision_shift["rank_movement_score"],
            decision_shift_score=float(decision_shift["decision_shift_score"]),
            decision_volatility_score=float(
                decision_shift.get("decision_volatility_score", decision_shift["decision_shift_score"])
            ),
            metric_name=str(decision_shift.get("metric_name", "decision_volatility")),
            primary_score_field=str(
                decision_shift.get("primary_score_field", "decision_volatility_score")
            ),
            deprecated_score_fields=tuple(
                str(item)
                for item in decision_shift.get("deprecated_score_fields", ("decision_shift_score",))
            ),
        )
        return result, payload

    def _upsert_proposal(
        self,
        cursor: Cursor,
        *,
        proposal_run_id: UUID,
        source_values: dict[str, Any],
        candidate: ActionOutcomeGdsCandidate,
        feature_builder_version: str,
        feature_count: int,
        rank: int,
        now: datetime,
        review_prior: ActionExperienceProposalReviewPrior | None = None,
    ) -> None:
        cursor.execute(
            _ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL,
            _adapt_json_parameters_for_cursor(
                cursor,
                action_experience_proposal_values(
                    proposal_run_id=proposal_run_id,
                    source_values=source_values,
                    candidate=candidate,
                    feature_builder_version=feature_builder_version,
                    feature_count=feature_count,
                    rank=rank,
                    produced_by=self._produced_by,
                    now=now,
                    proposal_source=ACTION_EXPERIENCE_PROPOSAL_SOURCE,
                    review_prior=review_prior,
                ),
            ),
        )

    def _upsert_surface_component_proposals(
        self,
        cursor: Cursor,
        *,
        proposal_run_id: UUID,
        source_values: dict[str, Any],
        snapshot_id: str,
        candidates: tuple[SurfaceComponentActionCandidate, ...],
        start_rank: int,
        feature_builder_version: str,
        review_priors: Mapping[tuple[str, str], ActionExperienceProposalReviewPrior] | None,
        now: datetime,
    ) -> int:
        for rank, candidate in enumerate(candidates, start=start_rank):
            self._upsert_surface_component_proposal(
                cursor,
                proposal_run_id=proposal_run_id,
                source_values=source_values,
                snapshot_id=snapshot_id,
                candidate=candidate,
                feature_builder_version=feature_builder_version,
                rank=rank,
                now=now,
                review_prior=_review_prior_for_candidate(review_priors, candidate.capability_id, candidate.profile_id),
            )
        return len(candidates)

    def _increment_proposal_run_candidate_count(
        self,
        cursor: Cursor,
        *,
        proposal_run_id: UUID,
        proposal_count: int,
    ) -> None:
        cursor.execute(
            UPDATE_ACTION_EXPERIENCE_PROPOSAL_RUN_CANDIDATE_COUNT_SQL,
            proposal_run_candidate_count_values(
                proposal_run_id=proposal_run_id,
                proposal_count=proposal_count,
                now=datetime.now(UTC),
            ),
        )

    def _upsert_surface_component_proposal(
        self,
        cursor: Cursor,
        *,
        proposal_run_id: UUID,
        source_values: dict[str, Any],
        snapshot_id: str,
        candidate: SurfaceComponentActionCandidate,
        feature_builder_version: str,
        rank: int,
        now: datetime,
        review_prior: ActionExperienceProposalReviewPrior | None = None,
    ) -> None:
        cursor.execute(
            _ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL,
            _adapt_json_parameters_for_cursor(
                cursor,
                surface_component_proposal_values(
                    proposal_run_id=proposal_run_id,
                    source_values=source_values,
                    snapshot_id=snapshot_id,
                    candidate=candidate,
                    feature_builder_version=feature_builder_version,
                    rank=rank,
                    produced_by=self._produced_by,
                    now=now,
                    proposal_source=SURFACE_COMPONENT_PROPOSAL_SOURCE,
                    review_prior=review_prior,
                ),
            ),
        )

    def _cursor(self) -> Cursor:
        return cursor_for(self._connection)

    def _commit(self) -> None:
        if hasattr(self._connection, "commit"):
            self._connection.commit()

    def _rollback(self) -> None:
        if hasattr(self._connection, "rollback"):
            self._connection.rollback()

