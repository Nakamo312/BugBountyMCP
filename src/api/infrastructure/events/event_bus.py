# infrastructure/event_bus.py
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Dict, Set
import aio_pika
from api.config import Settings
from api.application.contracts import EventEnvelope
from api.infrastructure.events.queue_config import QueueConfig

logger = logging.getLogger(__name__)


class EventBus:
    """
    Async EventBus using RabbitMQ with topic exchange.

    Architecture:
    - Topic exchange: "scan.events"
    - Routing key: "{queue}.{event}"
    - Priority based on confidence (0-10)
    - Queues: discovery, enumeration, validation, analysis
    """

    def __init__(
        self,
        settings: Settings,
        connection: aio_pika.RobustConnection | None = None,
        channel: aio_pika.Channel | None = None,
        event_recorder: Any | None = None,
    ):
        self.settings = settings
        self.connection = connection
        self.channel = channel
        self.exchange = None
        self.dead_letter_exchange = None
        self.event_recorder = event_recorder
        self._declared_queues: Set[str] = set()

    async def connect(self):
        """Establish connection, channel, and topic exchange"""
        if not self.connection:
            rabbit_url = self.settings.rabbitmq_url
            self.connection = await aio_pika.connect_robust(rabbit_url)
        if not self.channel:
            self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=self.settings.RABBITMQ_PREFETCH_COUNT)
        if not self.exchange:
            self.exchange = await self.channel.declare_exchange(
                QueueConfig.EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            logger.info(f"Declared topic exchange: {QueueConfig.EXCHANGE_NAME}")
        if not self.dead_letter_exchange:
            self.dead_letter_exchange = await self.channel.declare_exchange(
                QueueConfig.DEAD_LETTER_EXCHANGE_NAME,
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            logger.info(
                "Declared dead-letter exchange: %s",
                QueueConfig.DEAD_LETTER_EXCHANGE_NAME,
            )

    async def _ensure_queue(self, queue_name: str, binding_pattern: str):
        """
        Declare queue and bind to exchange with pattern.

        Args:
            queue_name: Queue name
            binding_pattern: Topic pattern (e.g., "discovery.#")
        """
        if queue_name not in self._declared_queues:
            dead_letter_queue_name = QueueConfig.get_dead_letter_queue_name(queue_name)
            dead_letter_routing_key = QueueConfig.get_dead_letter_routing_key(queue_name)
            dead_letter_queue = await self.channel.declare_queue(
                dead_letter_queue_name,
                durable=True,
            )
            await dead_letter_queue.bind(
                self.dead_letter_exchange,
                routing_key=dead_letter_routing_key,
            )
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    "x-max-priority": 10,
                    "x-dead-letter-exchange": QueueConfig.DEAD_LETTER_EXCHANGE_NAME,
                    "x-dead-letter-routing-key": dead_letter_routing_key,
                },
            )
            await queue.bind(self.exchange, routing_key=binding_pattern)
            self._declared_queues.add(queue_name)
            logger.info(f"Declared queue: {queue_name} bound to {binding_pattern}")

    async def publish(
        self,
        event: Dict[str, Any] | EventEnvelope,
        *,
        record_event: bool = True,
        routing_key: str | None = None,
    ):
        """
        Publish event to topic exchange.

        Event format:
        {
            "event": "host_discovered",
            "target": "admin.example.com",
            "source": "dnsx",
            "confidence": 0.7,
            "program_id": 42
        }

        Args:
            event: Event dictionary with required "event" field
            record_event: When false, publish only to RabbitMQ because the
                envelope has already been recorded in event_store.
            routing_key: Optional persisted routing key for event-store dispatch.
        """
        if not self.channel or not self.exchange:
            raise RuntimeError("EventBus not connected")

        envelope = event if isinstance(event, EventEnvelope) else EventEnvelope.from_legacy(event)
        event_dict = envelope.to_legacy_dict()
        event_name = envelope.event
        if not event_name:
            raise ValueError("Event missing 'event' field")

        routing_key = routing_key or QueueConfig.get_routing_key(event_name)
        confidence = envelope.confidence
        priority = QueueConfig.confidence_to_priority(confidence)

        if record_event and self.event_recorder is not None:
            await self.event_recorder.record_event(envelope)

        await self.exchange.publish(
            aio_pika.Message(
                body=json.dumps(event_dict).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority
            ),
            routing_key=routing_key
        )

        logger.info(
            f"Published event: {event_name} "
            f"(routing_key={routing_key}, priority={priority}, event_id={envelope.event_id})"
        )

    async def subscribe(
        self,
        queue_name: str,
        callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
    ):
        """
        Subscribe to queue and process messages.

        Args:
            queue_name: Queue name (discovery, enumeration, validation, analysis)
            callback: Async callback for processing messages
        """
        if not self.channel or not self.exchange:
            raise RuntimeError("EventBus not connected")

        binding_pattern = QueueConfig.get_queue_binding(queue_name)
        await self._ensure_queue(queue_name, binding_pattern)
        queue = await self.channel.get_queue(queue_name)

        logger.info(f"Subscribed to queue: {queue_name}")

        pending: Set[asyncio.Task] = set()
        try:
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    task = asyncio.create_task(
                        self._process_message(queue_name, message, callback)
                    )
                    pending.add(task)
                    task.add_done_callback(
                        lambda completed, tasks=pending: self._discard_message_task(
                            tasks,
                            completed,
                        )
                    )
        finally:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    async def _process_message(
        self,
        queue_name: str,
        message,
        callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        async with message.process():
            event = json.loads(message.body.decode())
            event_name = event.get("event")
            logger.debug("Processing RabbitMQ message: queue=%s event=%s", queue_name, event_name)
            await callback(event)

    @staticmethod
    def _discard_message_task(tasks: Set[asyncio.Task], task: asyncio.Task) -> None:
        tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "RabbitMQ message processing failed: %s",
                exc,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
