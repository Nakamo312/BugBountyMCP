# infrastructure/event_bus.py
import json
from typing import Any, Callable, Coroutine, Dict
import aio_pika
from api.config import Settings

class EventBus:
    """
    Async EventBus using RabbitMQ.
    Connection и Channel могут быть переданы извне или созданы внутри.
    """
    def __init__(self, settings: Settings, connection: aio_pika.RobustConnection | None = None, channel: aio_pika.Channel | None = None):
        self.settings = settings
        self.connection = connection
        self.channel = channel

    async def connect(self):
        if not self.connection:
            rabbit_url = self.settings.rabbitmq_url
            self.connection = await aio_pika.connect_robust(rabbit_url)
        if not self.channel:
            self.channel = await self.connection.channel()
            await self.channel.declare_queue("scan_results", durable=True)
            await self.channel.declare_queue("service_events", durable=True)

    async def publish(self, queue_name: str, message: Dict[str, Any]):
        if not self.channel:
            raise RuntimeError("EventBus not connected")
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
        if not self.channel:
            raise RuntimeError("EventBus not connected")
        queue = await self.channel.declare_queue(queue_name, durable=True)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    data = json.loads(message.body.decode())
                    await callback(data)
