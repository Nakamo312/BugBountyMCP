import logging
from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

from api.infrastructure.unit_of_work.interfaces.mantra import MantraUnitOfWork
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class MantraResultIngestor:
    """
    Handles ingestion of Mantra secret scanning results.
    Finds endpoint_id by URL and stores secrets in leaks table.
    """

    def __init__(self, uow: MantraUnitOfWork):
        self.uow = uow

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest Mantra results batch.

        Args:
            program_id: Target program ID
            results: List of dicts with 'url' and 'secret' keys

        Returns:
            IngestResult (empty - secrets stored in DB)
        """
        async with self.uow:
            try:
                ingested = 0
                skipped = 0

                for result in results:
                    url = result.get("url")
                    secret = result.get("secret")

                    if not url or not secret:
                        skipped += 1
                        continue

                    endpoint_id = await self._find_endpoint_by_url(program_id, url)

                    await self.uow.leaks.ensure(
                        program_id=program_id,
                        content=secret,
                        endpoint_id=endpoint_id,
                    )
                    ingested += 1

                await self.uow.commit()

                logger.info(
                    f"Mantra ingestion completed: program={program_id} "
                    f"ingested={ingested} skipped={skipped}"
                )

                return IngestResult()

            except Exception as e:
                logger.error(f"Mantra ingestion failed: program={program_id} error={e}")
                await self.uow.rollback()
                raise

    async def _find_endpoint_by_url(self, program_id: UUID, url: str) -> UUID | None:
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

            host = await self.uow.hosts.get_by_fields(program_id=program_id, host=host_name)
            if not host:
                logger.debug(f"Host not found: {host_name}")
                return None

            endpoint = await self.uow.endpoints.get_by_fields(host_id=host.id, path=path)
            if not endpoint:
                logger.debug(f"Endpoint not found: host={host_name} path={path}")
                return None

            return endpoint.id

        except Exception as e:
            logger.warning(f"Error finding endpoint for {url}: {e}")
            return None
