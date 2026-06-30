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


class ProposalStoreContractDefaults:
    def load_review_priors(self, *, program_id, campaign_id=None, proposal_source=None):
        return {}

    def record_decision_shift(self, *, proposal_run_id, source):
        return None

    def append_component_action_candidates(self, **kwargs):  # pragma: no cover
        raise AssertionError("surface component candidates were not expected")


def test_proposal_worker_uses_graph_ranker_and_does_not_create_actions() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    source = _source_row()
    ranking = _ranking(candidate_count=1)

    class Store(ProposalStoreContractDefaults):
        def __init__(self):
            self.recorded = []

        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def record_ranking(self, *, source, ranking):
            self.recorded.append((source, ranking))
            return uuid4(), len(ranking.candidates)

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    store = Store()
    driver = FakeDriver()
    ranker = FakeRanker(ranking)
    worker = Worker(store=store, neo4j_driver=driver, neo4j_database="neo4j", ranker=ranker, candidate_limit=3)

    result = worker.propose_once(limit=5, program_id=source["program_id"])

    assert result.scanned == 1
    assert result.proposal_runs == 1
    assert result.proposals == 1
    assert result.failed == 0
    assert driver.session_kwargs == [{"database": "neo4j"}]
    assert ranker.calls[0]["program_id"] == str(source["program_id"])
    assert ranker.calls[0]["node_id"] == "katana"
    assert ranker.calls[0]["event_name"] == "web.crawl"
    assert ranker.calls[0]["target_count"] == 8
    assert ranker.calls[0]["limit"] == 3
    assert ranker.calls[0]["candidate_profile_limit"] == 100
    assert "status:completed" in ranker.calls[0]["base_feature_keys"]
    assert "target_count_bucket:6-20" in ranker.calls[0]["base_feature_keys"]
    assert store.recorded[0][1] is ranking


def test_proposal_worker_requires_review_prior_store_contract() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    source = _source_row()
    ranking = _ranking(candidate_count=1)

    class Store:
        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def record_ranking(self, *, source, ranking):
            return uuid4(), len(ranking.candidates)

        def record_decision_shift(self, *, proposal_run_id, source):
            return None

        def append_component_action_candidates(self, **kwargs):  # pragma: no cover
            raise AssertionError("surface component candidates were not expected")

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    with pytest.raises(TypeError, match="ActionExperienceProposalStorePort"):
        Worker(store=Store(), neo4j_driver=FakeDriver(), ranker=FakeRanker(ranking))


def test_proposal_worker_requires_decision_shift_store_contract() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    source = _source_row()
    ranking = _ranking(candidate_count=1)

    class Store:
        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def load_review_priors(self, *, program_id, campaign_id=None, proposal_source=None):
            return {}

        def append_component_action_candidates(self, **kwargs):  # pragma: no cover
            raise AssertionError("surface component candidates were not expected")

        def record_ranking(self, *, source, ranking):
            return uuid4(), len(ranking.candidates)

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    with pytest.raises(TypeError, match="ActionExperienceProposalStorePort"):
        Worker(store=Store(), neo4j_driver=FakeDriver(), ranker=FakeRanker(ranking))


def test_proposal_worker_records_no_candidates_once() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    source = _source_row()
    ranking = _ranking(candidate_count=0)

    class Store(ProposalStoreContractDefaults):
        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def record_ranking(self, *, source, ranking):
            return uuid4(), len(ranking.candidates)

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    worker = Worker(store=Store(), neo4j_driver=FakeDriver(), ranker=FakeRanker(ranking))

    result = worker.propose_once(limit=1)

    assert result.scanned == 1
    assert result.proposal_runs == 1
    assert result.proposals == 0
    assert result.no_candidates == 1


def test_proposal_worker_appends_surface_component_candidates_when_snapshot_exists() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.surface_gds import SurfaceComponentActionCandidate

    source = {**_source_row(), "after_surface_snapshot_id": uuid4()}
    ranking = _ranking(candidate_count=1)
    component_candidate = SurfaceComponentActionCandidate(
        component_id=11,
        node_count=6,
        changed_node_count=2,
        max_novelty_score=75,
        capability_id="httpx",
        profile_id="safe-probe",
        sample_count=5,
        avg_similarity=0.5,
        avg_information_gain_score=4.0,
        human_positive_rate=0.2,
        human_stop_rate=0.0,
        utility_score=2.4,
        component_attention_score=68,
        candidate_score=61,
    )

    class Store(ProposalStoreContractDefaults):
        def __init__(self):
            self.appended = []

        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def record_ranking(self, *, source, ranking):
            return uuid4(), len(ranking.candidates)

        def append_component_action_candidates(self, **kwargs):
            self.appended.append(kwargs)
            return len(kwargs["candidates"])

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    class ComponentReader:
        def __init__(self):
            self.calls = []

        def component_action_candidates(self, session, **kwargs):
            self.calls.append(kwargs)
            return (component_candidate,)

    store = Store()
    reader = ComponentReader()
    worker = Worker(
        store=store,
        neo4j_driver=FakeDriver(),
        ranker=FakeRanker(ranking),
        surface_math_reader=reader,
        candidate_limit=2,
        surface_component_candidate_limit=4,
        surface_component_limit=6,
        surface_similarity_cutoff=0.07,
    )

    result = worker.propose_once(limit=1)

    assert result.scanned == 1
    assert result.proposals == 2
    assert result.no_candidates == 0
    assert reader.calls[0]["program_id"] == str(source["program_id"])
    assert reader.calls[0]["snapshot_id"] == str(source["after_surface_snapshot_id"])
    assert reader.calls[0]["limit"] == 4
    assert reader.calls[0]["component_limit"] == 6
    assert reader.calls[0]["similarity_cutoff"] == 0.07
    assert store.appended[0]["start_rank"] == 2
    assert store.appended[0]["candidates"] == (component_candidate,)

def test_proposal_loop_result_stops_after_idle_exit() -> None:
    _, _, LoopResult, _, _, _, _ = _symbols()

    class EmptyWorker:
        def propose_once(self, *, limit, program_id=None):
            from graph_projector.action_experience_proposals import ActionExperienceProposalWorkerResult

            return ActionExperienceProposalWorkerResult()

    result = LoopResult.run(EmptyWorker(), limit=1, idle_exit_after=2, poll_seconds=0)

    assert result.empty == 2
    assert result.iterations == 2


def test_proposal_worker_applies_review_priors_before_materialization() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience_proposals import ActionExperienceProposalReviewPrior

    source = _source_row()
    ranking = _ranking(candidate_count=1)

    class Store(ProposalStoreContractDefaults):
        def __init__(self):
            self.recorded = []

        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def load_review_priors(self, *, program_id, campaign_id=None, proposal_source=None):
            if proposal_source == "neo4j-jaccard-action-experience":
                return {
                    ("web.crawl.0", "passive-default"): ActionExperienceProposalReviewPrior(
                        capability_id="web.crawl.0",
                        profile_id="passive-default",
                        suppressed_count=4,
                        suppressed_confidence=4.0,
                    )
                }
            return {}

        def record_ranking(self, **kwargs):
            self.recorded.append(kwargs)
            return uuid4(), len(kwargs["ranking"].candidates)

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    store = Store()
    worker = Worker(store=store, neo4j_driver=FakeDriver(), ranker=FakeRanker(ranking))

    result = worker.propose_once(limit=1)

    assert result.proposals == 1
    assert store.recorded[0]["review_priors"]
    assert store.recorded[0]["ranking"] is ranking


def test_surface_component_candidates_apply_review_priors() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience_proposals import ActionExperienceProposalReviewPrior
    from graph_projector.surface_gds import SurfaceComponentActionCandidate

    source = {**_source_row(), "after_surface_snapshot_id": uuid4()}
    ranking = _ranking(candidate_count=0)
    candidate = SurfaceComponentActionCandidate(
        component_id=3,
        node_count=5,
        changed_node_count=2,
        max_novelty_score=70,
        capability_id="httpx",
        profile_id="safe-probe",
        sample_count=3,
        avg_similarity=0.5,
        avg_information_gain_score=4.0,
        human_positive_rate=0.0,
        human_stop_rate=0.0,
        utility_score=2.0,
        component_attention_score=60,
        candidate_score=80,
    )

    class Store(ProposalStoreContractDefaults):
        def __init__(self):
            self.appended = []

        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def load_review_priors(self, *, program_id, campaign_id=None, proposal_source=None):
            if proposal_source == "neo4j-jaccard-surface-component":
                return {
                    ("httpx", "safe-probe"): ActionExperienceProposalReviewPrior(
                        capability_id="httpx",
                        profile_id="safe-probe",
                        rejected_count=3,
                        rejected_confidence=3.0,
                    )
                }
            return {}

        def record_ranking(self, *, source, ranking):
            return uuid4(), len(ranking.candidates)

        def append_component_action_candidates(self, **kwargs):
            self.appended.append(kwargs)
            return len(kwargs["candidates"])

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    class ComponentReader:
        def component_action_candidates(self, session, **kwargs):
            return (candidate,)

    store = Store()
    worker = Worker(
        store=store,
        neo4j_driver=FakeDriver(),
        ranker=FakeRanker(ranking),
        surface_math_reader=ComponentReader(),
    )

    result = worker.propose_once(limit=1)

    assert result.proposals == 1
    assert store.appended[0]["candidates"] == (candidate,)
    assert store.appended[0]["review_priors"]


def test_proposal_worker_records_decision_shift_after_materialization() -> None:
    _, _, _, _, Worker, _, _ = _symbols()
    source = _source_row()
    ranking = _ranking(candidate_count=1)
    proposal_run_id = uuid4()

    class Store(ProposalStoreContractDefaults):
        def __init__(self):
            self.decision_shift_calls = []

        def list_sources_without_proposal_run(self, *, limit, program_id=None):
            return [source]

        def record_ranking(self, *, source, ranking):
            return proposal_run_id, len(ranking.candidates)

        def record_decision_shift(self, *, proposal_run_id, source):
            self.decision_shift_calls.append((proposal_run_id, source["id"]))

        def record_failed_generation(self, *, source, error):  # pragma: no cover
            raise AssertionError(error)

    store = Store()
    worker = Worker(store=store, neo4j_driver=FakeDriver(), ranker=FakeRanker(ranking))

    result = worker.propose_once(limit=1)

    assert result.proposals == 1
    assert store.decision_shift_calls == [(proposal_run_id, source["id"])]
