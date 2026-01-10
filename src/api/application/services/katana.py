"""Katana scan service for web crawling"""
import logging
from typing import AsyncIterator, Dict, Any
from uuid import UUID

from api.infrastructure.runners.katana_cli import KatanaCliRunner
from api.application.services.batch_processor import KatanaBatchProcessor

logger = logging.getLogger(__name__)


class KatanaScanService:
    """
    Service for Katana web crawling.
    Streams batched JSON results for pipeline node processing.
    """

    def __init__(self, runner: KatanaCliRunner, processor: KatanaBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(
        self,
        program_id: UUID,
        targets: list[str] | str,
        depth: int = 3,
        js_crawl: bool = True,
        headless: bool = False,
    ) -> AsyncIterator[list[Dict[str, Any]]]:
        """
        Execute Katana crawl and yield batched results.

        Args:
            program_id: Target program ID
            targets: Single target URL or list of target URLs to crawl
            depth: Maximum crawl depth (default: 3)
            js_crawl: Enable JavaScript crawling (default: True)
            headless: Enable headless browser mode (default: False)

        Yields:
            Batches of Katana crawl results
        """
        if isinstance(targets, str):
            targets = [targets]

        logger.info(
            f"Starting Katana scan: program={program_id} targets={len(targets)} "
            f"depth={depth} js_crawl={js_crawl} headless={headless}"
        )

        batches_yielded = 0
        results_count = 0

        try:
            async for batch in self.processor.batch_stream(self.runner.run(targets, depth, js_crawl, headless)):
                if batch:
                    batches_yielded += 1
                    results_count += len(batch)
                    logger.debug(f"Katana batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"Katana scan completed: program={program_id} targets={len(targets)} "
                f"results={results_count} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"Katana scan failed: program={program_id} targets={len(targets)} error={e}")
            raise
