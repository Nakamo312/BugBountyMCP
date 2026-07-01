from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.langgraph_context_tools import (
    LangGraphContextTools,
    ProgramBoundaryError,
    RawArtifactAccessDenied,
    InvalidHypothesisSearch,
)


class FakeProgramReader:
    async def list_hosts(self, *, program_id, limit):
        return [{"id": "host-1", "program_id": program_id, "host": "example.com"}]

    async def list_services(self, *, program_id, limit):
        return [{"id": "svc-1", "program_id": program_id, "port": 443}]

    async def list_endpoints(self, *, program_id, limit):
        return [{"id": "ep-1", "program_id": program_id, "path": "/api"}]


class FakeResultSetReader:
    async def list_result_sets(self, **kwargs):
        return [{"id": "rs-1", "program_id": kwargs["program_id"], "result_key": "k"}]


class FakeArtifactPreviewReader:
    async def list_bodies(self, **kwargs):
        return [
            {
                "id": "body-1",
                "program_id": kwargs["program_id"],
                "body_preview": "safe excerpt",
                "body_content": "must be stripped",
            }
        ]


class FakeRawArtifactPreviewReader:
    async def list_bodies(self, **kwargs):
        return [
            {
                "artifact_id": "artifact-1",
                "program_id": kwargs["program_id"],
                "sanitized_preview": "Authorization: [redacted]",
                "sanitized_safe_for_llm": True,
                "preview": "Authorization: Bearer secret",
                "raw_safe_for_llm": False,
            }
        ]


class FakeSearchReader:
    def __init__(self) -> None:
        self.calls = []
        self.hypothesis_calls = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return {"hits": [{"program_id": kwargs["program_id"], "id": "doc-1"}]}

    async def search_hypotheses(self, **kwargs):
        self.hypothesis_calls.append(kwargs)
        return {
            "hits": [
                {
                    "hypothesis_id": "hyp-1",
                    "program_id": kwargs["program_id"],
                    "hypothesis_type": kwargs.get("hypothesis_type"),
                    "status": kwargs.get("status") or "needs_verification",
                    "priority_score": 85,
                    "confidence": 0.7,
                    "evidence_count": 2,
                    "safe_evidence_text": ["safe only"],
                    "raw_content": "must be stripped",
                    "claim": "must not be projected",
                    "_score": 1.0,
                }
            ]
        }


class FakeGraphTemplateRenderer:
    def render(self, *, template_name, parameters):
        return {
            "template_name": template_name,
            "cypher": "MATCH (n {program_id: $program_id}) RETURN n LIMIT $limit",
            "parameters": parameters,
        }


def _tools(**overrides):
    dependencies = {
        "program_reader": FakeProgramReader(),
        "result_set_reader": FakeResultSetReader(),
        "artifact_preview_reader": FakeArtifactPreviewReader(),
        "search_reader": FakeSearchReader(),
        "graph_renderer": FakeGraphTemplateRenderer(),
    }
    dependencies.update(overrides)
    return LangGraphContextTools(**dependencies)


async def test_context_tools_return_program_context_without_raw_bodies() -> None:
    program_id = uuid4()
    context = await _tools().program_context(program_id=program_id, limit=5)

    assert context["program_id"] == str(program_id)
    assert context["hosts"][0]["host"] == "example.com"
    assert context["services"][0]["port"] == 443
    assert context["endpoints"][0]["path"] == "/api"
    assert "body_content" not in str(context)


async def test_context_tools_fetch_result_sets_with_program_boundary() -> None:
    program_id = uuid4()

    result = await _tools().result_sets(program_id=program_id, action_id=uuid4())

    assert result["items"][0]["program_id"] == str(program_id)


async def test_context_tools_reject_cross_program_result_sets() -> None:
    class CrossProgramResultSetReader:
        async def list_result_sets(self, **kwargs):
            return [{"id": "rs-1", "program_id": uuid4(), "result_key": "k"}]

    with pytest.raises(ProgramBoundaryError):
        await _tools(result_set_reader=CrossProgramResultSetReader()).result_sets(
            program_id=uuid4()
        )


async def test_context_tools_searches_sanitized_opensearch_with_program_filter() -> None:
    program_id = uuid4()
    search_reader = FakeSearchReader()

    result = await _tools(search_reader=search_reader).opensearch_search(
        program_id=program_id,
        index="bb-http-observations",
        query="login",
        limit=10,
    )

    assert result["hits"][0]["program_id"] == str(program_id)
    assert search_reader.calls == [
        {
            "program_id": program_id,
            "index": "bb-http-observations",
            "query": "login",
            "limit": 10,
        }
    ]


async def test_context_tools_render_graph_template_with_program_boundary() -> None:
    program_id = uuid4()

    rendered = await _tools().graph_template_query(
        program_id=program_id,
        template_name="asset_exposure",
        parameters={"program_id": uuid4(), "limit": 500},
    )

    assert rendered["parameters"]["program_id"] == str(program_id)
    assert rendered["parameters"]["limit"] == 100
    assert "MATCH" in rendered["cypher"]


async def test_context_tools_return_sanitized_artifact_previews_only() -> None:
    program_id = uuid4()

    result = await _tools().artifact_previews(program_id=program_id)

    assert result["items"] == [
        {
            "id": "body-1",
            "program_id": str(program_id),
            "body_preview": "safe excerpt",
        }
    ]


async def test_context_tools_never_return_raw_preview_fields() -> None:
    program_id = uuid4()

    result = await _tools(
        artifact_preview_reader=FakeRawArtifactPreviewReader()
    ).artifact_previews(program_id=program_id)

    assert result["items"] == [
        {
            "artifact_id": "artifact-1",
            "program_id": str(program_id),
            "sanitized_preview": "Authorization: [redacted]",
            "sanitized_safe_for_llm": True,
            "raw_safe_for_llm": False,
        }
    ]


async def test_context_tools_deny_raw_artifact_fetch() -> None:
    with pytest.raises(RawArtifactAccessDenied):
        await _tools().raw_artifact(artifact_id=uuid4())


def test_context_tools_are_wired_without_execution_surfaces() -> None:
    app_source = open("src/api/application/langgraph_context_tools.py", encoding="utf-8").read()
    infra_source = open("src/api/infrastructure/langgraph_context.py", encoding="utf-8").read()
    wiring_source = open("src/api/infrastructure/providers/research_runtime.py", encoding="utf-8").read()

    assert "LangGraphContextTools" in wiring_source
    assert "PostgresArtifactReader" in wiring_source
    assert "OpenSearchSanitizedSearchReader" in wiring_source
    assert "SafeGraphTemplateRenderer" in wiring_source
    assert "default_query_template_registry" in infra_source
    for forbidden in ("RabbitMQ", "EventBus", "runner", "subprocess", "raw_artifacts"):
        assert forbidden not in app_source

async def test_context_tools_search_hypotheses_uses_restricted_template() -> None:
    program_id = uuid4()
    search_reader = FakeSearchReader()

    result = await _tools(search_reader=search_reader).search_hypotheses(
        program_id=program_id,
        status="needs_verification",
        hypothesis_type="graph_surface_followup",
        min_priority_score=70,
        limit=500,
    )

    assert result["index"] == "bb-research-hypotheses"
    assert result["program_id"] == str(program_id)
    assert result["hits"] == [
        {
            "hypothesis_id": "hyp-1",
            "program_id": str(program_id),
            "hypothesis_type": "graph_surface_followup",
            "status": "needs_verification",
            "priority_score": 85,
            "confidence": 0.7,
            "evidence_count": 2,
            "safe_evidence_text": ["safe only"],
        }
    ]
    assert search_reader.hypothesis_calls == [
        {
            "program_id": program_id,
            "status": "needs_verification",
            "hypothesis_type": "graph_surface_followup",
            "min_priority_score": 70,
            "limit": 100,
        }
    ]


async def test_context_tools_search_hypotheses_rejects_invalid_filters() -> None:
    tools = _tools()
    program_id = uuid4()

    with pytest.raises(InvalidHypothesisSearch):
        await tools.search_hypotheses(program_id=program_id, status="raw")

    with pytest.raises(InvalidHypothesisSearch):
        await tools.search_hypotheses(program_id=program_id, min_priority_score=101)

    with pytest.raises(InvalidHypothesisSearch):
        await tools.search_hypotheses(
            program_id=program_id,
            hypothesis_type='graph_surface_followup" OR *',
        )


async def test_context_tools_search_hypotheses_rejects_cross_program_hits() -> None:
    class CrossProgramHypothesisSearchReader(FakeSearchReader):
        async def search_hypotheses(self, **kwargs):
            return {
                "hits": [
                    {
                        "hypothesis_id": "hyp-cross",
                        "program_id": uuid4(),
                        "status": "needs_verification",
                    }
                ]
            }

    with pytest.raises(ProgramBoundaryError):
        await _tools(search_reader=CrossProgramHypothesisSearchReader()).search_hypotheses(
            program_id=uuid4(),
            status="needs_verification",
        )


async def test_context_tools_search_hypotheses_filters_multiple_statuses_locally() -> None:
    class MultiStatusSearchReader(FakeSearchReader):
        async def search_hypotheses(self, **kwargs):
            self.hypothesis_calls.append(kwargs)
            return {
                "hits": [
                    {"hypothesis_id": "hyp-1", "program_id": kwargs["program_id"], "status": "new"},
                    {"hypothesis_id": "hyp-2", "program_id": kwargs["program_id"], "status": "stale"},
                ]
            }

    program_id = uuid4()
    search_reader = MultiStatusSearchReader()

    result = await _tools(search_reader=search_reader).search_hypotheses(
        program_id=program_id,
        status=["new", "needs_verification"],
    )

    assert [item["hypothesis_id"] for item in result["hits"]] == ["hyp-1"]
    assert search_reader.hypothesis_calls[0]["status"] is None


async def test_context_tools_select_hypotheses_returns_policy_decisions() -> None:
    class SelectionSearchReader(FakeSearchReader):
        async def search_hypotheses(self, **kwargs):
            self.hypothesis_calls.append(kwargs)
            return {
                "hits": [
                    {
                        "hypothesis_id": "hyp-ready",
                        "program_id": kwargs["program_id"],
                        "hypothesis_type": "graph_surface_followup",
                        "status": "needs_verification",
                        "priority_score": 85,
                        "confidence": 0.7,
                        "evidence_count": 2,
                        "evidence_roles": ["primary"],
                        "safe_evidence_text": ["safe excerpt"],
                        "raw_content": "must be stripped before selection",
                    }
                ]
            }

    program_id = uuid4()
    search_reader = SelectionSearchReader()

    result = await _tools(search_reader=search_reader).select_hypotheses(
        program_id=program_id,
        min_priority_score=50,
        limit=500,
    )

    assert result["program_id"] == str(program_id)
    assert result["source_index"] == "bb-research-hypotheses"
    assert result["decisions"] == [
        {
            "hypothesis_id": "hyp-ready",
            "next_step": "critic_review",
            "priority_band": "critical",
            "reasons": ["ready_for_critic", "priority_threshold_met"],
            "requires_human_review": False,
            "safe_context": {
                "hypothesis_id": "hyp-ready",
                "program_id": str(program_id),
                "hypothesis_type": "graph_surface_followup",
                "status": "needs_verification",
                "priority_score": 85,
                "confidence": 0.7,
                "evidence_count": 2,
                "evidence_roles": ["primary"],
                "safe_evidence_text": ["safe excerpt"],
            },
        }
    ]
    assert search_reader.hypothesis_calls[0]["limit"] == 100
    assert "raw_content" not in str(result)
