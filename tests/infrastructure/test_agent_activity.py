from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from api.application.agent_activity import AgentActivityEventType, AgentActivityService
from api.infrastructure.adapters.orm import metadata
from api.infrastructure.agent_activity import AgentActivityStore


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _Mappings(self._rows)


class _Session:
    def __init__(self, *, program_id, campaign_id, task_id):
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.task_id = task_id
        self.queries = []
        self.now = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
        self.message_id = uuid4()
        self.proposal_id = uuid4()
        self.feedback_id = uuid4()
        self.action_id = uuid4()
        self.source_message_id = uuid4()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        text = str(query)
        self.queries.append(text)
        if "FROM agent_task_messages" in text:
            return _Result([
                {
                    "id": self.message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "role": "agent",
                    "message_kind": "proposal",
                    "agent_key": "coordinator",
                    "body": "Предлагаю разобрать JavaScript и account/*.",
                    "body_hash": "a" * 64,
                    "artifact_refs": [],
                    "fact_refs": [],
                    "graph_refs": [],
                    "action_refs": [],
                    "proposal_refs": [{"kind": "agent_action_proposal", "proposal_id": str(self.proposal_id)}],
                    "decision_refs": [],
                    "metadata": {"source": "agent"},
                    "created_at": self.now,
                }
            ])
        if "FROM agent_action_proposals" in text and "JOIN" not in text:
            return _Result([
                {
                    "id": self.proposal_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "task_id": self.task_id,
                    "source_message_id": self.source_message_id,
                    "agent_key": "coordinator",
                    "proposal_key": "proposal-key",
                    "proposal_type": "investigation_task",
                    "status": "pending",
                    "title": "Проверить JavaScript",
                    "summary": "Новые скрипты и скрытые пути.",
                    "rationale": "Появилась новая поверхность.",
                    "capability_id": None,
                    "profile_id": None,
                    "priority": "medium",
                    "risk_level": "low",
                    "expected_gain": "Новые endpoints",
                    "action_intent": "review_js_paths",
                    "action_params": {},
                    "context_refs": [{"kind": "javascript", "id": "app.js"}],
                    "metadata": {"proposal_boundary": {"action_service_required": True}},
                    "produced_by": "agent-task-runtime",
                    "accepted_action_id": None,
                    "accepted_by": None,
                    "accepted_reason": None,
                    "accepted_at": None,
                    "reviewed_by": None,
                    "review_reason": None,
                    "review_feedback": {},
                    "reviewed_at": None,
                    "created_at": self.now + timedelta(seconds=1),
                    "updated_at": self.now + timedelta(seconds=1),
                }
            ])
        if "FROM agent_action_proposal_feedback_events" in text:
            return _Result([
                {
                    "id": self.feedback_id,
                    "proposal_id": self.proposal_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "task_id": self.task_id,
                    "source_message_id": self.source_message_id,
                    "agent_key": "coordinator",
                    "previous_status": "pending",
                    "new_status": "suppressed",
                    "feedback_type": "suppressed",
                    "actor": "human",
                    "reason": "Это повторяет прошлый шум.",
                    "confidence": 0.9,
                    "feedback_tags": ["noise"],
                    "metadata": {"source": "ui"},
                    "created_at": self.now + timedelta(seconds=2),
                }
            ])
        if "FROM action_requests" in text:
            return _Result([
                {
                    "id": self.action_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "catalog_entry_id": uuid4(),
                    "kind": "scan",
                    "capability_id": "linkfinder",
                    "profile_id": "js-analysis",
                    "requested_by": "human",
                    "workflow_id": None,
                    "correlation_id": uuid4(),
                    "catalog_hash": None,
                    "metadata": {"agent_task_id": str(self.task_id)},
                    "status": "requires_approval",
                    "request": {},
                    "created_at": self.now + timedelta(seconds=3),
                    "updated_at": self.now + timedelta(seconds=3),
                }
            ])
        raise AssertionError(text)


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_agent_activity_stream_returns_incremental_visible_events_without_running_engines() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    task_id = uuid4()
    session = _Session(program_id=program_id, campaign_id=campaign_id, task_id=task_id)
    service = AgentActivityService(AgentActivityStore(_SessionFactory(session)))

    snapshot = await service.get_activity_stream(program_id=program_id, campaign_id=campaign_id, task_id=task_id)

    assert snapshot.program_id == program_id
    assert snapshot.campaign_id == campaign_id
    assert snapshot.task_id == task_id
    assert [event.event_type for event in snapshot.events] == [
        AgentActivityEventType.AGENT_MESSAGE,
        AgentActivityEventType.AGENT_PROPOSAL,
        AgentActivityEventType.PROPOSAL_DECISION,
        AgentActivityEventType.ACTION_STATUS,
    ]
    assert snapshot.events[0].summary.startswith("Предлагаю")
    assert snapshot.events[1].requires_attention is True
    assert snapshot.events[2].status == "suppressed"
    assert snapshot.events[3].requires_attention is True
    assert snapshot.counts == {
        "events": 4,
        "agent_messages": 1,
        "agent_proposals": 1,
        "proposal_decisions": 1,
        "action_status_updates": 1,
        "requires_attention": 2,
    }
    assert snapshot.next_after == session.now + timedelta(seconds=3)
    assert snapshot.boundaries["agent_execution"] == "not_available_from_activity_api"
    assert snapshot.boundaries["tool_execution"] == "must_go_through_action_service"
    assert not any("raw_artifacts" in query for query in session.queries)


@pytest.mark.asyncio
async def test_agent_activity_stream_passes_after_cursor_into_queries() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    task_id = uuid4()
    session = _Session(program_id=program_id, campaign_id=campaign_id, task_id=task_id)
    service = AgentActivityService(AgentActivityStore(_SessionFactory(session)))
    after = datetime(2026, 6, 26, 11, 59, tzinfo=timezone.utc)

    snapshot = await service.get_activity_stream(
        program_id=program_id,
        campaign_id=campaign_id,
        task_id=task_id,
        after=after,
        limit=50,
    )

    assert snapshot.after == after
    rendered_queries = "\n".join(session.queries)
    assert "agent_task_messages.created_at >" in rendered_queries
    assert "agent_action_proposals.created_at >" in rendered_queries
    assert "agent_action_proposal_feedback_events.created_at >" in rendered_queries
    assert "action_requests.created_at >" in rendered_queries


def test_agent_activity_tables_exist_without_new_migration() -> None:
    for table_name in (
        "agent_task_messages",
        "agent_action_proposals",
        "agent_action_proposal_feedback_events",
        "action_requests",
    ):
        assert table_name in metadata.tables


def test_agent_activity_source_does_not_expose_internal_engines_or_raw_artifacts() -> None:
    source = Path("src/api/infrastructure/agent_activity.py").read_text(encoding="utf-8")
    route_source = Path("src/api/presentation/rest/routes/agent_activity.py").read_text(encoding="utf-8")

    assert "gds." not in source.lower()
    assert "raw_artifacts" not in source
    assert "execute agents, GDS, or tools" in route_source
