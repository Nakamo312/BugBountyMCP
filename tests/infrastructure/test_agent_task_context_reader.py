from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from api.application.agent_task_inbox_bridge import AgentTaskRuntimeRequest
from api.infrastructure.agent_task_context import PostgresAgentTaskContextReader


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return _Mappings(self._rows)

    def scalar_one(self):
        return self._scalar


class _Session:
    def __init__(self, request):
        self.request = request
        self.queries = []
        now = datetime(2026, 6, 26, tzinfo=timezone.utc)
        self.now = now

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        text = str(query)
        self.queries.append(text)
        if "FROM agent_tasks" in text:
            return _Result(rows=[{
                "id": self.request.task_id,
                "program_id": self.request.program_id,
                "campaign_id": self.request.campaign_id,
                "correlation_id": self.request.correlation_id,
                "status": "queued",
                "target_agent": "surface",
                "title": "Разбери account",
                "created_by": "human",
                "source": "ui",
                "context_refs": [{"kind": "surface", "id": "api/account"}],
                "created_at": self.now,
            }])
        if "FROM agent_task_messages" in text:
            return _Result(rows=[{
                "id": self.request.message_id,
                "role": "user",
                "message_kind": "note",
                "agent_key": "surface",
                "body": "Разбери новую ветку api/account/* и не тащи сырой вывод",
                "artifact_refs": [],
                "fact_refs": [{"kind": "fact", "id": "fact-1"}],
                "graph_refs": [],
                "action_refs": [],
                "proposal_refs": [],
                "decision_refs": [],
                "created_at": self.now,
            }])
        if "FROM action_outcomes" in text:
            return _Result(rows=[{
                "id": uuid4(),
                "action_id": uuid4(),
                "run_id": uuid4(),
                "capability_id": "katana",
                "profile_id": "passive-crawl",
                "node_id": "katana",
                "event_name": "crawl_requested",
                "status": "completed",
                "terminal_outcome": "completed",
                "raw_artifact_count": 2,
                "observed_hosts_count": 1,
                "observed_services_count": 1,
                "observed_endpoints_count": 36,
                "http_observation_count": 36,
                "javascript_reference_count": 12,
                "manual_interest": True,
                "manual_stop": None,
                "continued_by_followup": True,
                "report_created": False,
                "triage_outcome": None,
                "information_gain_score": 0.81,
                "created_at": self.now,
            }])
        if "FROM action_experience_proposals" in text:
            return _Result(rows=[{
                "id": uuid4(),
                "proposal_run_id": uuid4(),
                "source_outcome_id": uuid4(),
                "capability_id": "linkfinder",
                "profile_id": "js-analysis",
                "rank": 1,
                "utility_score": 0.73,
                "sample_count": 9,
                "avg_similarity": 0.82,
                "avg_information_gain_score": 0.69,
                "human_positive_rate": 0.4,
                "human_stop_rate": 0.1,
                "explanation": {"why": "similar outcomes"},
                "created_at": self.now,
            }])
        if "count(*)" in text and "FROM hosts" in text and "JOIN" not in text:
            return _Result(scalar=4)
        if "count(*)" in text and "FROM endpoints JOIN hosts" in text:
            return _Result(scalar=120)
        if "count(*)" in text and "FROM http_observations" in text:
            return _Result(scalar=44)
        if "count(*)" in text and "FROM javascript_references" in text:
            return _Result(scalar=12)
        if "FROM http_observations" in text:
            return _Result(rows=[{
                "id": uuid4(),
                "method": "GET",
                "url": "https://example.com/api/account/export",
                "status_code": 200,
                "content_type": "application/json",
                "source_tool": "httpx",
                "observed_at": self.now,
            }])
        if "FROM javascript_references" in text:
            return _Result(rows=[{
                "id": uuid4(),
                "source_url": "https://example.com/app.js",
                "referenced_url": "https://example.com/api/account/profile",
                "reference_type": "endpoint",
                "source_tool": "linkfinder",
                "observed_at": self.now,
            }])
        raise AssertionError(text)


class _SessionFactory:
    def __init__(self, request):
        self.session = _Session(request)

    def __call__(self):
        return self.session


def _request():
    return AgentTaskRuntimeRequest(
        task_id=uuid4(),
        message_id=uuid4(),
        program_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        target_agent="surface",
        schema_version="agent-task-prompt.v1",
        body_excerpt="Разбери account",
        body_hash="a" * 64,
        context_refs=({"kind": "surface", "id": "api/account"},),
        metadata={"ui": "campaign-workspace"},
        source="ui",
    )


@pytest.mark.asyncio
async def test_postgres_agent_task_context_reader_returns_bounded_compact_context() -> None:
    request = _request()
    factory = _SessionFactory(request)
    reader = PostgresAgentTaskContextReader(factory, max_request_context_refs=5)

    context = await reader.read(request)

    assert context["task"]["title"] == "Разбери account"
    assert context["thread_messages"][0]["body_excerpt"].startswith("Разбери новую ветку")
    assert context["recent_outcomes"][0]["capability_id"] == "katana"
    assert context["recent_outcomes"][0]["counts"]["endpoints"] == 36
    assert context["pending_proposals"][0]["capability_id"] == "linkfinder"
    assert context["pending_proposals"][0]["status"] == "pending"
    assert context["surface_summary"]["counts"] == {
        "hosts": 4,
        "endpoints": 120,
        "http_observations": 44,
        "javascript_references": 12,
    }
    assert context["surface_summary"]["recent_http"][0]["url_excerpt"].endswith("/api/account/export")
    assert context["context_reader"]["raw_artifact_access"] == "forbidden"
    assert not any("raw_artifacts" in query for query in factory.session.queries)


def test_agent_task_context_reader_includes_failed_acceptance_statuses_for_recovery() -> None:
    source = Path("src/api/infrastructure/agent_task_context.py").read_text(encoding="utf-8")

    assert '"pending", "accepting", "accept_failed"' in source
    assert "action_experience_proposals.c.status" in source


def test_agent_task_context_reader_source_does_not_import_raw_artifact_table() -> None:
    source = Path("src/api/infrastructure/agent_task_context.py").read_text(encoding="utf-8")

    assert "RawArtifact" not in source
    assert "raw_artifacts," not in source
    assert "raw_artifacts)" not in source
    assert "from api.infrastructure.adapters.orm import raw_artifacts" not in source
    assert "raw_artifact_access" in source
