"""Subjack scan service for subdomain takeover detection"""
import logging
from typing import AsyncIterator
from uuid import UUID

from api.infrastructure.runners.subjack_cli import SubjackCliRunner
from api.application.services.batch_processor import BaseBatchProcessor

logger = logging.getLogger(__name__)


class SubjackScanService:
    """
    Service for Subjack subdomain takeover detection.
    Returns batched results via async generator.
    """

    def __init__(self, runner: SubjackCliRunner, processor: BaseBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(
        self,
        program_id: UUID,
        targets: list[str] | str,
    ) -> AsyncIterator[list[dict]]:
        """
        Execute Subjack subdomain takeover scan.

        Args:
            program_id: Target program ID
            targets: Single domain or list of domains to scan

        Yields:
            Batches of vulnerability results
        """
        if isinstance(targets, str):
            targets = [targets]

        logger.info(f"Starting Subjack scan: program={program_id} targets={len(targets)}")

        results_count = 0
        batches_yielded = 0

        async for batch in self.processor.batch_stream(self.runner.run(targets)):
            if batch:
                batches_yielded += 1
                results_count += len(batch)
                yield batch

        logger.info(
            f"Subjack scan completed: program={program_id} targets={len(targets)} "
            f"vulnerabilities={results_count} batches={batches_yielded}"
        )
