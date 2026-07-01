from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4


def symbols():
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.action_experience_probe import (
        ActionExperienceProbeFeatureSet,
        ActionExperienceProbeRanking,
    )
    from graph_projector.action_experience.proposals import (
        ActionExperienceProposalLoopResult,
        ActionExperienceProposalStore,
        ActionExperienceProposalWorker,
        _proposal_key,
    )
    from graph_projector.action_outcome_gds import ActionOutcomeGdsCandidate

    return (
        ActionExperienceProbeFeatureSet,
        ActionExperienceProbeRanking,
        ActionExperienceProposalLoopResult,
        ActionExperienceProposalStore,
        ActionExperienceProposalWorker,
        ActionOutcomeGdsCandidate,
        _proposal_key,
    )


class RecordingCursor:
    def __init__(self):
        self.calls = []
        self._fetchone_values = []
        self._fetchall_values = []

    def execute(self, query, parameters=None):
        self.calls.append((query, parameters or {}))

    def fetchone(self):
        if self._fetchone_values:
            return self._fetchone_values.pop(0)
        return {"id": uuid4()}

    def fetchall(self):
        if self._fetchall_values:
            return self._fetchall_values.pop(0)
        return []


class RecordingConnection:
    def __init__(self):
        self.cursor_obj = RecordingCursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeDriver:
    def __init__(self):
        self.session_kwargs = []

    def session(self, **kwargs):
        self.session_kwargs.append(kwargs)
        return FakeSession()


class FakeRanker:
    def __init__(self, ranking):
        self.ranking = ranking
        self.calls = []

    def rank_for_current_graph_state(self, session, **kwargs):
        self.calls.append(kwargs)
        return self.ranking


def source_row():
    return {
        "id": uuid4(),
        "program_id": uuid4(),
        "campaign_id": uuid4(),
        "action_id": uuid4(),
        "job_id": uuid4(),
        "run_id": uuid4(),
        "node_id": "katana",
        "event_name": "web.crawl",
        "target_count": 8,
        "status": "completed",
        "terminal_outcome": "completed",
        "duration_ms": 1500,
        "raw_artifact_count": 1,
        "http_observation_count": 6,
        "javascript_reference_count": 2,
        "error_count": 0,
    }


def ranking(*, candidate_count: int = 1):
    FeatureSet, Ranking, _, _, _, Candidate, _ = symbols()
    candidates = tuple(
        Candidate(
            capability_id=f"web.crawl.{idx}",
            profile_id="passive-default",
            sample_count=3,
            avg_similarity=0.75,
            avg_information_gain_score=5.0,
            human_positive_rate=0.25,
            human_stop_rate=0.0,
            utility_score=4.6875,
        )
        for idx in range(candidate_count)
    )
    return Ranking(
        feature_set=FeatureSet(
            program_id="program",
            feature_keys=("node:katana", "surface_endpoints_bucket:6-20"),
            graph_counts={"endpoint_count": 12},
        ),
        candidates=candidates,
    )
