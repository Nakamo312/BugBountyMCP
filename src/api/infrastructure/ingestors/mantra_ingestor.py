import logging
from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

from api.application.contracts import IngestContext
from api.infrastructure.unit_of_work.interfaces.mantra import MantraUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor

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

    async def before_ingest(
        self,
        uow: MantraUnitOfWork,
        program_id: UUID,
        results: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._ingested = 0
        self._skipped = 0

    def log_extra(self) -> str:
        return f"ingested={self._ingested} skipped={self._skipped}"

    async def process_record(self, uow: MantraUnitOfWork, program_id: UUID, result: Dict[str, Any], context: IngestContext | None = None) -> None:
        """Process a batch of Mantra results"""
        url = result.get("url")
        secret = result.get("secret")

        if not url or not secret:
            self._skipped += 1
            return

        endpoint_id = await self._find_endpoint_by_url(uow, program_id, url)

        await uow.leaks.ensure(
            program_id=program_id,
            content=secret,
            endpoint_id=endpoint_id,
        )
        self._ingested += 1

    async def _find_endpoint_by_url(self, *args) -> UUID | None:
        """
        Find endpoint ID by URL.

        Args:
            program_id: Target program ID
            url: Full URL of JS file

        Returns:
            endpoint_id or None if not found
        """
        if len(args) == 2:
            uow = self.uow
            program_id, url = args
        elif len(args) == 3:
            uow, program_id, url = args
        else:
            raise TypeError(
                "_find_endpoint_by_url expects (program_id, url) or (uow, program_id, url)"
            )

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
