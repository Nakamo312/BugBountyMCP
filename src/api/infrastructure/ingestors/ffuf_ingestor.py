import logging
from typing import List, Dict, Any
from uuid import UUID
from urllib.parse import urlparse

from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork
from api.infrastructure.normalization.path_normalizer import PathNormalizer
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class FFUFResultIngestor:
    """
    Handles ingestion of FFUF fuzzing results.
    Parses URLs and stores discovered endpoints in database.
    """

    def __init__(self, uow: HTTPXUnitOfWork):
        self.uow = uow

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest FFUF results batch.

        Args:
            program_id: Target program ID
            results: List of dicts with url, status, length, etc.
        """
        async with self.uow:
            try:
                ingested = 0
                skipped = 0

                for result in results:
                    url = result.get("url")
                    if not url:
                        skipped += 1
                        continue

                    try:
                        parsed = urlparse(url)
                        if not parsed.hostname:
                            skipped += 1
                            continue

                        host_name = parsed.hostname
                        scheme = parsed.scheme or "https"
                        port = parsed.port or (443 if scheme == "https" else 80)
                        path = parsed.path or "/"
                        status_code = result.get("status", 0)

                        host = await self.uow.hosts.get_by_fields(
                            program_id=program_id,
                            host=host_name
                        )

                        if not host:
                            skipped += 1
                            continue

                        host_ip_records = await self.uow.host_ips.find_many(
                            filters={"host_id": host.id},
                            limit=1
                        )
                        if not host_ip_records:
                            skipped += 1
                            continue

                        ip = await self.uow.ips.get(host_ip_records[0].ip_id)
                        if not ip:
                            skipped += 1
                            continue

                        service = await self.uow.services.get_by_fields(
                            ip_id=ip.id,
                            port=port,
                            scheme=scheme
                        )

                        if not service:
                            skipped += 1
                            continue

                        normalized_path = PathNormalizer.normalize_path(url)

                        await self.uow.endpoints.ensure(
                            host_id=host.id,
                            service_id=service.id,
                            path=path,
                            normalized_path=normalized_path,
                            method="GET",
                            status_code=status_code,
                        )

                        ingested += 1

                    except Exception as e:
                        logger.warning(f"Failed to ingest FFUF result {url}: {e}")
                        skipped += 1
                        continue

                await self.uow.commit()

                logger.info(
                    f"FFUF ingestion completed: program={program_id} "
                    f"ingested={ingested} skipped={skipped}"
                )

                return IngestResult()

            except Exception as e:
                logger.error(f"FFUF ingestion failed: program={program_id} error={e}")
                await self.uow.rollback()
                raise
