from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.application.event_contracts import EventEnvelope, EventType
from api.application.services.mapcidr import MapCIDRService


class FakeMapCIDRRunner:
    async def run(self, values: list[str], **options):
        mode = options["mode"]
        if mode == "expand":
            outputs = ["192.0.2.1", "192.0.2.2"]
        elif mode.startswith("slice_"):
            outputs = ["192.0.2.0/31"]
        elif mode == "aggregate":
            outputs = ["192.0.2.0/24"]
        else:  # pragma: no cover - defensive fixture guard
            outputs = []
        for output in outputs:
            yield SimpleNamespace(type="result", payload=output)


class FakeMapCIDRRunnerFactory:
    def create(self, tool_name: str) -> FakeMapCIDRRunner:
        assert tool_name == "mapcidr"
        return FakeMapCIDRRunner()


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    @property
    def requires_bound_job_id_for_recording(self) -> bool:
        return False

    async def connect(self) -> None:
        pass

    async def publish(
        self,
        event: EventEnvelope,
        *,
        record_event: bool = True,
        routing_key: str | None = None,
    ) -> None:
        assert isinstance(event, EventEnvelope)
        self.events.append(event)


@pytest.mark.asyncio
async def test_mapcidr_expand_publishes_typed_event_envelope() -> None:
    bus = RecordingBus()
    service = MapCIDRService(
        runner_factory=FakeMapCIDRRunnerFactory(),  # type: ignore[arg-type]
        bus=bus,
    )
    program_id = uuid4()

    result = await service.expand(program_id, ["192.0.2.0/30"], skip_base=True)

    assert result.output_count == 2
    assert len(bus.events) == 1
    envelope = bus.events[0]
    assert envelope.event == EventType.IPS_EXPANDED.value
    assert envelope.program_id == program_id
    assert envelope.targets == ["192.0.2.1", "192.0.2.2"]
    assert envelope.source == "mapcidr"
    assert envelope.payload == {
        "ips": ["192.0.2.1", "192.0.2.2"],
        "source_cidrs": ["192.0.2.0/30"],
    }

    legacy = envelope.to_legacy_dict()
    assert legacy["ips"] == ["192.0.2.1", "192.0.2.2"]
    assert legacy["source_cidrs"] == ["192.0.2.0/30"]


@pytest.mark.asyncio
async def test_mapcidr_slice_and_aggregate_publish_typed_event_envelopes() -> None:
    bus = RecordingBus()
    service = MapCIDRService(
        runner_factory=FakeMapCIDRRunnerFactory(),  # type: ignore[arg-type]
        bus=bus,
    )
    program_id = uuid4()

    await service.slice_by_count(program_id, ["192.0.2.0/24"], count=2)
    await service.slice_by_host_count(program_id, ["192.0.2.0/24"], host_count=64)
    await service.aggregate(program_id, ["192.0.2.1", "192.0.2.2"])

    assert [event.event for event in bus.events] == [
        EventType.CIDR_SLICED.value,
        EventType.CIDR_SLICED.value,
        EventType.IPS_AGGREGATED.value,
    ]
    assert all(isinstance(event, EventEnvelope) for event in bus.events)
    assert bus.events[0].payload == {
        "cidrs": ["192.0.2.0/31"],
        "source_cidrs": ["192.0.2.0/24"],
    }
    assert bus.events[2].payload == {
        "cidrs": ["192.0.2.0/24"],
        "source_ips": ["192.0.2.1", "192.0.2.2"],
    }
