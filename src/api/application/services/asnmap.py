"""ASNMap Scan Service - Streaming results"""

import logging
from typing import AsyncIterator
from uuid import UUID

from api.application.services.batch_processor import ASNMapBatchProcessor
from api.infrastructure.runners.asnmap_cli import ASNMapCliRunner

logger = logging.getLogger(__name__)


class ASNMapScanService:
    """
    Service for ASNMap scans.
    Streams batched results for pipeline node processing.
    Supports three modes: domain, asn, organization.
    """

    def __init__(self, runner: ASNMapCliRunner, processor: ASNMapBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(
        self,
        program_id: UUID,
        targets: list[str],
        mode: str = "domain"
    ) -> AsyncIterator[list[dict]]:
        """
        Execute ASNMap scan and yield batched results.

        Args:
            program_id: Program identifier
            targets: List of targets (domains, ASNs, or organization names)
            mode: Scan mode - 'domain', 'asn', or 'organization'

        Yields:
            Batches of ASNMap results
        """
        logger.info(f"Starting ASNMap {mode} scan: program={program_id} targets={len(targets)}")

        batches_yielded = 0
        results_count = 0

        try:
            if mode == "domain":
                stream = self.runner.run_domain(targets)
            elif mode == "asn":
                stream = self.runner.run_asn(targets)
            elif mode == "organization":
                stream = self.runner.run_organization(targets)
            else:
                raise ValueError(f"Invalid ASNMap mode: {mode}. Must be 'domain', 'asn', or 'organization'")

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"ASNMap {mode} batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"ASNMap {mode} scan completed: program={program_id} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"ASNMap {mode} scan failed: program={program_id} error={e}", exc_info=True)
            raise
