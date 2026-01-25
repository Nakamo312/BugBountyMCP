import logging
from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork
from api.infrastructure.normalization.path_normalizer import PathNormalizer
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class FFUFResultIngestor(BaseResultIngestor):
    """
    Handles ingestion of FFUF fuzzing results.
    Parses URLs and stores discovered endpoints in database.
    """

    def __init__(self, uow: HTTPXUnitOfWork):
        super().__init__(uow, batch_size=50)
        self._ingested = 0
        self._skipped = 0

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest FFUF results batch.

        Args:
            program_id: Target program ID
            results: List of dicts with url, status, length, etc.
        """
        self._ingested = 0
        self._skipped = 0

        await super().ingest(program_id, results)

        logger.info(
            f"FFUF ingestion completed: program={program_id} "
            f"ingested={self._ingested} skipped={self._skipped}"
        )

        return IngestResult()

    async def _process_batch(self, uow: HTTPXUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a batch of FFUF results"""
        for result in batch:
            url = result.get("url")
            if not url:
                self._skipped += 1
                continue

            try:
                parsed = urlparse(url)
                if not parsed.hostname:
                    self._skipped += 1
                    continue

                host_name = parsed.hostname
                scheme = parsed.scheme or "https"
                port = parsed.port or (443 if scheme == "https" else 80)
                path = parsed.path or "/"
                status_code = result.get("status", 0)

                host = await uow.hosts.get_by_fields(
                    program_id=program_id,
                    host=host_name
                )

                if not host:
                    self._skipped += 1
                    continue

                host_ip_records = await uow.host_ips.find_many(
                    filters={"host_id": host.id},
                    limit=1
                )
                if not host_ip_records:
                    self._skipped += 1
                    continue

                ip = await uow.ips.get(host_ip_records[0].ip_id)
                if not ip:
                    self._skipped += 1
                    continue

                service = await uow.services.get_by_fields(
                    ip_id=ip.id,
                    port=port,
                    scheme=scheme
                )

                if not service:
                    self._skipped += 1
                    continue

                normalized_path = PathNormalizer.normalize_path(url)

                await uow.endpoints.ensure(
                    host_id=host.id,
                    service_id=service.id,
                    path=path,
                    normalized_path=normalized_path,
                    method="GET",
                    status_code=status_code,
                )

                self._ingested += 1

            except Exception as e:
                logger.warning(f"Failed to ingest FFUF result {url}: {e}")
                self._skipped += 1
                continue
