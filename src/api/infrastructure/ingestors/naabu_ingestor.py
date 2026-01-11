"""Naabu Result Ingestor"""

import logging
from uuid import UUID
from typing import Any

from api.domain.models import IPAddressModel, ServiceModel
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.config import Settings

logger = logging.getLogger(__name__)


class NaabuResultIngestor:
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
        self.uow = uow
        self.batch_size = settings.NAABU_INGESTOR_BATCH_SIZE

    async def ingest(
        self,
        program_id: UUID,
        results: list[dict[str, Any]]
    ) -> None:
        """
        Ingest Naabu port scan results into database.

        Args:
            program_id: Program UUID for scope association
            results: List of Naabu JSON results
        """
        if not results:
            logger.info("No Naabu results to ingest")
            return

        logger.info(
            f"Starting Naabu ingestion: program={program_id} results={len(results)} "
            f"batch_size={self.batch_size}"
        )

        batches = [
            results[i : i + self.batch_size]
            for i in range(0, len(results), self.batch_size)
        ]

        async with self.uow:
            processed = 0
            failed = 0
            skipped = 0

            for i, batch in enumerate(batches):
                savepoint = f"naabu_batch_{i}"
                await self.uow.create_savepoint(savepoint)

                try:
                    batch_stats = await self._process_batch(batch, program_id)
                    processed += batch_stats["processed"]
                    skipped += batch_stats["skipped"]
                    await self.uow.release_savepoint(savepoint)

                    logger.debug(
                        f"Naabu batch {i+1}/{len(batches)} completed: "
                        f"processed={batch_stats['processed']} skipped={batch_stats['skipped']}"
                    )

                except Exception as e:
                    failed += len(batch)
                    await self.uow.rollback_to_savepoint(savepoint)
                    logger.error(
                        f"Naabu batch {i+1}/{len(batches)} failed: {e}",
                        exc_info=True
                    )

            await self.uow.commit()

        logger.info(
            f"Naabu ingestion completed: program={program_id} "
            f"processed={processed} skipped={skipped} failed={failed} total={len(results)}"
        )

    async def _process_batch(
        self,
        batch: list[dict[str, Any]],
        program_id: UUID
    ) -> dict[str, int]:
        """
        Process a single batch of Naabu results.

        Args:
            batch: Batch of Naabu results
            program_id: Program UUID

        Returns:
            Dictionary with processing statistics
        """
        processed = 0
        skipped = 0

        for result in batch:
            try:
                ip_address = result.get("ip")
                port = result.get("port")
                protocol = result.get("protocol", "tcp")

                if not ip_address or port is None:
                    logger.warning(f"Invalid Naabu result, missing ip or port: {result}")
                    skipped += 1
                    continue

                ip_model = IPAddressModel(
                    address=ip_address,
                    program_id=program_id
                )
                ip_obj = await self.uow.ip_addresses.ensure(
                    ip_model,
                    unique_fields=["address", "program_id"]
                )

                # Map protocol to scheme: https for port 443, http for others
                scheme = "https" if int(port) == 443 else "http"

                await self.uow.services.ensure(
                    ip_id=ip_obj.id,
                    scheme=scheme,
                    port=int(port),
                    technologies={}
                )

                processed += 1

            except Exception as e:
                logger.error(
                    f"Failed to process Naabu result {result}: {e}",
                    exc_info=True
                )
                skipped += 1
                continue

        return {"processed": processed, "skipped": skipped}
