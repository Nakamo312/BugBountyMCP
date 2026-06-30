from __future__ import annotations

import asyncio

import pytest

from api.application.pipeline.registry import NodeRegistry
from api.config import Settings


class RecordingBus:
    requires_bound_job_id_for_recording = False

    def __init__(self) -> None:
        self.connected = False
        self.subscriptions: list[str] = []

    async def connect(self) -> None:
        self.connected = True

    async def publish(
        self,
        event,
        *,
        record_event: bool = True,
        routing_key: str | None = None,
    ) -> None:
        return None

    async def subscribe(self, queue_name: str, callback) -> None:
        self.subscriptions.append(queue_name)


@pytest.mark.asyncio
async def test_node_registry_start_requires_infrastructure_subscription_queues() -> None:
    bus = RecordingBus()
    registry = NodeRegistry(bus, Settings())

    with pytest.raises(
        RuntimeError,
        match="NodeRegistry requires subscription queues from infrastructure wiring",
    ):
        await registry.start()

    assert bus.connected is False
    assert bus.subscriptions == []

@pytest.mark.asyncio
async def test_node_registry_subscribes_to_infrastructure_queues() -> None:
    bus = RecordingBus()
    registry = NodeRegistry(
        bus,
        Settings(),
        subscription_queues=("discovery", "validation"),
    )

    await registry.start()
    try:
        await asyncio.sleep(0)

        assert bus.connected is True
        assert sorted(bus.subscriptions) == ["discovery", "validation"]
    finally:
        await registry.stop()
