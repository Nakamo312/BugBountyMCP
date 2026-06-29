from __future__ import annotations

from api.application.agent_action_proposals import AgentActionProposalType
from api.application.agent_task_roles import AgentTaskRoleComposer, normalize_agent_role
from api.application.agent_tasks import AgentTaskMessageKind, AgentTaskStatus


def test_agent_role_composer_routes_surface_to_finding_with_surface_refs() -> None:
    composer = AgentTaskRoleComposer()

    reply = composer.compose(
        target_agent="surface",
        body_excerpt="Разбери api/account/*",
        context={
            "context_refs": [
                {"kind": "surface", "id": "api/account", "count": 7},
                {"kind": "graph", "id": "cluster-account"},
                {"kind": "artifact", "id": "raw-1"},
            ]
        },
    )

    assert reply.agent_key == "surface"
    assert reply.message_kind is AgentTaskMessageKind.FINDING
    assert reply.status is AgentTaskStatus.WAITING
    assert "агент поверхности" in reply.body
    assert "surface: 1" in reply.body
    assert reply.fact_refs == ({"kind": "surface", "id": "api/account", "count": 7},)
    assert reply.graph_refs == ({"kind": "graph", "id": "cluster-account"},)
    assert reply.metadata["agent_role"] == "surface"
    assert reply.metadata["tool_execution"] == "forbidden_from_role_node"
    assert reply.proposal_drafts
    assert reply.proposal_drafts[0].proposal_type is AgentActionProposalType.INVESTIGATION_TASK
    assert reply.proposal_drafts[0].metadata["action_service_required"] is True


def test_agent_role_composer_routes_artifacts_to_artifact_refs() -> None:
    composer = AgentTaskRoleComposer()

    reply = composer.compose(
        target_agent="артефакты",
        body_excerpt="Покажи новые JS пути",
        context={
            "context_refs": [
                {"kind": "artifact", "id": "js-linkfinder-1"},
                {"kind": "fact", "id": "path-1"},
            ]
        },
    )

    assert reply.agent_key == "artifacts"
    assert reply.message_kind is AgentTaskMessageKind.FINDING
    assert "агент артефактов" in reply.body
    assert reply.artifact_refs == ({"kind": "artifact", "id": "js-linkfinder-1"},)
    assert reply.fact_refs == ({"kind": "fact", "id": "path-1"},)


def test_agent_role_composer_critic_is_question_not_execution() -> None:
    composer = AgentTaskRoleComposer()

    reply = composer.compose(
        target_agent="critic",
        body_excerpt="Стоит ли продолжать nuclei?",
        context={"context_refs": [{"kind": "decision", "id": "noise-stop"}]},
    )

    assert reply.agent_key == "critic"
    assert reply.message_kind is AgentTaskMessageKind.QUESTION
    assert "повторы" in reply.body
    assert reply.decision_refs == ({"kind": "decision", "id": "noise-stop"},)


def test_agent_role_composer_unknown_role_falls_back_to_coordinator() -> None:
    reply = AgentTaskRoleComposer().compose(
        target_agent="unknown-agent",
        body_excerpt="Что дальше?",
        context={"context_refs": []},
    )

    assert reply.agent_key == "coordinator"
    assert reply.message_kind is AgentTaskMessageKind.PROPOSAL
    assert "не буду выдумывать найденное" in reply.body


def test_normalize_agent_role_aliases() -> None:
    assert normalize_agent_role("Координатор") == "coordinator"
    assert normalize_agent_role("agent-surface") == "surface"
    assert normalize_agent_role("агент-артефактов") == "artifacts"
    assert normalize_agent_role("КРИТИК") == "critic"
    assert normalize_agent_role("отчёт") == "report"


def test_surface_agent_reports_recent_http_samples_concretely() -> None:
    reply = AgentTaskRoleComposer().compose(
        target_agent="surface",
        body_excerpt="Что изменилось по поверхности?",
        context={
            "surface_summary": {
                "counts": {
                    "hosts": 3,
                    "endpoints": 42,
                    "http_observations": 64,
                    "javascript_references": 5,
                },
                "recent_http": [
                    {
                        "kind": "http_observation",
                        "observation_id": "obs-1",
                        "method": "GET",
                        "url_excerpt": "https://example.com/api/account/export",
                        "status_code": 200,
                        "content_type": "application/json",
                    }
                ],
            }
        },
    )

    assert "hosts 3, endpoints 42" in reply.body
    assert "GET https://example.com/api/account/export -> 200 application/json" in reply.body
    assert "Сгруппировать свежие HTTP observations" in reply.proposal_drafts[0].title
    assert reply.proposal_drafts[0].priority == "high"
    assert reply.metadata["context_summary"]["recent_http_count"] == 1


def test_artifact_agent_reports_recent_javascript_refs_concretely() -> None:
    reply = AgentTaskRoleComposer().compose(
        target_agent="artifacts",
        body_excerpt="Разбери JS",
        context={
            "surface_summary": {
                "counts": {"http_observations": 10, "javascript_references": 2},
                "recent_javascript": [
                    {
                        "kind": "javascript_reference",
                        "reference_id": "js-1",
                        "reference_type": "path",
                        "source_url_excerpt": "https://example.com/static/app.js",
                        "referenced_url_excerpt": "/api/billing/methods",
                    }
                ],
            }
        },
    )

    assert "path: https://example.com/static/app.js -> /api/billing/methods" in reply.body
    assert "Извлечь новые пути из JS refs" in reply.proposal_drafts[0].title
    assert reply.proposal_drafts[0].priority == "high"
    assert reply.metadata["context_summary"]["recent_javascript_count"] == 1


def test_coordinator_uses_pending_proposal_and_best_outcome() -> None:
    reply = AgentTaskRoleComposer().compose(
        target_agent="coordinator",
        body_excerpt="Что дальше?",
        context={
            "recent_outcomes": [
                {
                    "kind": "action_outcome",
                    "outcome_id": "low",
                    "capability_id": "httpx",
                    "profile_id": "probe",
                    "information_gain_score": 0.12,
                    "counts": {"endpoints": 3},
                },
                {
                    "kind": "action_outcome",
                    "outcome_id": "high",
                    "capability_id": "katana",
                    "profile_id": "passive-crawl",
                    "information_gain_score": 0.82,
                    "counts": {"endpoints": 36, "javascript_references": 4},
                    "human_feedback": {"continued_by_followup": True},
                },
            ],
            "pending_proposals": [
                {
                    "proposal_id": "proposal-1",
                    "capability_id": "linkfinder",
                    "profile_id": "js-analysis",
                    "utility_score": 0.74,
                    "sample_count": 9,
                }
            ],
        },
    )

    assert "katana/passive-crawl" in reply.body
    assert "gain 0.82" in reply.body
    assert "linkfinder/js-analysis" in reply.body
    assert "Разобрать pending proposal" in reply.proposal_drafts[0].title
    assert reply.proposal_drafts[0].priority == "high"
    assert reply.metadata["context_summary"]["strongest_outcome"]["outcome_id"] == "high"


def test_critic_calls_out_low_gain_and_manual_stop() -> None:
    reply = AgentTaskRoleComposer().compose(
        target_agent="critic",
        body_excerpt="Продолжать эту ветку?",
        context={
            "recent_outcomes": [
                {
                    "kind": "action_outcome",
                    "outcome_id": "noise-1",
                    "information_gain_score": 0.01,
                    "human_feedback": {"manual_stop": True},
                }
            ],
            "pending_proposals": [
                {"proposal_id": "p1", "human_stop_rate": 0.45, "utility_score": 0.2}
            ],
        },
    )

    assert "низкий information gain" in reply.body
    assert "manual stop" in reply.body
    assert "высокий human_stop_rate" in reply.body
    assert "stop/noise" in reply.proposal_drafts[0].title
    assert reply.proposal_drafts[0].risk_level == "medium"
