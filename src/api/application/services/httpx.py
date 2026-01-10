"""HTTPX Scan Service - Streaming results"""
import logging
from typing import AsyncIterator, Dict, Any
from uuid import UUID

from api.application.services.batch_processor import HTTPXBatchProcessor
from api.infrastructure.runners.httpx_cli import HTTPXCliRunner

logger = logging.getLogger(__name__)


class HTTPXScanService:
    """
    Service for HTTPX scans.
    Streams batched results for pipeline node processing.
    """

    def __init__(self, runner: HTTPXCliRunner, processor: HTTPXBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(self, program_id: UUID, targets: list[str]) -> AsyncIterator[list[Dict[str, Any]]]:
        """
        Execute HTTPX scan and yield batched results.

        Args:
            program_id: Program identifier
            targets: List of URLs or hosts to scan

        Yields:
            Batches of HTTPX results
        """
        logger.info(f"Starting HTTPX scan: program={program_id} targets={len(targets)}")

        batches_yielded = 0
        results_count = 0

        try:
            async for batch in self.processor.batch_stream(self.runner.run(targets)):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"HTTPX batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"HTTPX scan completed: program={program_id} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"HTTPX scan failed: program={program_id} error={e}", exc_info=True)
            raise
