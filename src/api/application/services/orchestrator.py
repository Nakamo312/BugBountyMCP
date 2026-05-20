"""Compatibility orchestrator for legacy integration tests."""
from __future__ import annotations

import asyncio
from uuid import UUID

from api.application.services._legacy_scan import publish_legacy_event
from api.infrastructure.events.event_types import EventType


class DNSxResultIngestor:
    """Legacy DI marker kept only for compatibility tests."""


class SubjackResultIngestor:
    """Legacy DI marker kept only for compatibility tests."""


class Orchestrator:
    def __init__(self, bus, container, settings):
        self.bus = bus
        self.container = container
        self.settings = settings
        self.tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        await self.bus.connect()
        await self.bus.subscribe(EventType.CNAME_DISCOVERED, self.handle_cname_discovered)
        await self.bus.subscribe(EventType.SUBJACK_RESULTS_BATCH, self.handle_subjack_results_batch)

    async def handle_cname_discovered(self, event: dict) -> None:
        hosts = event.get("hosts") or event.get("targets") or []
        task = asyncio.create_task(self._process_subjack_batch(event["program_id"], hosts))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _process_subjack_batch(self, program_id: str, hosts: list[str]) -> None:
        await publish_legacy_event(
            self.bus,
            EventType.SUBJACK_SCAN_REQUESTED,
            {"program_id": str(program_id), "targets": hosts, "hosts": hosts},
        )

    async def handle_subjack_results_batch(self, event: dict) -> None:
        async with self.container() as request_container:
            ingestor = await request_container.get(SubjackResultIngestor)
            await ingestor.ingest(UUID(event["program_id"]), event.get("results", []))

    async def handle_dnsx_deep_results_batch(self, event: dict) -> None:
        results = event.get("results", [])
        program_id = UUID(event["program_id"])

        async with self.container() as request_container:
            ingestor = await request_container.get(DNSxResultIngestor)
            await ingestor.ingest(program_id, results)

        cname_hosts = [
            result["host"]
            for result in results
            if result.get("host") and result.get("cname") and not result.get("wildcard", False)
        ]
        if cname_hosts:
            await publish_legacy_event(
                self.bus,
                EventType.CNAME_DISCOVERED,
                {"program_id": str(program_id), "hosts": cname_hosts, "targets": cname_hosts},
            )
