from __future__ import annotations

from typing import get_type_hints

from api.application.event_contracts import EventEnvelope
from api.application.ports.events import EventBusPort


def test_event_bus_port_publish_accepts_only_typed_event_envelope() -> None:
    hints = get_type_hints(EventBusPort.publish)

    assert hints["event"] is EventEnvelope
