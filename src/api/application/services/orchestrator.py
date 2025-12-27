from typing import Dict, Any
import asyncio
import logging
from dishka.integrations.fastapi import FromDishka
from src.api.infrastructure.events.event_bus import EventBus
from api.application.services.httpx import HTTPXScanService
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    Orchestrates scan services and ingestors.
    Uses DI injection for services and ingestors via Dishka.
    """
    def __init__(
        self,
        bus: FromDishka[EventBus],
        httpx_service: FromDishka[HTTPXScanService],
        httpx_ingestor: FromDishka[HTTPXResultIngestor]
    ):
        self.bus = bus
        self.httpx_service = httpx_service
        self.httpx_ingestor = httpx_ingestor
        self.tasks: set[asyncio.Task] = set()

    async def start(self):
        await self.bus.connect()
        asyncio.create_task(self.bus.subscribe("service_events", self.handle_service_event))
        asyncio.create_task(self.bus.subscribe("scan_results", self.handle_scan_result))

    async def handle_service_event(self, event: Dict[str, Any]):
        """
        Executes scan services using injected HTTPXScanService.
        """
        service_name = event.get("service")
        if service_name != "httpx":
            logger.warning("Unsupported service: %s", service_name)
            return

        action = event.get("action", "execute")
        kwargs = {k: v for k, v in event.items() if k not in ("service", "action")}

        async def run_service():
            method = getattr(self.httpx_service, action)
            await method(**kwargs)

        task = asyncio.create_task(run_service())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def handle_scan_result(self, event: Dict[str, Any]):
        """
        Executes HTTPXResultIngestor using injected DI dependency.
        """
        program_id = event["program_id"]
        result = event["result"]

        async def run_ingest():
            await self.httpx_ingestor.ingest(program_id, [result])

        task = asyncio.create_task(run_ingest())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
