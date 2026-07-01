from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from api.application.contracts import EventEnvelope, NodeRunClaim, ExecutionStatus, NodeRunClaimRequest
from api.infrastructure.pipeline.builder import build_node
from api.application.pipeline.context import PipelineContext
from api.application.pipeline.fingerprints import build_node_work_key
from api.application.pipeline.registry import NodeRegistry
from api.application.pipeline.yaml_config import load_pipeline_config
from api.config import Settings


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)


class RecordingClaimStore:
    def __init__(self) -> None:
        self.claims: list[NodeRunClaimRequest] = []

    async def claim_node_run(self, request: NodeRunClaimRequest) -> NodeRunClaim:
        self.claims.append(request)
        return NodeRunClaim(
            run_id=uuid4(),
            claim_key=request.claim_key,
            status=ExecutionStatus.QUEUED,
        )


def test_event_envelope_roundtrips_campaign_expansion_context() -> None:
    campaign_id = uuid4()
    envelope = EventEnvelope(
        event="host_discovered",
        program_id=uuid4(),
        campaign_id=campaign_id,
        expansion_depth=3,
    )

    restored = EventEnvelope.from_legacy(envelope.to_legacy_dict())

    assert restored.campaign_id == campaign_id
    assert restored.expansion_depth == 3


def test_event_envelope_payload_cannot_override_typed_legacy_fields() -> None:
    program_id = uuid4()
    payload_program_id = uuid4()
    envelope = EventEnvelope(
        event="host_discovered",
        program_id=program_id,
        targets=["https://example.com"],
        payload={
            "event": "forged_event",
            "program_id": str(payload_program_id),
            "targets": ["https://evil.example"],
            "timeout": 10,
        },
    )

    legacy = envelope.to_legacy_dict()

    assert legacy["event"] == "host_discovered"
    assert legacy["program_id"] == str(program_id)
    assert legacy["targets"] == ["https://example.com"]
    assert legacy["timeout"] == 10
    assert legacy["payload"]["event"] == "forged_event"


@pytest.mark.asyncio
async def test_pipeline_context_inherits_campaign_and_increments_depth() -> None:
    bus = RecordingBus()
    campaign_id = uuid4()
    correlation_id = uuid4()
    parent_event_id = uuid4()
    context = PipelineContext(node_id="httpx", bus=bus)
    context.bind_event(
        {
            "event": "host_discovered",
            "event_id": str(parent_event_id),
            "job_id": str(uuid4()),
            "run_id": str(uuid4()),
            "campaign_id": str(campaign_id),
            "correlation_id": str(correlation_id),
            "expansion_depth": 2,
        }
    )

    await context.emit(
        event="http_service_discovered",
        targets=["https://example.com"],
        program_id=uuid4(),
    )

    emitted = bus.events[0]
    assert emitted.campaign_id == campaign_id
    assert emitted.expansion_depth == 3
    assert emitted.correlation_id == correlation_id
    assert emitted.causation_id == parent_event_id


def test_pipeline_workers_receive_bounded_expansion_settings() -> None:
    config = load_pipeline_config()
    spec = config.workers["httpx"]

    assert spec.cooldown_seconds == 300
    assert spec.max_fanout_per_event == 20
    assert spec.max_expansion_depth == 6
    assert spec.token_cost == 1

    node = build_node("httpx", spec, Settings())

    assert node.cooldown_seconds == 300
    assert node.max_fanout_per_event == 20
    assert node.max_expansion_depth == 6
    assert node.token_cost == 1


def test_scheduled_chunk_fanout_respects_worker_limit() -> None:
    config = load_pipeline_config()
    node = build_node("httpx", config.workers["httpx"], Settings())
    registry = NodeRegistry(RecordingBus(), Settings())
    targets = [f"host-{index}.example.com" for index in range(2101)]

    chunks = registry._claim_events_for_node(
        node,
        {"targets": targets},
    )

    assert len(chunks) == 20
    assert sum(len(chunk["targets"]) for chunk in chunks) == 2000


def test_work_key_isolated_by_campaign() -> None:
    common = {
        "program_id": uuid4(),
        "node_id": "httpx",
        "event_name": "host_discovered",
        "targets": ["example.com"],
    }

    first = build_node_work_key(**common, campaign_id=uuid4())
    second = build_node_work_key(**common, campaign_id=uuid4())

    assert first != second


@pytest.mark.asyncio
async def test_registry_passes_expansion_limits_to_scheduled_claim() -> None:
    config = load_pipeline_config()
    node = build_node("httpx", config.workers["httpx"], Settings())
    store = RecordingClaimStore()
    registry = NodeRegistry(
        RecordingBus(),
        Settings(),
        node_run_claims=store,
    )
    registry._nodes[node.node_id] = node
    campaign_id = uuid4()
    event = {
        "event": "host_discovered",
        "event_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "program_id": str(uuid4()),
        "campaign_id": str(campaign_id),
        "correlation_id": str(uuid4()),
        "expansion_depth": 4,
        "targets": ["example.com"],
    }

    await registry._claim_event_for_node("httpx", "host_discovered", event)

    claim = store.claims[0]
    assert claim.campaign_id == campaign_id
    assert claim.expansion_depth == 4
    assert claim.max_expansion_depth == 6
    assert claim.cooldown_seconds == 300
    assert claim.token_cost == 1
    assert claim.target_count == 1
    assert claim.run_payload["targets"] == ["example.com"]
    assert claim.coalesced_trigger["trigger_event_id"] == event["event_id"]
    assert claim.work_key is not None
