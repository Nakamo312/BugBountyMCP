from __future__ import annotations

import pytest

from api.infrastructure.events.dispatcher import EventDispatcher
from api.infrastructure.events.notify_channels import validate_postgres_notify_channel
from api.infrastructure.orchestration.store import OrchestrationStore


def test_event_dispatcher_validates_notify_channel_at_boundary() -> None:
    dispatcher = EventDispatcher(
        store=object(),
        event_bus=object(),
        notify_channel="event_dispatches_changed_test",
    )

    assert dispatcher.notify_channel == "event_dispatches_changed_test"

    with pytest.raises(ValueError):
        EventDispatcher(store=object(), event_bus=object(), notify_channel="bad; LISTEN x")


def test_event_dispatch_pg_notify_statement_validates_channel() -> None:
    statement = OrchestrationStore._event_dispatch_notify_statement(
        channel="event_dispatches_changed_test",
        payload="event-id",
    )

    compiled = str(statement)
    assert "pg_notify" in compiled

    with pytest.raises(ValueError):
        OrchestrationStore._event_dispatch_notify_statement(
            channel="event_dispatches_changed;DROP",
            payload="event-id",
        )


def test_api_notify_channel_validator_contract() -> None:
    assert validate_postgres_notify_channel("graph_projection_events_changed") == "graph_projection_events_changed"
    with pytest.raises(ValueError):
        validate_postgres_notify_channel("1bad")
    with pytest.raises(ValueError):
        validate_postgres_notify_channel("x" * 64)
