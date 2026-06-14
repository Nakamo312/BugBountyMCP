from __future__ import annotations

from uuid import uuid4

import pytest

from api.application.contracts import EventDispatchRecord, EventEnvelope
from api.infrastructure.events.dispatcher import EventDispatcher


class InMemoryDispatchStore:
    def __init__(self, records: list[EventDispatchRecord]) -> None:
        self.records = list(records)
        self.claims: list[dict] = []
        self.sent: list[tuple] = []
        self.failed: list[dict] = []

    async def claim_dispatches(self, **kwargs):
        self.claims.append(kwargs)
        records, self.records = self.records, []
        return records

    async def mark_sent(self, *, dispatch_id, dispatcher_id):
        self.sent.append((dispatch_id, dispatcher_id))
        return True

    async def mark_failed(self, **kwargs):
        self.failed.append(kwargs)
        return True


class RecordingEventBus:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.published: list[tuple[EventEnvelope, bool, str | None]] = []

    async def publish(self, event, *, record_event: bool = True, routing_key: str | None = None):
        self.published.append((event, record_event, routing_key))
        if self.fail:
            raise RuntimeError("rabbit down")


def _record(attempts: int = 0) -> EventDispatchRecord:
    envelope = EventEnvelope(
        event="httpx_scan_requested",
        program_id=uuid4(),
        targets=["https://example.com"],
        source="api",
        confidence=0.7,
    )
    return EventDispatchRecord(
        dispatch_id=uuid4(),
        event_id=envelope.event_id,
        destination="rabbitmq",
        routing_key="enumeration.httpx_scan_requested",
        attempts=attempts,
        envelope=envelope,
    )


@pytest.mark.asyncio
async def test_dispatcher_sends_stored_event_without_recording_again() -> None:
    record = _record()
    store = InMemoryDispatchStore([record])
    bus = RecordingEventBus()
    dispatcher = EventDispatcher(
        store=store,
        event_bus=bus,
        dispatcher_id="dispatcher-1",
        batch_size=25,
        lease_ttl_seconds=45,
    )

    sent = await dispatcher.send_once()

    assert sent == 1
    assert store.claims == [
        {
            "destination": "rabbitmq",
            "dispatcher_id": "dispatcher-1",
            "batch_size": 25,
            "lease_ttl_seconds": 45,
        }
    ]
    assert bus.published == [(record.envelope, False, record.routing_key)]
    assert store.sent == [(record.dispatch_id, "dispatcher-1")]
    assert store.failed == []


@pytest.mark.asyncio
async def test_dispatcher_records_failure_for_retry() -> None:
    record = _record(attempts=2)
    store = InMemoryDispatchStore([record])
    bus = RecordingEventBus(fail=True)
    dispatcher = EventDispatcher(
        store=store,
        event_bus=bus,
        dispatcher_id="dispatcher-2",
        max_attempts=5,
        retry_delay_seconds=9,
    )

    sent = await dispatcher.send_once()

    assert sent == 1
    assert store.sent == []
    assert len(store.failed) == 1
    failure = store.failed[0]
    assert failure["dispatch_id"] == record.dispatch_id
    assert failure["dispatcher_id"] == "dispatcher-2"
    assert failure["current_attempts"] == 2
    assert failure["max_attempts"] == 5
    assert failure["retry_delay_seconds"] == 9
    assert "rabbit down" in failure["error"]


@pytest.mark.asyncio
async def test_dispatcher_idles_without_rows() -> None:
    store = InMemoryDispatchStore([])
    bus = RecordingEventBus()
    dispatcher = EventDispatcher(store=store, event_bus=bus)

    sent = await dispatcher.send_once()

    assert sent == 0
    assert bus.published == []
    assert store.sent == []
    assert store.failed == []


def test_dispatcher_uses_existing_event_store() -> None:
    source = open("src/api/infrastructure/orchestration/store.py", encoding="utf-8").read()
    dispatcher_source = open("src/api/infrastructure/events/dispatcher.py", encoding="utf-8").read()
    bus_source = open("src/api/infrastructure/events/event_bus.py", encoding="utf-8").read()

    assert "claim_dispatches" in source
    assert "mark_sent" in source
    assert "mark_failed" in source
    assert "event_dispatches.join(" in source
    assert "pg_notify" in source
    assert "record_event: bool = True" in bus_source
    assert "record_event=False" in dispatcher_source
    assert "routing_key=record.routing_key" in dispatcher_source
