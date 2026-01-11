# infrastructure/event_bus.py
import json
import logging
from typing import Any, Callable, Coroutine, Dict, Set
import aio_pika
from api.config import Settings
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

    def __init__(self, settings: Settings, connection: aio_pika.RobustConnection | None = None, channel: aio_pika.Channel | None = None):
        self.settings = settings
        self.connection = connection
        self.channel = channel
        self.exchange = None
        self._declared_queues: Set[str] = set()

    async def connect(self):
        """Establish connection, channel, and topic exchange"""
        if not self.connection:
            rabbit_url = self.settings.rabbitmq_url
            self.connection = await aio_pika.connect_robust(rabbit_url)
        if not self.channel:
            self.channel = await self.connection.channel()
        if not self.exchange:
            self.exchange = await self.channel.declare_exchange(
                QueueConfig.EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            logger.info(f"Declared topic exchange: {QueueConfig.EXCHANGE_NAME}")

    async def _ensure_queue(self, queue_name: str, binding_pattern: str):
        """
        Declare queue and bind to exchange with pattern.

        Args:
            queue_name: Queue name
            binding_pattern: Topic pattern (e.g., "discovery.#")
        """
        if queue_name not in self._declared_queues:
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={"x-max-priority": 10}
            )
            await queue.bind(self.exchange, routing_key=binding_pattern)
            self._declared_queues.add(queue_name)
            logger.info(f"Declared queue: {queue_name} bound to {binding_pattern}")

    async def publish(self, event: Dict[str, Any]):
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
        """
        if not self.channel or not self.exchange:
            raise RuntimeError("EventBus not connected")

        event_name = event.get("event")
        if not event_name:
            raise ValueError("Event missing 'event' field")

        routing_key = QueueConfig.get_routing_key(event_name)
        confidence = event.get("confidence", 0.5)
        priority = QueueConfig.confidence_to_priority(confidence)

        await self.exchange.publish(
            aio_pika.Message(
                body=json.dumps(event).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                priority=priority
            ),
            routing_key=routing_key
        )

        logger.debug(
            f"Published event: {event_name} "
            f"(routing_key={routing_key}, priority={priority})"
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

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    event = json.loads(message.body.decode())
                    await callback(event)
