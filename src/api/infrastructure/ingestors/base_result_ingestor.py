"""Base class for batch result ingestors with savepoint support"""
import logging
from typing import Any, Dict, List
from uuid import UUID

from api.application.contracts import IngestContext
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class BaseResultIngestor:
    """
    Base class for result ingestors.

    Handles Unit of Work, savepoints, batch accounting and result assembly.
    Instances keep per-run counters on self and are intentionally non-reentrant.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        has_hook = any(
            base is not BaseResultIngestor
            and (
                "process_record" in base.__dict__
                or (
                    "_process_batch" in base.__dict__
                    and base.__dict__["_process_batch"]
                    is not BaseResultIngestor._process_batch
                )
            )
            for base in cls.__mro__
        )
        if not has_hook:
            raise TypeError(
                f"{cls.__name__} must implement _process_batch or process_record"
            )

    def __init__(self, uow, batch_size: int = 50):
        self.uow = uow
        self.batch_size = batch_size

    async def ingest(
        self,
        program_id: UUID,
        results: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> IngestResult:
        total_results = len(results)
        successful_batches = 0
        failed_batches = 0

        logger.info(
            f"{self.__class__.__name__}: Starting ingestion "
            f"program={program_id} total_results={total_results}"
        )

        try:
            async with self.uow as uow:
                await self.before_ingest(uow, program_id, results, context=context)

                for batch_index, batch in enumerate(self._chunks(results, self.batch_size)):
                    savepoint_name = f"batch_{batch_index}"
                    await uow.create_savepoint(savepoint_name)

                    try:
                        await self._process_batch(
                            uow,
                            program_id,
                            batch,
                            context=context,
                        )
                        await uow.release_savepoint(savepoint_name)
                        successful_batches += 1
                    except Exception as exc:
                        await uow.rollback_to_savepoint(savepoint_name)
                        failed_batches += 1
                        logger.error(
                            f"{self.__class__.__name__}: Batch {batch_index} failed "
                            f"(size={len(batch)}): {exc}"
                        )
                await uow.commit()
        except Exception:
            await self.uow.rollback()
            raise

        extra = self.log_extra()
        logger.info(
            f"{self.__class__.__name__}: Ingestion completed program={program_id} "
            f"total={total_results} batches_ok={successful_batches} "
            f"batches_failed={failed_batches}{f' {extra}' if extra else ''}"
        )
        return self.build_result()

    async def before_ingest(
        self,
        uow,
        program_id: UUID,
        results: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        """Prepare per-run state before the first batch is processed."""

    async def _process_batch(
        self,
        uow,
        program_id: UUID,
        batch: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        """Process one batch through a subclass process_record hook."""
        process_record = self.process_record
        for record in batch:
            await process_record(uow, program_id, record, context=context)

    def build_result(self) -> IngestResult:
        """Build the public result after all batches were processed."""
        return IngestResult()

    def log_extra(self) -> str:
        """Append ingestor-specific counters to the completion log line."""
        return ""

    def _chunks(self, data: List[Any], size: int):
        for i in range(0, len(data), size):
            yield data[i:i + size]
