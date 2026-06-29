from __future__ import annotations

from pathlib import Path


def test_cypher_gateway_route_exposes_single_safe_boundary() -> None:
    route_source = Path("src/api/presentation/rest/routes/graph.py").read_text(encoding="utf-8")
    router_source = Path("src/api/presentation/rest/routes/__init__.py").read_text(encoding="utf-8")
    di_source = Path("src/api/application/di.py").read_text(encoding="utf-8")

    assert '@router.post("/cypher")' in route_source
    assert "CypherGateway" in route_source
    assert "debug_approved" in route_source
    assert "CypherAccessDenied" in route_source
    assert "status_code=403" in route_source
    assert 'prefix="/api/v1/graph"' in router_source
    assert "get_cypher_gateway" in di_source
    assert "CypherGateway" not in Path("src/api/application/langgraph_context_tools.py").read_text(encoding="utf-8")
    for forbidden in ("session.run", "GraphDatabase", "subprocess", "RabbitMQ"):
        assert forbidden not in route_source
