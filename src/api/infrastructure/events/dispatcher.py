"""Durable event dispatch loop for stored event deliveries."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from api.application.contracts import EventDispatchRecord

logger = logging.getLogger(__name__)


class EventDispatcher:
    """Dispatch pending stored events to an external destination.

    The dispatcher never creates new domain events. It claims rows from the
    durable dispatch table, publishes the stored envelope to the destination,
    and updates the dispatch row with delivery state.
    """

    def __init__(
        self,
        *,
        store: Any,
        event_bus: Any,
        destination: str = "rabbitmq",
        dispatcher_id: str | None = None,
        batch_size: int = 100,
        lease_ttl_seconds: int = 30,
        max_attempts: int = 10,
        retry_delay_seconds: float = 5.0,
        sweep_interval_seconds: float = 5.0,
        notify_channel: str = "event_dispatches_changed",
        listen_dsn: str | None = None,
    ) -> None:
        self.store = store
        self.event_bus = event_bus
        self.destination = destination
        self.dispatcher_id = dispatcher_id or f"event-dispatcher-{uuid.uuid4()}"
        self.batch_size = max(1, int(batch_size))
        self.lease_ttl_seconds = max(1, int(lease_ttl_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_delay_seconds = max(0.1, float(retry_delay_seconds))
        self.sweep_interval_seconds = max(0.1, float(sweep_interval_seconds))
        self.notify_channel = notify_channel
        self.listen_dsn = listen_dsn
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._run_task: asyncio.Task | None = None
        self._listen_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._run_task is not None and not self._run_task.done():
            return
        self._stop_event.clear()
        self._run_task = asyncio.create_task(self.run(), name="event-dispatcher")

    async def stop(self) -> None:
        self._stop_event.set()
        self.wake()
        tasks = [task for task in (self._run_task, self._listen_task) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._run_task = None
        self._listen_task = None

    def wake(self) -> None:
        self._wake_event.set()

    async def run(self) -> None:
        await self.drain_pending()
        if self.listen_dsn:
            self._listen_task = asyncio.create_task(
                self._listen_for_notifications(),
                name="event-dispatcher-listener",
            )
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=self.sweep_interval_seconds)
            except TimeoutError:
                pass
            self._wake_event.clear()
            await self.drain_pending()

    async def drain_pending(self) -> int:
        total = 0
        while not self._stop_event.is_set():
            sent = await self.send_once()
            if sent == 0:
                break
            total += sent
        return total

    async def send_once(self) -> int:
        records: list[EventDispatchRecord] = await self.store.claim_dispatches(
            destination=self.destination,
            dispatcher_id=self.dispatcher_id,
            batch_size=self.batch_size,
            lease_ttl_seconds=self.lease_ttl_seconds,
        )
        if not records:
            return 0

        for record in records:
            await self._send_record(record)
        return len(records)

    async def _send_record(self, record: EventDispatchRecord) -> None:
        try:
            await self.event_bus.publish(
                record.envelope,
                record_event=False,
                routing_key=record.routing_key,
            )
        except Exception as exc:  # pragma: no cover - exercised by unit tests through stubs
            logger.warning(
                "Event send failed: dispatch_id=%s event_id=%s destination=%s attempts=%s error=%s",
                record.dispatch_id,
                record.event_id,
                record.destination,
                record.attempts + 1,
                exc,
            )
            await self.store.mark_failed(
                dispatch_id=record.dispatch_id,
                dispatcher_id=self.dispatcher_id,
                error=str(exc),
                current_attempts=record.attempts,
                max_attempts=self.max_attempts,
                retry_delay_seconds=self.retry_delay_seconds,
            )
            return

        await self.store.mark_sent(
            dispatch_id=record.dispatch_id,
            dispatcher_id=self.dispatcher_id,
        )

    async def _listen_for_notifications(self) -> None:
        """Wake the dispatcher on PostgreSQL NOTIFY; periodic sweep is the fallback."""
        try:
            import asyncpg
        except ImportError:  # pragma: no cover - asyncpg is a runtime dependency
            logger.warning("asyncpg not installed; EventDispatcher will use periodic sweep only")
            return

        connection = None
        try:
            connection = await asyncpg.connect(self.listen_dsn)
            loop = asyncio.get_running_loop()

            def _on_notify(*_: Any) -> None:
                loop.call_soon_threadsafe(self.wake)

            await connection.add_listener(self.notify_channel, _on_notify)
            while not self._stop_event.is_set():
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - depends on live PostgreSQL
            logger.warning("Event dispatch notification listener stopped: %s", exc)
        finally:
            if connection is not None:
                await connection.close()
