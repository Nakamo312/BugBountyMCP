"""TLSx Scan Service - Event-driven architecture"""

import logging
from uuid import UUID

from api.application.dto import TLSxScanOutputDTO
from api.application.services.batch_processor import TLSxBatchProcessor
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.runners.tlsx_cli import TLSxCliRunner

logger = logging.getLogger(__name__)


class TLSxScanService:
    """
    Event-driven service for TLSx scans.
    Batches results before publishing to EventBus for better performance.
    Supports two modes: default (cert scanning) and sni_brute.
    """

    def __init__(self, runner: TLSxCliRunner, processor: TLSxBatchProcessor, bus: EventBus):
        self.runner = runner
        self.processor = processor
        self.bus = bus

    async def execute_default(
        self,
        program_id: UUID,
        targets: list[str],
        ports: list[int] | None = None
    ) -> TLSxScanOutputDTO:
        """
        Execute TLSx default certificate scan and publish results.
        Blocks until scan completes to properly hold orchestrator semaphore.

        Args:
            program_id: Program identifier
            targets: List of targets (IPs, domains, IP:PORT)
            ports: List of ports to scan (default: 443, 8443)

        Returns:
            Response after scan has completed
        """
        logger.info(f"Starting TLSx default scan: program={program_id} targets={len(targets)}")

        await self._run_default_scan(program_id, targets, ports)

        return TLSxScanOutputDTO(
            status="completed",
            message=f"TLSx default scan completed for {len(targets)} targets",
            scanner="tlsx",
            mode="default",
            targets_count=len(targets)
        )

    async def execute_sni_brute(
        self,
        program_id: UUID,
        ips: list[str],
        domains: list[str],
        ports: list[int] | None = None
    ) -> TLSxScanOutputDTO:
        """
        Execute TLSx SNI brute-force scan and publish results.
        Tests known domains against IPs to discover virtual hosts.

        Args:
            program_id: Program identifier
            ips: List of IP addresses to probe
            domains: List of domain names to use as SNI values
            ports: List of ports to scan (default: 443, 8443)

        Returns:
            Response after scan has completed
        """
        logger.info(
            f"Starting TLSx SNI brute: program={program_id} "
            f"ips={len(ips)} domains={len(domains)}"
        )

        await self._run_sni_brute_scan(program_id, ips, domains, ports)

        return TLSxScanOutputDTO(
            status="completed",
            message=f"TLSx SNI brute completed for {len(ips)} IPs with {len(domains)} domains",
            scanner="tlsx",
            mode="sni_brute",
            targets_count=len(ips)
        )

    async def _run_default_scan(
        self,
        program_id: UUID,
        targets: list[str],
        ports: list[int] | None
    ):
        """Run the default certificate scan with result batching"""
        results_count = 0
        batches_published = 0

        try:
            stream = self.runner.scan_default_certs(targets, ports)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"TLSx default scan completed: program={program_id} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"TLSx default scan failed: program={program_id} error={e}", exc_info=True)
            raise

    async def _run_sni_brute_scan(
        self,
        program_id: UUID,
        ips: list[str],
        domains: list[str],
        ports: list[int] | None
    ):
        """Run the SNI brute-force scan with result batching"""
        results_count = 0
        batches_published = 0

        try:
            stream = self.runner.scan_sni_brute(ips, domains, ports)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    await self._publish_batch(program_id, batch)
                    batches_published += 1
                    results_count += len(batch)

            logger.info(
                f"TLSx SNI brute completed: program={program_id} "
                f"results={results_count} batches={batches_published}"
            )
        except Exception as e:
            logger.error(f"TLSx SNI brute failed: program={program_id} error={e}", exc_info=True)
            raise

    async def _publish_batch(self, program_id: UUID, results: list[dict]):
        """Publish batch of results to EventBus"""
        await self.bus.publish(
            EventType.TLSX_RESULTS_BATCH,
            {
                "program_id": str(program_id),
                "results": results,
            },
        )
        logger.debug(f"Published TLSx results batch: program={program_id} count={len(results)}")
