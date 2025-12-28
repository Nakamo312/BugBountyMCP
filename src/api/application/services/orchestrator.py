import json
from typing import Dict, Any
import asyncio
import logging
from dishka import AsyncContainer

from api.infrastructure.events.event_bus import EventBus
from api.application.services.httpx import HTTPXScanService
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        container: AsyncContainer,
    ):
        self.bus = bus
        self.container = container
        self.tasks: set[asyncio.Task] = set()

    async def start(self):
        await self.bus.connect()
        asyncio.create_task(
            self.bus.subscribe("service_events", self.handle_service_event)
        )
        asyncio.create_task(
            self.bus.subscribe("scan_results", self.handle_scan_result)
        )
        asyncio.create_task(
            self.bus.subscribe("subdomain_discovered", self.handle_subdomain_discovered)
        )

    async def handle_service_event(self, event: Dict[str, Any]):
        async with self.container() as request_container:
            httpx_service = await request_container.get(HTTPXScanService)

            action = event.get("action", "execute")
            kwargs = {k: v for k, v in event.items() if k not in ("service", "action")}

            await getattr(httpx_service, action)(**kwargs)

    async def handle_scan_result(self, event: Dict[str, Any]):
        async with self.container() as request_container:
            ingestor = await request_container.get(HTTPXResultIngestor)
            result = event["result"]
            if isinstance(result, str):
                result = json.loads(result)

            await ingestor.ingest(event["program_id"], [result])

    async def handle_subdomain_discovered(self, event: Dict[str, Any]):
        """
        Handle subdomain discovery events by triggering HTTPX scans for the batch.
        """
        async with self.container() as request_container:
            httpx_service = await request_container.get(HTTPXScanService)

            program_id = event["program_id"]
            targets = event["subdomains"]

            logger.info(f"Processing subdomain batch for program {program_id}: {len(targets)} targets")

            await httpx_service.execute(program_id=program_id, targets=targets)
