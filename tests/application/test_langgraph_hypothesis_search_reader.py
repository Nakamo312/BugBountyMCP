from __future__ import annotations

from uuid import uuid4

from api.config import Settings
from api.infrastructure.langgraph_context import OpenSearchSanitizedSearchReader


class FakeResponse:
    def __init__(self) -> None:
        self.payload = {
            "hits": {
                "hits": [
                    {
                        "_id": "hyp-1",
                        "_score": 1.0,
                        "_source": {
                            "hypothesis_id": "hyp-1",
                            "program_id": "program-1",
                            "safe_evidence_text": ["safe excerpt"],
                        },
                    }
                ]
            }
        }

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


def test_opensearch_hypothesis_search_uses_restricted_query(monkeypatch) -> None:
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setattr("api.infrastructure.langgraph_context.requests.post", fake_post)
    settings = Settings(OPENSEARCH_URL="http://opensearch:9200")
    reader = OpenSearchSanitizedSearchReader(settings)
    program_id = uuid4()

    result = reader._search_hypotheses_sync(
        program_id=program_id,
        status="needs_verification",
        hypothesis_type="graph_surface_followup",
        min_priority_score=70,
        limit=500,
    )

    url, kwargs = calls[0]
    request = kwargs["json"]
    assert url == "http://opensearch:9200/bb-research-hypotheses/_search"
    assert request["size"] == 100
    assert {"term": {"program_id": str(program_id)}} in request["query"]["bool"]["filter"]
    assert {"term": {"status": "needs_verification"}} in request["query"]["bool"]["filter"]
    assert {"term": {"hypothesis_type": "graph_surface_followup"}} in request["query"]["bool"]["filter"]
    assert {"range": {"priority_score": {"gte": 70}}} in request["query"]["bool"]["filter"]
    assert "safe_evidence_text" in request["_source"]["includes"]
    assert "claim" not in request["_source"]["includes"]
    assert "raw_content" not in request["_source"]["includes"]
    assert result["index"] == "bb-research-hypotheses"
    assert result["hits"][0]["hypothesis_id"] == "hyp-1"
