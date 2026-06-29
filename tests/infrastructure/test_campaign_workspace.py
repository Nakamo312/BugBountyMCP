from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from api.application.campaign_workspace import CampaignWorkspaceService
from api.infrastructure.adapters.orm import metadata
from api.infrastructure.campaign_workspace import CampaignWorkspaceStore


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
    def __init__(self, *, program_id, campaign_id):
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.queries = []
        self.now = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
        self.task_id = uuid4()
        self.message_id = uuid4()
        self.decision_message_id = uuid4()
        self.proposal_id = uuid4()
        self.experience_proposal_id = uuid4()
        self.proposal_run_id = uuid4()
        self.action_id = uuid4()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        text = str(query)
        self.queries.append(text)
        if "FROM agent_tasks" in text:
            return _Result([
                {
                    "id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "status": "queued",
                    "target_agent": "coordinator",
                    "title": "Разобрать новую ветку",
                    "prompt_excerpt": "Разбери account/*",
                    "prompt_hash": "a" * 64,
                    "created_by": "human",
                    "source": "ui",
                    "context_refs": [{"kind": "surface", "id": "account"}],
                    "metadata": {"ui": "campaign-workspace"},
                    "created_at": self.now,
                    "updated_at": self.now,
                    "inbox_message_id": uuid4(),
                }
            ])
        if "FROM agent_task_messages" in text:
            return _Result([
                {
                    "id": self.decision_message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "role": "agent",
                    "message_kind": "decision",
                    "agent_key": "proposal-feedback",
                    "body": "Предложение отклонено как обратная связь.",
                    "body_hash": "b" * 64,
                    "artifact_refs": [],
                    "fact_refs": [],
                    "graph_refs": [],
                    "action_refs": [],
                    "proposal_refs": [{"kind": "agent_action_proposal", "proposal_id": str(self.proposal_id)}],
                    "decision_refs": [{"kind": "agent_action_proposal_decision", "decision": "rejected"}],
                    "metadata": {"source": "agent_action_proposal_review"},
                    "created_at": self.now,
                },
                {
                    "id": self.message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "role": "agent",
                    "message_kind": "proposal",
                    "agent_key": "coordinator",
                    "body": "Предлагаю проверить JavaScript через безопасный контур.",
                    "body_hash": "c" * 64,
                    "artifact_refs": [],
                    "fact_refs": [],
                    "graph_refs": [],
                    "action_refs": [],
                    "proposal_refs": [{"kind": "agent_action_proposal", "proposal_id": str(self.proposal_id)}],
                    "decision_refs": [],
                    "metadata": {
                        "source": "agent",
                        "budget": {
                            "requested_mode": "deep",
                            "selected_mode": "normal",
                            "llm_allowed": True,
                            "reason_code": "deep_mode_disabled",
                            "deep_approval": {"reason_code": "deep_mode_disabled"},
                            "observed": {
                                "prompt_chars_before": 500,
                                "prompt_chars_after": 500,
                                "context_refs_before": 20,
                                "context_refs_after": 8,
                            },
                        },
                    },
                    "created_at": self.now,
                },
            ])
        if "FROM agent_action_proposals" in text:
            return _Result([
                {
                    "id": self.proposal_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "task_id": self.task_id,
                    "source_message_id": self.message_id,
                    "agent_key": "coordinator",
                    "proposal_key": "proposal-key",
                    "proposal_type": "investigation_task",
                    "status": "pending",
                    "title": "Проверить JavaScript",
                    "summary": "Появились новые скрипты и скрытые пути.",
                    "rationale": "Есть новая поверхность.",
                    "capability_id": None,
                    "profile_id": None,
                    "priority": "medium",
                    "risk_level": "low",
                    "expected_gain": "новые endpoints",
                    "action_intent": "review_js_paths",
                    "action_params": {},
                    "context_refs": [{"kind": "surface", "id": "js"}],
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
                }
            ])
        if "FROM action_experience_proposals" in text:
            return _Result([
                {
                    "id": self.experience_proposal_id,
                    "proposal_run_id": self.proposal_run_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "status": "pending",
                    "rank": 1,
                    "capability_id": "linkfinder",
                    "profile_id": "js-analysis",
                    "utility_score": 0.72,
                    "sample_count": 12,
                    "avg_similarity": 0.81,
                    "explanation": {"why": "similar outcomes"},
                    "created_at": self.now,
                }
            ])
        if "FROM agent_runtime_usage_daily" in text:
            return _Result([
                {
                    "id": uuid4(),
                    "scope_key": "scope",
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "usage_date": self.now.date(),
                    "total_agent_messages": 1,
                    "runtime_decision_messages": 1,
                    "requested_none_count": 0,
                    "requested_cheap_count": 0,
                    "requested_normal_count": 0,
                    "requested_deep_count": 1,
                    "selected_none_count": 0,
                    "selected_cheap_count": 0,
                    "selected_normal_count": 1,
                    "selected_deep_count": 0,
                    "llm_allowed_messages": 1,
                    "no_model_messages": 0,
                    "downgraded_messages": 1,
                    "deep_requested_messages": 1,
                    "deep_approved_messages": 0,
                    "deep_downgraded_messages": 1,
                    "context_truncated_messages": 1,
                    "latest_message_id": self.message_id,
                    "latest_selected_mode": "normal",
                    "latest_requested_mode": "deep",
                    "latest_reason_code": "deep_mode_disabled",
                    "metadata": {},
                    "created_at": self.now,
                    "updated_at": self.now,
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
                    "capability_id": "katana",
                    "profile_id": "passive-crawl",
                    "requested_by": "human",
                    "workflow_id": None,
                    "correlation_id": uuid4(),
                    "catalog_hash": None,
                    "metadata": {"source": "accepted_proposal"},
                    "status": "queued",
                    "request": {},
                    "created_at": self.now,
                    "updated_at": self.now,
                }
            ])
        raise AssertionError(text)


class _SessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_campaign_workspace_read_model_assembles_ui_payload_without_running_internal_engines() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    session = _Session(program_id=program_id, campaign_id=campaign_id)
    service = CampaignWorkspaceService(CampaignWorkspaceStore(_SessionFactory(session)))

    snapshot = await service.get_workspace(program_id=program_id, campaign_id=campaign_id)

    assert snapshot.program_id == program_id
    assert snapshot.campaign_id == campaign_id
    assert snapshot.tasks[0].task.title == "Разобрать новую ветку"
    assert any(message.body.startswith("Предложение отклонено") for message in snapshot.tasks[0].messages)
    assert snapshot.tasks[0].proposals[0].title == "Проверить JavaScript"
    assert snapshot.pending_agent_proposals[0].status.value == "pending"
    assert snapshot.pending_experience_proposals[0].capability_id == "linkfinder"
    assert any("action_experience_proposals.status IN" in query for query in session.queries)
    assert snapshot.recent_decisions[0].message_kind.value == "decision"
    assert snapshot.action_queue[0].capability_id == "katana"
    assert snapshot.counts == {
        "tasks": 1,
        "visible_messages": 2,
        "pending_agent_proposals": 1,
        "pending_experience_proposals": 1,
        "recent_decisions": 1,
        "action_queue": 1,
        "agent_runtime_decisions": 1,
        "agent_runtime_llm_allowed": 1,
        "agent_runtime_deep_downgraded": 1,
    }
    assert snapshot.agent_runtime_usage.runtime_decision_messages == 1
    assert snapshot.agent_runtime_usage.selected_modes["normal"] == 1
    assert snapshot.agent_runtime_usage.deep_downgraded_messages == 1
    assert "context_truncated" in snapshot.agent_runtime_usage.warnings
    assert snapshot.boundaries["gds_execution"] == "not_available_from_workspace_api"
    assert snapshot.boundaries["tool_execution"] == "must_go_through_action_service"
    assert not any("raw_artifacts" in query for query in session.queries)


def test_campaign_workspace_experience_query_includes_failed_acceptance_for_retry_surface() -> None:
    source = Path("src/api/infrastructure/campaign_workspace.py").read_text(encoding="utf-8")

    assert '"pending", "accepting", "accept_failed"' in source
    assert ".status.in_(" in source


def test_campaign_workspace_tables_exist_without_new_migration() -> None:
    for table_name in (
        "agent_tasks",
        "agent_task_messages",
        "agent_action_proposals",
        "action_experience_proposals",
        "action_requests",
        "agent_runtime_usage_daily",
    ):
        assert table_name in metadata.tables


def test_campaign_workspace_source_does_not_expose_internal_gds_or_raw_artifacts() -> None:
    source = Path("src/api/infrastructure/campaign_workspace.py").read_text(encoding="utf-8")
    route_source = Path("src/api/presentation/rest/routes/campaign_workspace.py").read_text(encoding="utf-8")

    assert "gds." not in source.lower()
    assert "raw_artifacts" not in source
    assert "run gds" not in route_source.lower()
    assert "does not execute agents, GDS, or tools" in route_source


def test_agent_runtime_usage_daily_migration_extends_review_head() -> None:
    source = Path("alembic/versions/t5u6v7w8x9y0_add_agent_runtime_usage_daily.py").read_text(encoding="utf-8")
    assert 'down_revision = "s4t5u6v7w8x9"' in source
    assert '"agent_runtime_usage_daily"' in source
    assert '"scope_key"' in source
    assert '"latest_message_id"' in source
