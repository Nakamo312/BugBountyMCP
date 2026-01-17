"""Waymore result ingestor - returns URLs for HTTPX processing"""
import logging
from typing import List
from uuid import UUID

from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class WaymoreResultIngestor:
    """
    Ingestor for waymore URLs.
    Returns URLs for HTTPX to probe (historical URLs may not be live).
    """

    async def ingest(self, program_id: UUID, results: List[str]) -> IngestResult:
        """
        Process waymore URLs and return them for HTTPX.

        Args:
            program_id: Target program ID
            results: List of URL strings from waymore batch

        Returns:
            IngestResult with urls list for HTTPX to probe
        """
        logger.info(f"Waymore URLs collected: program={program_id} count={len(results)}")

        return IngestResult(urls=results)
