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


def test_action_experience_proposal_tables_are_internal_advisory_state() -> None:
    assert "source_outcome_id" in action_experience_proposal_runs.c
    assert "feature_keys" in action_experience_proposal_runs.c
    assert "graph_counts" in action_experience_proposal_runs.c
    assert "candidate_count" in action_experience_proposal_runs.c
    assert "proposal_run_id" in action_experience_proposals.c
    assert "capability_id" in action_experience_proposals.c
    assert "profile_id" in action_experience_proposals.c
    assert "utility_score" in action_experience_proposals.c
    assert "explanation" in action_experience_proposals.c
    assert any(index.name == "idx_action_experience_proposals_pending_program_rank" for index in action_experience_proposals.indexes)
    assert any(index.name == "idx_action_experience_proposal_runs_status_created" for index in action_experience_proposal_runs.indexes)


def test_action_experience_proposal_migration_has_no_public_api_or_bug_rules() -> None:
    source = Path("alembic/versions/n9o0p1q2r3s4_add_action_experience_proposals.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "m9n0o1p2q3r4"' in source
    assert "action_experience_proposal_runs" in source
    assert "action_experience_proposals" in source
    assert "feature_keys" in source
    assert "utility_score" in source
    assert "capability_id" in source
    forbidden_bug_classes = ["idor", "ssrf", "takeover", "auth bypass"]
    assert not any(token in source.lower() for token in forbidden_bug_classes)

    routes_source = Path("src/api/presentation/rest/routes/actions.py").read_text(encoding="utf-8")
    assert "experience-proposal" not in routes_source
    assert "GDS" not in routes_source


def test_action_experience_acceptance_statuses_live_in_later_migration_only() -> None:
    source = Path("alembic/versions/u5v6w7x8y9z0_extend_action_experience_acceptance_statuses.py").read_text(
        encoding="utf-8"
    )

    assert 'down_revision = "f9a0b1c2d3e4"' in source
    assert "accepting" in source
    assert "accept_failed" in source


def test_proposal_store_lists_sources_not_sql_utility_ranking() -> None:
    _, _, _, Store, _, _, _ = _symbols()
    connection = RecordingConnection()
    program_id = uuid4()

    Store(connection).list_sources_without_proposal_run(limit=7, program_id=program_id)

    query, parameters = connection.cursor_obj.calls[0]
    assert "FROM action_outcomes" in query
    assert "action_experience_proposal_runs" in query
    assert "utility_score" not in query
    assert "GROUP BY" not in query.upper()
    assert parameters["limit"] == 7
    assert parameters["program_id"] == str(program_id)
    assert connection.commits == 1
