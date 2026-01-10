import logging
from typing import List, AsyncIterator
from uuid import UUID

from api.infrastructure.runners.linkfinder_cli import LinkFinderCliRunner

logger = logging.getLogger(__name__)


class LinkFinderScanService:
    """
    Service for LinkFinder JS analysis.
    Extracts endpoints from JavaScript files.
    """

    def __init__(self, runner: LinkFinderCliRunner):
        self.runner = runner

    async def execute(self, program_id: UUID, targets: List[str]) -> AsyncIterator[List[str]]:
        """
        Execute LinkFinder scan on JS files.

        Args:
            program_id: Target program ID
            targets: List of JS URLs to analyze

        Yields:
            Lists of discovered URLs
        """
        logger.info(f"Starting LinkFinder scan: program={program_id} targets={len(targets)}")

        all_urls = []

        async for result in self.runner.run(targets):
            if result.type == "result" and result.payload:
                urls = result.payload.get("urls", [])
                all_urls.extend(urls)
                logger.debug(
                    f"LinkFinder found URLs: source={result.payload.get('source_js')} count={len(urls)}"
                )

        if all_urls:
            logger.info(
                f"LinkFinder scan completed: program={program_id} targets={len(targets)} "
                f"urls_found={len(all_urls)}"
            )
            yield all_urls
        else:
            logger.info(
                f"LinkFinder scan completed: program={program_id} targets={len(targets)} "
                f"urls_found=0"
            )
