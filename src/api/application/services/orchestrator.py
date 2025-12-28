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
        max_concurrent_scans: int = 3,
    ):
        self.bus = bus
        self.container = container
        self.tasks: set[asyncio.Task] = set()
        self._scan_semaphore = asyncio.Semaphore(max_concurrent_scans)

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
        asyncio.create_task(
            self.bus.subscribe("gau_discovered", self.handle_gau_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe("katana_discovered", self.handle_katana_discovered)
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
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        targets = event["subdomains"]

        logger.info(f"Received subdomain batch for program {program_id}: {len(targets)} targets")

        task = asyncio.create_task(self._process_subdomain_batch(program_id, targets))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_subdomain_batch(self, program_id: str, targets: list[str]):
        """
        Process subdomain batch with semaphore to limit concurrent scans.
        """
        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                logger.info(f"Starting HTTPX scan for program {program_id}: {len(targets)} targets")

                await httpx_service.execute(program_id=program_id, targets=targets)

    async def handle_gau_discovered(self, event: Dict[str, Any]):
        """
        Handle GAU URL discovery events by triggering HTTPX scans for the batch.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        urls = event["urls"]

        logger.info(f"Received GAU URL batch for program {program_id}: {len(urls)} URLs")

        task = asyncio.create_task(self._process_gau_batch(program_id, urls))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_gau_batch(self, program_id: str, urls: list[str]):
        """
        Process GAU URL batch with semaphore to limit concurrent scans.
        """
        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                logger.info(f"Starting HTTPX scan for GAU batch: program={program_id} urls={len(urls)}")

                await httpx_service.execute(program_id=program_id, targets=urls)

    async def handle_katana_discovered(self, event: Dict[str, Any]):
        """
        Handle Katana URL discovery events by triggering HTTPX scans for the batch.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        urls = event["urls"]

        logger.info(f"Received Katana URL batch for program {program_id}: {len(urls)} URLs")

        task = asyncio.create_task(self._process_katana_batch(program_id, urls))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_katana_batch(self, program_id: str, urls: list[str]):
        """
        Process Katana URL batch with semaphore to limit concurrent scans.
        """
        async with self._scan_semaphore:
            async with self.container() as request_container:
                httpx_service = await request_container.get(HTTPXScanService)

                logger.info(f"Starting HTTPX scan for Katana batch: program={program_id} urls={len(urls)}")

                await httpx_service.execute(program_id=program_id, targets=urls)
