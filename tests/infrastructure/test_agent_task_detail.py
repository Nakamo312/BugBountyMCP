from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from api.application.agent_task_detail import AgentTaskDetailService
from api.infrastructure.adapters.orm import metadata
from api.infrastructure.agent_task_detail import AgentTaskDetailStore


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def one_or_none(self):
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
    def __init__(self, *, program_id, campaign_id, task_id):
        self.program_id = program_id
        self.campaign_id = campaign_id
        self.task_id = task_id
        self.now = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)
        self.queries = []
        self.message_id = uuid4()
        self.decision_message_id = uuid4()
        self.proposal_id = uuid4()
        self.accepted_action_id = uuid4()
        self.outcome_id = uuid4()
        self.run_id = uuid4()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, query):
        text = str(query)
        self.queries.append(text)
        if "FROM agent_tasks" in text:
            return _Result(rows=[{
                "id": self.task_id,
                "program_id": self.program_id,
                "campaign_id": self.campaign_id,
                "correlation_id": uuid4(),
                "status": "queued",
                "target_agent": "artifact",
                "title": "Разобрать JS пути",
                "prompt_excerpt": "Разбери новые пути из JavaScript",
                "prompt_hash": "a" * 64,
                "created_by": "human",
                "source": "ui",
                "context_refs": [{"kind": "javascript", "id": "app.js"}],
                "metadata": {"ui": "task-detail"},
                "created_at": self.now,
                "updated_at": self.now,
                "inbox_message_id": uuid4(),
            }])
        if "FROM agent_task_messages" in text:
            return _Result(rows=[
                {
                    "id": self.message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "role": "user",
                    "message_kind": "note",
                    "agent_key": "artifact",
                    "body": "Разбери новые JS пути и предложи безопасный следующий шаг",
                    "body_hash": "b" * 64,
                    "artifact_refs": [],
                    "fact_refs": [{"kind": "js_ref", "id": "ref-1"}],
                    "graph_refs": [],
                    "action_refs": [],
                    "proposal_refs": [],
                    "decision_refs": [],
                    "metadata": {"source": "ui"},
                    "created_at": self.now,
                },
                {
                    "id": self.decision_message_id,
                    "task_id": self.task_id,
                    "program_id": self.program_id,
                    "campaign_id": self.campaign_id,
                    "correlation_id": uuid4(),
                    "role": "agent",
                    "message_kind": "decision",
                    "agent_key": "proposal-feedback",
                    "body": "Предложение принято. Создан ActionRequest.",
                    "body_hash": "c" * 64,
                    "artifact_refs": [],
                    "fact_refs": [],
                    "graph_refs": [],
                    "action_refs": [{"kind": "action_request", "action_id": str(self.accepted_action_id)}],
                    "proposal_refs": [{"kind": "agent_action_proposal", "proposal_id": str(self.proposal_id)}],
                    "decision_refs": [{"kind": "agent_action_proposal_decision", "decision": "accepted"}],
                    "metadata": {
                        "source": "agent_action_proposal_accept",
                        "budget": {
                            "requested_mode": "cheap",
                            "selected_mode": "cheap",
                            "llm_allowed": True,
                            "reason_code": "selected",
                            "observed": {
                                "prompt_chars_before": 900,
                                "prompt_chars_after": 900,
                                "context_refs_before": 2,
                                "context_refs_after": 2,
                            },
                        },
                    },
                    "created_at": self.now,
                },
            ])
        if "FROM agent_action_proposals" in text:
            return _Result(rows=[{
                "id": self.proposal_id,
                "program_id": self.program_id,
                "campaign_id": self.campaign_id,
                "task_id": self.task_id,
                "source_message_id": self.message_id,
                "agent_key": "artifact",
                "proposal_key": "proposal-key",
                "proposal_type": "tool_action",
                "status": "accepted",
                "title": "Проверить JS пути",
                "summary": "Новые пути можно проверить через безопасный контур.",
                "rationale": "Появились новые JS refs.",
                "capability_id": "linkfinder",
                "profile_id": "js-analysis",
                "priority": "medium",
                "risk_level": "low",
                "expected_gain": "новые endpoints",
                "action_intent": "review_js_paths",
                "action_params": {"targets": ["https://example.com/app.js"]},
                "context_refs": [{"kind": "javascript", "id": "app.js"}],
                "metadata": {"proposal_boundary": {"action_service_required": True}},
                "produced_by": "agent-task-runtime",
                "accepted_action_id": self.accepted_action_id,
                "accepted_by": "human",
                "accepted_reason": "проверить безопасно",
                "accepted_at": self.now,
                "reviewed_by": None,
                "review_reason": None,
                "review_feedback": {},
                "reviewed_at": None,
            }])
        if "FROM action_requests" in text:
            return _Result(rows=[{
                "id": self.accepted_action_id,
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
                "metadata": {"source": "agent_action_proposal_accept"},
                "status": "queued",
                "request": {},
                "created_at": self.now,
                "updated_at": self.now,
            }])
        if "FROM action_outcomes" in text:
            return _Result(rows=[{
                "id": self.outcome_id,
                "program_id": self.program_id,
                "campaign_id": self.campaign_id,
                "action_id": self.accepted_action_id,
                "job_id": uuid4(),
                "run_id": self.run_id,
                "capability_id": "linkfinder",
                "profile_id": "js-analysis",
                "node_id": "linkfinder",
                "event_name": "js_analysis_requested",
                "correlation_id": uuid4(),
                "status": "completed",
                "terminal_outcome": "completed",
                "attempt": 1,
                "target_count": 1,
                "started_at": self.now,
                "finished_at": self.now,
                "duration_ms": 1200,
                "error_count": 0,
                "error_message": None,
                "raw_artifact_count": 1,
                "raw_artifact_bytes": 400,
                "observed_hosts_count": 1,
                "observed_services_count": 1,
                "observed_endpoints_count": 9,
                "http_observation_count": 9,
                "javascript_reference_count": 12,
                "new_hosts_count": None,
                "new_services_count": None,
                "new_endpoints_count": None,
                "before_surface_snapshot_id": None,
                "after_surface_snapshot_id": None,
                "new_surface_nodes_count": None,
                "new_surface_edges_count": None,
                "new_surface_clusters_count": None,
                "new_surface_deltas_count": None,
                "new_graph_facts_count": None,
                "new_search_documents_count": None,
                "budget_limit": {},
                "budget_spent": {},
                "manual_interest": True,
                "manual_stop": False,
                "continued_by_followup": True,
                "report_created": False,
                "triage_outcome": None,
                "information_gain_score": 0.74,
                "score_version": "v1",
                "score_breakdown": {},
                "metadata": {},
                "created_at": self.now,
                "updated_at": self.now,
            }])
        if "count(*)" in text and "FROM hosts" in text and "JOIN" not in text:
            return _Result(scalar=3)
        if "count(*)" in text and "FROM endpoints JOIN hosts" in text:
            return _Result(scalar=41)
        if "count(*)" in text and "FROM http_observations" in text:
            return _Result(scalar=16)
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
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self.session


@pytest.mark.asyncio
async def test_agent_task_detail_assembles_thread_proposals_actions_outcomes_and_compact_context() -> None:
    program_id = uuid4()
    campaign_id = uuid4()
    task_id = uuid4()
    session = _Session(program_id=program_id, campaign_id=campaign_id, task_id=task_id)
    service = AgentTaskDetailService(AgentTaskDetailStore(_SessionFactory(session)))

    detail = await service.get_task_detail(task_id=task_id)

    assert detail is not None
    assert detail.task.task_id == task_id
    assert detail.task.title == "Разобрать JS пути"
    assert len(detail.messages) == 2
    assert detail.decisions[0].message_kind.value == "decision"
    assert detail.proposals[0].status.value == "accepted"
    assert detail.accepted_actions[0].capability_id == "linkfinder"
    assert detail.related_outcomes[0].information_gain_score == 0.74
    assert detail.compact_context.thread_summary["messages"] == 2
    assert detail.compact_context.proposal_summary["accepted"] == 1
    assert detail.compact_context.action_summary["queued"] == 1
    assert detail.compact_context.outcome_summary["high_gain_outcomes"] == 1
    assert detail.compact_context.agent_runtime_usage.runtime_decision_messages == 1
    assert detail.compact_context.agent_runtime_usage.selected_modes["cheap"] == 1
    assert detail.compact_context.agent_runtime_usage.llm_allowed_messages == 1
    assert detail.compact_context.surface_summary["counts"] == {
        "hosts": 3,
        "endpoints": 41,
        "http_observations": 16,
        "javascript_references": 12,
    }
    assert detail.compact_context.last_user_message_excerpt.startswith("Разбери новые JS")
    assert detail.compact_context.boundaries["raw_artifact_access"] == "forbidden"
    assert detail.counts == {
        "messages": 2,
        "proposals": 1,
        "pending_proposals": 0,
        "decisions": 1,
        "accepted_actions": 1,
        "related_outcomes": 1,
        "agent_runtime_decisions": 1,
        "agent_runtime_llm_allowed": 1,
        "agent_runtime_deep_downgraded": 0,
    }
    assert not any("raw_artifacts" in query for query in session.queries)


def test_agent_task_detail_tables_exist_without_new_migration() -> None:
    for table_name in (
        "agent_tasks",
        "agent_task_messages",
        "agent_action_proposals",
        "action_requests",
        "action_outcomes",
        "hosts",
        "endpoints",
        "http_observations",
        "javascript_references",
    ):
        assert table_name in metadata.tables


def test_agent_task_detail_source_does_not_expose_internal_engines_or_raw_artifacts() -> None:
    source = Path("src/api/infrastructure/agent_task_detail.py").read_text(encoding="utf-8")
    route_source = Path("src/api/presentation/rest/routes/agent_tasks.py").read_text(encoding="utf-8")

    assert "gds." not in source.lower()
    assert "raw_artifacts" not in source
    assert "run gds" not in route_source.lower()
    assert "does not execute agents, GDS, or tools" in route_source
