# infrastructure/event_bus.py
import json
import logging
from typing import Any, Callable, Coroutine, Dict, Set
import aio_pika
from api.config import Settings

logger = logging.getLogger(__name__)


class EventBus:
    """
    Async EventBus using RabbitMQ.
    Automatically declares queues on first use.
    """

    def __init__(self, settings: Settings, connection: aio_pika.RobustConnection | None = None, channel: aio_pika.Channel | None = None):
        self.settings = settings
        self.connection = connection
        self.channel = channel
        self._declared_queues: Set[str] = set()

    async def connect(self):
        """Establish connection and channel to RabbitMQ"""
        if not self.connection:
            rabbit_url = self.settings.rabbitmq_url
            self.connection = await aio_pika.connect_robust(rabbit_url)
        if not self.channel:
            self.channel = await self.connection.channel()

    async def _ensure_queue(self, queue_name: str):
        """
        Declare queue if not already declared.
        Idempotent - safe to call multiple times for same queue.
        """
        if queue_name not in self._declared_queues:
            await self.channel.declare_queue(queue_name, durable=True)
            self._declared_queues.add(queue_name)
            logger.debug(f"Declared queue: {queue_name}")

    async def publish(self, queue_name: str, message: Dict[str, Any]):
        """
        Publish message to queue.
        Automatically declares queue if needed.
        """
        if not self.channel:
            raise RuntimeError("EventBus not connected")

        await self._ensure_queue(queue_name)

        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=queue_name
        )

    async def subscribe(
        self,
        queue_name: str,
        callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
    ):
        """
        Subscribe to queue and process messages.
        Automatically declares queue if needed.
        """
        if not self.channel:
            raise RuntimeError("EventBus not connected")

        await self._ensure_queue(queue_name)
        queue = await self.channel.get_queue(queue_name)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    data = json.loads(message.body.decode())
                    await callback(data)
