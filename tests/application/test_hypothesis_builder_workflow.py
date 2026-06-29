from __future__ import annotations

from uuid import uuid4

from api.application.hypotheses import (
    HypothesisBuilderWorkflow,
    HypothesisBuildRequest,
    StoredHypothesis,
)


class RecordingContextTools:
    def __init__(self, items):
        self.items = items
        self.calls = []

    async def result_sets(self, **kwargs):
        self.calls.append(kwargs)
        return {"program_id": str(kwargs["program_id"]), "items": self.items}


class RecordingHypothesisStore:
    def __init__(self) -> None:
        self.candidates = []

    async def upsert_candidate(self, candidate):
        self.candidates.append(candidate)
        return StoredHypothesis(
            hypothesis_id=uuid4(),
            program_id=candidate.program_id,
            hypothesis_type=candidate.hypothesis_type,
            status=candidate.status,
            priority_score=candidate.priority_score,
            confidence=candidate.confidence,
            evidence_count=len(candidate.evidence),
        )


async def test_hypothesis_builder_links_candidates_to_result_set_evidence_refs() -> None:
    program_id = uuid4()
    workflow_id = uuid4()
    workflow_run_id = uuid4()
    artifact_id = uuid4()
    store = RecordingHypothesisStore()
    context = RecordingContextTools(
        [
            {
                "program_id": str(program_id),
                "result_type": "surface_cluster",
                "result_key": "cluster:hidden-js-endpoints",
                "payload": {"label": "hidden JS endpoints"},
                "artifact_refs": [{"artifact_id": str(artifact_id), "role": "source"}],
                "fact_refs": [{"fact_id": "endpoint:/admin", "role": "candidate"}],
                "search_refs": [],
                "graph_refs": [{"template": "hidden_endpoints_from_js", "node_id": "Endpoint:/admin"}],
            }
        ]
    )
    workflow = HypothesisBuilderWorkflow(context_tools=context, hypothesis_store=store)

    result = await workflow.build_from_result_sets(
        HypothesisBuildRequest(
            program_id=program_id,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
            result_key="cluster:hidden-js-endpoints",
        )
    )

    assert len(result.hypotheses) == 1
    candidate = store.candidates[0]
    assert candidate.program_id == program_id
    assert candidate.hypothesis_type == "graph_surface_followup"
    assert candidate.status == "needs_verification"
    assert candidate.evidence
    assert result.candidates == (candidate,)
    assert {evidence.ref_type for evidence in candidate.evidence} == {
        "result_set",
        "artifact",
        "fact",
        "graph",
    }
    assert all(evidence.ref_id for evidence in candidate.evidence)
    assert result.finding_ids == ()
    assert context.calls[0]["workflow_id"] == workflow_id
    assert context.calls[0]["workflow_run_id"] == workflow_run_id


async def test_hypothesis_builder_skips_result_sets_without_evidence_refs() -> None:
    program_id = uuid4()
    store = RecordingHypothesisStore()
    context = RecordingContextTools(
        [
            {
                "program_id": str(program_id),
                "result_type": "empty",
                "result_key": "empty",
                "payload": {},
                "artifact_refs": [],
                "fact_refs": [],
                "search_refs": [],
                "graph_refs": [],
            }
        ]
    )
    workflow = HypothesisBuilderWorkflow(context_tools=context, hypothesis_store=store)

    result = await workflow.build_from_result_sets(HypothesisBuildRequest(program_id=program_id))

    assert result.hypotheses == ()
    assert result.candidates == ()
    assert result.finding_ids == ()
    assert store.candidates == []


def test_hypothesis_builder_does_not_import_finding_or_execution_surfaces() -> None:
    source = open("src/api/application/hypotheses.py", encoding="utf-8").read()

    for forbidden in (
        "Finding",
        "findings",
        "RabbitMQ",
        "EventBus",
        "runner",
        "subprocess",
        "request_action",
    ):
        assert forbidden not in source
