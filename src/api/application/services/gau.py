"""GAU scan service for URL enumeration"""
import logging
from typing import AsyncIterator
from uuid import UUID

from api.infrastructure.runners.gau_cli import GAUCliRunner
from api.application.services.batch_processor import GAUBatchProcessor

logger = logging.getLogger(__name__)


class GAUScanService:
    """
    Service for GAU (GetAllURLs) scanning.
    Streams batched URLs for pipeline node processing.
    """

    def __init__(self, runner: GAUCliRunner, processor: GAUBatchProcessor):
        self.runner = runner
        self.processor = processor

    async def execute(
        self, program_id: UUID, domain: str, include_subs: bool = True
    ) -> AsyncIterator[list[str]]:
        """
        Execute GAU scan and yield URL batches.

        Args:
            program_id: Target program ID
            domain: Domain to scan
            include_subs: Include subdomains in results

        Yields:
            Batches of URLs
        """
        logger.info(f"Starting GAU scan: program={program_id} domain={domain} include_subs={include_subs}")

        batches_yielded = 0
        urls_found = 0

        try:
            async for batch in self.processor.batch_stream(self.runner.run(domain, include_subs)):
                if batch:
                    batches_yielded += 1
                    urls_found += len(batch)
                    logger.debug(f"GAU batch ready: program={program_id} count={len(batch)}")
                    yield batch

            logger.info(
                f"GAU scan completed: program={program_id} domain={domain} "
                f"urls={urls_found} batches={batches_yielded}"
            )
        except Exception as e:
            logger.error(f"GAU scan failed: program={program_id} domain={domain} error={e}")
            raise
