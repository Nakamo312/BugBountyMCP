from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("sqlalchemy")

from api.infrastructure.adapters.orm import action_experience_proposal_runs, action_experience_proposals
from tests.infrastructure.action_experience_support import (
    FakeDriver,
    FakeRanker,
    RecordingConnection,
    ranking as _ranking,
    source_row as _source_row,
    symbols as _symbols,
)


def test_proposal_store_persists_ranking_with_generic_explanation() -> None:
    _, _, _, Store, _, _, proposal_key = _symbols()
    connection = RecordingConnection()
    source = _source_row()

    proposal_run_id, proposal_count = Store(connection).record_ranking(source=source, ranking=_ranking(candidate_count=2))

    assert isinstance(proposal_run_id, UUID)
    assert proposal_count == 2
    assert connection.commits == 1
    assert len(connection.cursor_obj.calls) == 3
    proposal_params = connection.cursor_obj.calls[1][1]
    assert proposal_params["proposal_key"] == proposal_key(
        source["id"],
        "web.crawl.0",
        "passive-default",
        "action-experience-probe-features.v1",
    )
    assert proposal_params["explanation"]["source"] == "neo4j-jaccard-action-experience"
    assert "state/action pairs" in proposal_params["explanation"]["candidate_basis"]




def test_proposal_store_applies_review_prior_when_persisting_ranking() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience.proposals import ActionExperienceProposalReviewPrior

    connection = RecordingConnection()
    source = _source_row()
    prior = ActionExperienceProposalReviewPrior(
        capability_id="web.crawl.0",
        profile_id="passive-default",
        suppressed_count=5,
        suppressed_confidence=5.0,
    )

    Store(connection).record_ranking(
        source=source,
        ranking=_ranking(candidate_count=1),
        review_priors={("web.crawl.0", "passive-default"): prior},
    )

    proposal_params = connection.cursor_obj.calls[1][1]
    assert proposal_params["utility_score"] == 4.6875
    action_candidate = proposal_params["explanation"]["action_candidate"]
    assert action_candidate["utility_score_semantics"] == (
        "outcome-derived historical utility signal; not adjusted by operator review prior"
    )
    assert action_candidate["rank_score"] < 4.6875
    assert action_candidate["base_utility_score"] == 4.6875
    assert action_candidate["adjusted_rank_score"] == action_candidate["rank_score"]
    assert action_candidate["review_prior_multiplier"] < 1.0
    assert proposal_params["explanation"]["proposal_review_prior"]["suppressed_count"] == 5


def test_proposal_store_appends_surface_component_candidates_to_existing_run() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_gds import SurfaceComponentActionCandidate

    connection = RecordingConnection()
    source = _source_row()
    proposal_run_id = uuid4()
    snapshot_id = uuid4()
    candidate = SurfaceComponentActionCandidate(
        component_id=7,
        node_count=9,
        changed_node_count=3,
        max_novelty_score=80,
        capability_id="katana",
        profile_id="safe-crawl",
        sample_count=4,
        avg_similarity=0.42,
        avg_information_gain_score=5.0,
        human_positive_rate=0.25,
        human_stop_rate=0.0,
        utility_score=2.625,
        component_attention_score=70,
        candidate_score=66,
    )

    count = Store(connection).append_component_action_candidates(
        proposal_run_id=proposal_run_id,
        source=source,
        snapshot_id=snapshot_id,
        candidates=(candidate,),
        start_rank=3,
    )

    assert count == 1
    assert connection.commits == 1
    assert len(connection.cursor_obj.calls) == 2
    insert_query, insert_params = connection.cursor_obj.calls[0]
    assert "INSERT INTO action_experience_proposals" in insert_query
    assert insert_params["proposal_run_id"] == proposal_run_id
    assert insert_params["rank"] == 3
    assert insert_params["capability_id"] == "katana"
    assert insert_params["profile_id"] == "safe-crawl"
    assert insert_params["utility_score"] == 2.625
    assert insert_params["explanation"]["surface_candidate"]["candidate_score"] == 66
    assert insert_params["explanation"]["surface_candidate"]["candidate_score_semantics"] == "uncalibrated heuristic ranking signal stored in the legacy candidate_score field; not outcome utility"
    assert insert_params["proposal_key"].startswith("surface-component-action-proposal:")
    assert insert_params["explanation"]["source"] == "neo4j-jaccard-surface-component"
    assert insert_params["explanation"]["snapshot_id"] == str(snapshot_id)
    assert insert_params["explanation"]["component_id"] == 7
    update_query, update_params = connection.cursor_obj.calls[1]
    assert "UPDATE action_experience_proposal_runs" in update_query
    assert update_params["proposal_count"] == 1
    assert update_params["proposal_run_id"] == proposal_run_id




def test_proposal_store_applies_review_prior_when_persisting_surface_component_candidate() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience.proposals import ActionExperienceProposalReviewPrior
    from graph_projector.surface_gds import SurfaceComponentActionCandidate

    connection = RecordingConnection()
    source = _source_row()
    candidate = SurfaceComponentActionCandidate(
        component_id=7,
        node_count=9,
        changed_node_count=3,
        max_novelty_score=80,
        capability_id="katana",
        profile_id="safe-crawl",
        sample_count=4,
        avg_similarity=0.42,
        avg_information_gain_score=5.0,
        human_positive_rate=0.25,
        human_stop_rate=0.0,
        utility_score=2.625,
        component_attention_score=70,
        candidate_score=66,
    )
    prior = ActionExperienceProposalReviewPrior(
        capability_id="katana",
        profile_id="safe-crawl",
        rejected_count=4,
        rejected_confidence=4.0,
    )

    Store(connection).append_component_action_candidates(
        proposal_run_id=uuid4(),
        source=source,
        snapshot_id=uuid4(),
        candidates=(candidate,),
        review_priors={("katana", "safe-crawl"): prior},
    )

    proposal_params = connection.cursor_obj.calls[0][1]
    assert proposal_params["utility_score"] == 2.625
    surface = proposal_params["explanation"]["surface_candidate"]
    assert surface["utility_score_semantics"] == (
        "outcome-derived historical utility signal; not adjusted by operator review prior"
    )
    assert surface["candidate_score"] < 66
    assert surface["base_candidate_score"] == 66
    assert surface["adjusted_candidate_score"] == surface["candidate_score"]
    assert surface["score_features_stage"] == "post_review_prior"
    assert surface["review_prior_multiplier"] < 1.0
    assert surface["candidate_score_features"]["base_candidate_score"] == 66
    assert surface["candidate_score_features"]["adjusted_candidate_score"] == surface["candidate_score"]
    assert proposal_params["explanation"]["proposal_review_prior"]["rejected_count"] == 4


def test_proposal_store_records_proposal_review_without_rewriting_source_outcome() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    connection = RecordingConnection()
    proposal_id = uuid4()
    connection.cursor_obj._fetchone_values.append(
        {
            "id": proposal_id,
            "previous_status": "pending",
            "status": "suppressed",
            "capability_id": "katana",
            "profile_id": "safe-crawl",
        }
    )

    result = Store(connection).record_proposal_review(
        proposal_id=proposal_id,
        status="suppressed",
        actor="operator",
        reason="not useful for this component",
        confidence=0.8,
    )

    assert result is not None
    assert result.proposal_id == proposal_id
    assert result.status == "suppressed"
    assert result.capability_id == "katana"
    query, params = connection.cursor_obj.calls[0]
    assert "UPDATE action_experience_proposals" in query
    assert "action_outcome_feedback_events" not in query
    assert "UPDATE action_outcomes" not in query
    assert params["proposal_id"] == proposal_id
    assert params["status"] == "suppressed"
    assert params["review_payload"]["review"]["actor"] == "operator"
    assert params["review_payload"]["review"]["confidence"] == 0.8
    assert connection.commits == 1


def test_proposal_upserts_preserve_reviewed_status_and_review_payload() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    connection = RecordingConnection()
    source = _source_row()

    Store(connection).record_ranking(source=source, ranking=_ranking(candidate_count=1))

    insert_query = connection.cursor_obj.calls[1][0]
    assert "ON CONFLICT (proposal_key) DO UPDATE" in insert_query
    assert "action_experience_proposals.status IN ('accepting', 'accepted', 'accept_failed', 'rejected', 'suppressed')" in insert_query
    assert "THEN action_experience_proposals.status" in insert_query
    assert "THEN action_experience_proposals.proposal_run_id" in insert_query
    assert "THEN action_experience_proposals.rank" in insert_query
    assert "THEN action_experience_proposals.utility_score" in insert_query
    assert "THEN action_experience_proposals.explanation" in insert_query
    assert "THEN action_experience_proposals.produced_by" in insert_query


def test_action_experience_proposal_upsert_uses_shared_statement_for_all_sources() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    import graph_projector.action_experience.proposals as proposals
    from graph_projector.surface_gds import SurfaceComponentActionCandidate

    assert proposals._ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL.count("INSERT INTO action_experience_proposals") == 1

    statement_source = Path("services/graph-projector/graph_projector/proposal_upsert_statements.py").read_text(
        encoding="utf-8"
    )
    store_source = Path("services/graph-projector/graph_projector/action_experience/proposals/store.py").read_text(
        encoding="utf-8"
    )
    assert statement_source.count("INSERT INTO action_experience_proposals") == 1
    assert store_source.count("INSERT INTO action_experience_proposals") == 0

    ranking_connection = RecordingConnection()
    source_row = _source_row()
    proposals.ActionExperienceProposalStore(ranking_connection).record_ranking(
        source=source_row, ranking=_ranking(candidate_count=1)
    )
    ranking_insert_query = ranking_connection.cursor_obj.calls[1][0]

    surface_connection = RecordingConnection()
    surface_candidate = SurfaceComponentActionCandidate(
        component_id=7,
        node_count=9,
        changed_node_count=3,
        max_novelty_score=80,
        capability_id="katana",
        profile_id="safe-crawl",
        sample_count=4,
        avg_similarity=0.42,
        avg_information_gain_score=5.0,
        human_positive_rate=0.25,
        human_stop_rate=0.0,
        utility_score=2.625,
        component_attention_score=70,
        candidate_score=66,
    )
    proposals.ActionExperienceProposalStore(surface_connection).append_component_action_candidates(
        proposal_run_id=uuid4(),
        source=source_row,
        snapshot_id=uuid4(),
        candidates=(surface_candidate,),
        start_rank=1,
    )
    surface_insert_query = surface_connection.cursor_obj.calls[0][0]

    assert ranking_insert_query == proposals._ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL
    assert surface_insert_query == proposals._ACTION_EXPERIENCE_PROPOSAL_UPSERT_SQL


def test_proposal_store_loads_review_priors_without_touching_outcomes() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    connection = RecordingConnection()
    program_id = uuid4()
    campaign_id = uuid4()
    connection.cursor_obj._fetchall_values.append(
        [
            {
                "capability_id": "katana",
                "profile_id": "safe-crawl",
                "accepted_count": 1,
                "rejected_count": 2,
                "suppressed_count": 1,
                "accepted_confidence": 0.5,
                "rejected_confidence": 1.6,
                "suppressed_confidence": 1.0,
            }
        ]
    )

    priors = Store(connection).load_review_priors(
        program_id=program_id,
        campaign_id=campaign_id,
        proposal_source="neo4j-jaccard-surface-component",
    )

    query, params = connection.cursor_obj.calls[0]
    assert "FROM action_experience_proposals" in query
    assert "UPDATE action_outcomes" not in query
    assert "action_outcome_feedback_events" not in query
    assert "explanation->>'source'" in query
    assert params["program_id"] == program_id
    assert params["campaign_id"] == campaign_id
    assert params["proposal_source"] == "neo4j-jaccard-surface-component"
    prior = priors[("katana", "safe-crawl")]
    assert prior.review_count == 4
    assert 0 < prior.multiplier < 1
    assert connection.commits == 1


def test_proposal_store_records_decision_shift_in_run_graph_counts() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    connection = RecordingConnection()
    source = _source_row()
    proposal_run_id = uuid4()
    previous_run_id = uuid4()
    connection.cursor_obj._fetchall_values.extend(
        [
            [
                {
                    "capability_id": "katana",
                    "profile_id": "safe-crawl",
                    "rank": 1,
                    "utility_score": 9.0,
                },
                {
                    "capability_id": "httpx",
                    "profile_id": "safe-probe",
                    "rank": 2,
                    "utility_score": 1.0,
                },
            ],
            [
                {
                    "capability_id": "httpx",
                    "profile_id": "safe-probe",
                    "rank": 1,
                    "utility_score": 5.0,
                },
                {
                    "capability_id": "subfinder",
                    "profile_id": "passive",
                    "rank": 2,
                    "utility_score": 5.0,
                },
            ],
        ]
    )
    connection.cursor_obj._fetchone_values.append({"proposal_run_id": previous_run_id})

    result = Store(connection).record_decision_shift(
        proposal_run_id=proposal_run_id,
        source=source,
        top_k=5,
    )

    assert result.proposal_run_id == proposal_run_id
    assert result.candidate_count == 2
    assert result.previous_candidate_count == 2
    assert result.total_variation_distance is not None
    assert result.decision_shift_score > 0
    run_update_query, run_update_params = next(
        (query, params)
        for query, params in connection.cursor_obj.calls
        if "UPDATE action_experience_proposal_runs" in query and "decision_graph_counts" in params
    )
    assert "decision_distribution" in run_update_query or "decision_graph_counts" in run_update_params
    assert run_update_params["proposal_run_id"] == proposal_run_id
    assert run_update_params["decision_graph_counts"]["decision_distribution"]["candidate_count"] == 2
    assert run_update_params["decision_graph_counts"]["decision_shift"]["previous_proposal_run_id"] == str(previous_run_id)
    assert run_update_params["decision_graph_counts"]["decision_shift"]["decision_shift_score"] > 0

    all_queries = "\n".join(query for query, _ in connection.cursor_obj.calls)
    assert "UPDATE action_outcomes" not in all_queries
    assert "graph_projection_events" not in all_queries
    assert not hasattr(result, "experience_utility_score")
    assert not hasattr(result, "decision_shift_units")
