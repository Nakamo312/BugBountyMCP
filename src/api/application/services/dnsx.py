"""DNSx Scan Service - Streaming results"""
import logging
from typing import AsyncIterator
from uuid import UUID

from api.application.services.batch_processor import DNSxBatchProcessor
from api.infrastructure.runners.dnsx_cli import DNSxCliRunner

logger = logging.getLogger(__name__)


class DNSxScanService:
    """
    Service for DNSx scans.
    Streams batched results for pipeline node processing.
    Supports three modes: basic (A/AAAA/CNAME), deep (all records), ptr (reverse DNS).
    """

    def __init__(self, runner: DNSxCliRunner, processor: DNSxBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(
        self, program_id: UUID, targets: list[str], mode: str = "basic"
    ) -> AsyncIterator[list[dict]]:
        """
        Execute DNSx scan and yield batched results.

        Args:
            program_id: Program identifier
            targets: List of domains/hosts (for basic/deep) or IPs (for ptr) to scan
            mode: Scan mode - 'basic', 'deep', or 'ptr'

        Yields:
            Batches of DNS results
        """
        logger.info(f"Starting DNSx {mode} scan: program={program_id} targets={len(targets)}")

        batches_yielded = 0
        results_count = 0

        try:
            if mode == "basic":
                stream = self.runner.run_basic(targets)
            elif mode == "ptr":
                stream = self.runner.run_ptr(targets)
            else:
                stream = self.runner.run_deep(targets)

            async for batch in self.processor.batch_stream(stream):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"DNSx {mode} batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"DNSx {mode} scan completed: program={program_id} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"DNSx {mode} scan failed: program={program_id} error={e}", exc_info=True)
            raise
