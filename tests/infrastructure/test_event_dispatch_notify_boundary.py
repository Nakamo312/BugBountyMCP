from uuid import uuid4

import pytest

pytest.importorskip("sqlalchemy")

from api.application.contracts import EventEnvelope
from api.config import Settings
from api.infrastructure.orchestration.dispatch_store import DispatchStore


class RecordingAsyncSession:
    def __init__(self) -> None:
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_event_dispatch_notify_uses_configured_channel_and_core_statement() -> None:
    settings = Settings(EVENT_DISPATCH_NOTIFY_CHANNEL="custom_dispatch_channel")
    store = DispatchStore(lambda: None, settings=settings)
    session = RecordingAsyncSession()
    envelope = EventEnvelope(
        event="httpx_scan_requested",
        program_id=uuid4(),
        targets=["https://example.com"],
    )

    await store.enqueue_dispatch(session, envelope)

    assert len(session.statements) == 2
    notify_statement = session.statements[1]
    compiled = notify_statement.compile()

    assert "pg_notify" in str(notify_statement)
    assert "SELECT pg_notify" in str(notify_statement)
    assert "text(" not in type(notify_statement).__name__.lower()
    assert set(compiled.params.values()) == {
        "custom_dispatch_channel",
        str(envelope.event_id),
    }
