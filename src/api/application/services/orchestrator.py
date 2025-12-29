from typing import Dict, Any
import asyncio
import logging
from uuid import UUID
from dishka import AsyncContainer

from api.config import Settings
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.application.services.httpx import HTTPXScanService
from api.application.services.katana import KatanaScanService
from api.infrastructure.ingestors.httpx_ingestor import HTTPXResultIngestor
from api.infrastructure.ingestors.katana_ingestor import KatanaResultIngestor

logger = logging.getLogger(__name__)

class Orchestrator:
    def __init__(
        self,
        bus: EventBus,
        container: AsyncContainer,
        settings: Settings,
    ):
        self.bus = bus
        self.container = container
        self.settings = settings
        self.tasks: set[asyncio.Task] = set()
        self._scan_semaphore = asyncio.Semaphore(settings.ORCHESTRATOR_MAX_CONCURRENT)

    async def start(self):
        await self.bus.connect()
        asyncio.create_task(
            self.bus.subscribe(EventType.SERVICE_EVENTS, self.handle_service_event)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.SCAN_RESULTS_BATCH, self.handle_scan_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.SUBDOMAIN_DISCOVERED, self.handle_subdomain_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.GAU_DISCOVERED, self.handle_gau_discovered)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.KATANA_RESULTS_BATCH, self.handle_katana_results_batch)
        )
        asyncio.create_task(
            self.bus.subscribe(EventType.HOST_DISCOVERED, self.handle_host_discovered)
        )

    async def handle_service_event(self, event: Dict[str, Any]):
        async with self.container() as request_container:
            httpx_service = await request_container.get(HTTPXScanService)

            action = event.get("action", "execute")
            kwargs = {k: v for k, v in event.items() if k not in ("service", "action")}

            await getattr(httpx_service, action)(**kwargs)

    async def handle_scan_results_batch(self, event: Dict[str, Any]):
        """Handle batched HTTPX scan results"""
        async with self.container() as request_container:
            ingestor = await request_container.get(HTTPXResultIngestor)
            program_id = UUID(event["program_id"])
            results = event["results"]

            logger.info(f"Ingesting HTTPX results batch: program={program_id} count={len(results)}")
            await ingestor.ingest(program_id, results)

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

    async def handle_katana_results_batch(self, event: Dict[str, Any]):
        """Handle batched Katana scan results"""
        async with self.container() as request_container:
            ingestor = await request_container.get(KatanaResultIngestor)
            program_id = UUID(event["program_id"])
            results = event["results"]

            logger.info(f"Ingesting Katana results batch: program={program_id} count={len(results)}")
            await ingestor.ingest(program_id, results)

    async def handle_host_discovered(self, event: Dict[str, Any]):
        """
        Handle new host discovery events by triggering Katana crawls.
        Creates background task to avoid blocking queue processing.
        """
        program_id = event["program_id"]
        hosts = event["hosts"]

        logger.info(f"Received new hosts for program {program_id}: {len(hosts)} hosts")

        task = asyncio.create_task(self._process_host_batch(program_id, hosts))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_host_batch(self, program_id: str, hosts: list[str]):
        """
        Process new host batch by launching Katana crawl with rate limiting.
        Delay prevents cascading load from newly discovered hosts.
        """
        await asyncio.sleep(self.settings.ORCHESTRATOR_SCAN_DELAY)

        async with self._scan_semaphore:
            async with self.container() as request_container:
                katana_service = await request_container.get(KatanaScanService)

                logger.info(f"Starting Katana crawl for new hosts: program={program_id} hosts={len(hosts)}")

                await katana_service.execute(program_id=program_id, targets=hosts)
