import logging
from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

from api.infrastructure.unit_of_work.interfaces.mantra import MantraUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class MantraResultIngestor(BaseResultIngestor):
    """
    Handles ingestion of Mantra secret scanning results.
    Finds endpoint_id by URL and stores secrets in leaks table.
    """

    def __init__(self, uow: MantraUnitOfWork):
        super().__init__(uow, batch_size=50)
        self._ingested = 0
        self._skipped = 0

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest Mantra results batch.

        Args:
            program_id: Target program ID
            results: List of dicts with 'url' and 'secret' keys

        Returns:
            IngestResult (empty - secrets stored in DB)
        """
        self._ingested = 0
        self._skipped = 0

        await super().ingest(program_id, results)

        logger.info(
            f"Mantra ingestion completed: program={program_id} "
            f"ingested={self._ingested} skipped={self._skipped}"
        )

        return IngestResult()

    async def _process_batch(self, uow: MantraUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a batch of Mantra results"""
        for result in batch:
            url = result.get("url")
            secret = result.get("secret")

            if not url or not secret:
                self._skipped += 1
                continue

            endpoint_id = await self._find_endpoint_by_url(uow, program_id, url)

            await uow.leaks.ensure(
                program_id=program_id,
                content=secret,
                endpoint_id=endpoint_id,
            )
            self._ingested += 1

    async def _find_endpoint_by_url(self, uow, program_id: UUID, url: str) -> UUID | None:
        """
        Find endpoint ID by URL.

        Args:
            program_id: Target program ID
            url: Full URL of JS file

        Returns:
            endpoint_id or None if not found
        """
        try:
            parsed = urlparse(url)
            host_name = parsed.hostname

            if not host_name:
                return None

            path = parsed.path or "/"
            if "?" in path:
                path = path.split("?")[0]

            host = await uow.hosts.get_by_fields(program_id=program_id, host=host_name)
            if not host:
                logger.debug(f"Host not found: {host_name}")
                return None

            endpoint = await uow.endpoints.get_by_fields(host_id=host.id, path=path)
            if not endpoint:
                logger.debug(f"Endpoint not found: host={host_name} path={path}")
                return None

            return endpoint.id

        except Exception as e:
            logger.warning(f"Error finding endpoint for {url}: {e}")
            return None
