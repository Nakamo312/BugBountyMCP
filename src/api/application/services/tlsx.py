"""TLSx Scan Service - Streaming results"""

import logging
from typing import AsyncIterator
from uuid import UUID

from api.application.services.batch_processor import TLSxBatchProcessor
from api.infrastructure.runners.tlsx_cli import TLSxCliRunner

logger = logging.getLogger(__name__)


class TLSxScanService:
    """
    Service for TLSx scans.
    Streams batched results for pipeline node processing.
    Supports two modes: default (cert scanning) and sni_brute.
    """

    def __init__(self, runner: TLSxCliRunner, processor: TLSxBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute_default(
        self,
        program_id: UUID,
        targets: list[str],
        ports: list[int] | None = None
    ) -> AsyncIterator[list[dict]]:
        """
        Execute TLSx default certificate scan and yield batched results.

        Args:
            program_id: Program identifier
            targets: List of targets (IPs, domains, IP:PORT)
            ports: List of ports to scan (default: 443, 8443)

        Yields:
            Batches of TLSx certificate results
        """
        logger.info(f"Starting TLSx default scan: program={program_id} targets={len(targets)}")

        batches_yielded = 0
        results_count = 0

        try:
            stream = self.runner.scan_default_certs(targets, ports)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"TLSx default batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"TLSx default scan completed: program={program_id} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"TLSx default scan failed: program={program_id} error={e}", exc_info=True)
            raise

    async def execute_sni_brute(
        self,
        program_id: UUID,
        ips: list[str],
        domains: list[str],
        ports: list[int] | None = None
    ) -> AsyncIterator[list[dict]]:
        """
        Execute TLSx SNI brute-force scan and yield batched results.
        Tests known domains against IPs to discover virtual hosts.

        Args:
            program_id: Program identifier
            ips: List of IP addresses to probe
            domains: List of domain names to use as SNI values
            ports: List of ports to scan (default: 443, 8443)

        Yields:
            Batches of TLSx SNI brute results
        """
        logger.info(
            f"Starting TLSx SNI brute: program={program_id} "
            f"ips={len(ips)} domains={len(domains)}"
        )

        batches_yielded = 0
        results_count = 0

        try:
            stream = self.runner.scan_sni_brute(ips, domains, ports)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"TLSx SNI batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"TLSx SNI brute completed: program={program_id} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"TLSx SNI brute failed: program={program_id} error={e}", exc_info=True)
            raise
