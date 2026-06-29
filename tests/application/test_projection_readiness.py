from __future__ import annotations

from api.application.projections import (
    ProjectionKey,
    ProjectionLagState,
    ProjectionReadinessService,
    evaluate_projection_readiness,
)


OPENSEARCH_HTTP = ProjectionKey("opensearch", "http-observations")
OPENSEARCH_ENDPOINTS = ProjectionKey("opensearch", "endpoints")


def test_projection_readiness_requires_every_named_projection() -> None:
    result = evaluate_projection_readiness(
        states=[
            ProjectionLagState(
                key=OPENSEARCH_HTTP,
                status="ready",
                source_watermark="42",
                applied_watermark="42",
                lag_count=0,
            )
        ],
        required=[OPENSEARCH_HTTP, OPENSEARCH_ENDPOINTS],
    )

    assert result.ready is False
    assert result.missing == (OPENSEARCH_ENDPOINTS,)


def test_projection_readiness_rejects_lag_failed_and_mismatched_watermarks() -> None:
    states = [
        ProjectionLagState(OPENSEARCH_HTTP, "ready", "43", "42", 1),
        ProjectionLagState(OPENSEARCH_ENDPOINTS, "failed", "9", "9", 0),
    ]

    result = evaluate_projection_readiness(
        states=states,
        required=[OPENSEARCH_HTTP, OPENSEARCH_ENDPOINTS],
    )

    assert result.ready is False
    assert result.lagging == (OPENSEARCH_HTTP,)
    assert result.failed == (OPENSEARCH_ENDPOINTS,)


def test_projection_readiness_is_true_only_for_zero_lag_matching_watermarks() -> None:
    states = [
        ProjectionLagState(OPENSEARCH_HTTP, "ready", "42", "42", 0),
        ProjectionLagState(OPENSEARCH_ENDPOINTS, "ready", "9", "9", 0),
    ]

    result = evaluate_projection_readiness(
        states=states,
        required=[OPENSEARCH_HTTP, OPENSEARCH_ENDPOINTS],
    )

    assert result.ready is True
    assert result.missing == ()
    assert result.lagging == ()
    assert result.failed == ()


class StubProjectionStateReader:
    def __init__(self, states: list[ProjectionLagState]) -> None:
        self.states = states
        self.calls: list[tuple[object, tuple[ProjectionKey, ...]]] = []

    async def list_states(self, *, program_id, required):
        self.calls.append((program_id, tuple(required)))
        return self.states


async def test_projection_readiness_service_reads_program_scoped_state() -> None:
    reader = StubProjectionStateReader(
        [ProjectionLagState(OPENSEARCH_HTTP, "ready", "42", "42", 0)]
    )
    service = ProjectionReadinessService(reader)

    result = await service.evaluate(
        program_id="program-1",
        required=[OPENSEARCH_HTTP],
    )

    assert result.ready is True
    assert reader.calls == [("program-1", (OPENSEARCH_HTTP,))]
