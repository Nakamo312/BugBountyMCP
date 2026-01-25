"""Naabu Result Ingestor"""

import logging
from uuid import UUID
from typing import Any, List, Dict

from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.config import Settings

logger = logging.getLogger(__name__)


class NaabuResultIngestor(BaseResultIngestor):
    """
    Ingests Naabu port scan results into database.

    Processing flow:
    1. Ensure IP address exists
    2. Create/update service record with port, protocol
    3. Batch processing with savepoint recovery

    Naabu result format:
    {
        "host": "8.8.8.8",
        "ip": "8.8.8.8",
        "port": 53,
        "protocol": "tcp"
    }
    """

    def __init__(self, uow: AbstractNaabuUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=settings.NAABU_INGESTOR_BATCH_SIZE)
        self._processed = 0
        self._skipped = 0

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest Naabu port scan results into database.

        Args:
            program_id: Program UUID for scope association
            results: List of Naabu JSON results

        Returns:
            IngestResult (empty for naabu)
        """
        self._processed = 0
        self._skipped = 0

        await super().ingest(program_id, results)

        logger.info(
            f"Naabu ingestion completed: program={program_id} "
            f"processed={self._processed} skipped={self._skipped}"
        )

        return IngestResult()

    async def _process_batch(self, uow: AbstractNaabuUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a single batch of Naabu results"""
        for result in batch:
            try:
                ip_address = result.get("ip")
                port = result.get("port")
                protocol = result.get("protocol", "tcp")

                if not ip_address or port is None:
                    logger.warning(f"Invalid Naabu result, missing ip or port: {result}")
                    self._skipped += 1
                    continue

                ip_obj = await uow.ip_addresses.ensure(
                    program_id=program_id,
                    address=ip_address,
                    in_scope=True
                )

                scheme = "https" if int(port) == 443 else "http"

                await uow.services.ensure(
                    ip_id=ip_obj.id,
                    scheme=scheme,
                    port=int(port),
                    technologies={}
                )

                self._processed += 1

            except Exception as e:
                logger.error(
                    f"Failed to process Naabu result {result}: {e}",
                    exc_info=True
                )
                self._skipped += 1
                continue
