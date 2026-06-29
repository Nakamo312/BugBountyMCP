from __future__ import annotations

from pathlib import Path


def test_agent_protocol_routes_expose_m6_coordination_endpoints() -> None:
    source = Path("src/api/presentation/rest/routes/agent_protocol.py").read_text(
        encoding="utf-8"
    )
    router_source = Path("src/api/presentation/rest/routes/__init__.py").read_text(
        encoding="utf-8"
    )
    di_source = Path("src/api/application/di.py").read_text(encoding="utf-8")

    for endpoint in (
        '@router.post("/subscriptions"',
        '@router.get("/inbox"',
        '@router.post("/inbox/claim"',
        '@router.post("/inbox/{message_id}/ack"',
        '@router.post("/workflows/{run_id}/cancel"',
        '@router.post("/wait-conditions"',
        '@router.get("/wait-conditions"',
        '@router.post("/result-sets"',
        '@router.get("/result-sets"',
        '@router.post("/task-runtime-results"',
        '@router.post("/tasks/{task_id}/messages"',
    ):
        assert endpoint in source

    assert "AgentProtocolStore" in source
    assert "LangGraphWorkflowRuntime" in source
    assert "AgentTaskAgentReplyRequest" in source
    assert "Depends(require_agent_protocol_internal_access)" in source
    assert "AgentProtocolStore" in di_source
    assert "agent_protocol_router" in router_source
    security_source = Path("src/api/presentation/rest/security.py").read_text(encoding="utf-8")
    assert "X-Agent-Actor" in security_source
    assert "X-Agent-Internal-Token" in security_source
    assert "inbox_key" in source
    assert "message_type" in source
    assert "AgentTaskRuntimeResultIngestService" in source
    assert "AGENT_PROTOCOL_INTERNAL_TOKEN" in Path("src/api/config.py").read_text(encoding="utf-8")
    assert 'prefix="/api/v1/agent"' in router_source


def test_agent_protocol_api_does_not_expose_execution_shortcuts() -> None:
    source = Path("src/api/presentation/rest/routes/agent_protocol.py").read_text(
        encoding="utf-8"
    )

    forbidden = (
        "subprocess",
        "shell",
        "RabbitMQ",
        "event_bus.publish",
        "raw_artifacts",
        "session.execute",
    )
    for token in forbidden:
        assert token not in source
