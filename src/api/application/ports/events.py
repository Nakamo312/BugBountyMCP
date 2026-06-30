from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from api.application.event_contracts import EventEnvelope

EventPayload = dict[str, Any]
EventCallback = Callable[[EventPayload], Awaitable[None]]


class EventBusPort(Protocol):
    """Application-facing event bus contract.

    Concrete transport adapters may use RabbitMQ, in-memory dispatch, replay, or
    another event backend. Pipeline application code must publish typed envelopes
    through this port, not legacy event dictionaries or infrastructure buses.
    """

    @property
    def requires_bound_job_id_for_recording(self) -> bool:
        """Whether publishing records durable events and therefore needs job_id."""
        ...

    async def connect(self) -> None:
        """Connect the underlying transport, if needed."""
        ...

    async def publish(
        self,
        event: EventEnvelope,
        *,
        record_event: bool = True,
        routing_key: str | None = None,
    ) -> None:
        """Publish a typed application event envelope through the transport."""
        ...

    async def subscribe(
        self,
        queue_name: str,
        callback: EventCallback,
    ) -> None:
        """Subscribe a callback to a concrete queue name supplied by wiring."""
        ...
