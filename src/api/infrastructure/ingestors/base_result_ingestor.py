"""Base class for batch result ingestors with savepoint support"""
from typing import List, Any, Dict
from uuid import UUID
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class BaseResultIngestor(ABC):
    """
    Base class for batch result ingestors.
    Handles savepoint-based batch processing with partial failure support.
    """

    def __init__(self, uow, batch_size: int = 50):
        """
        Initialize ingestor with Unit of Work and batch size.

        Args:
            uow: Unit of Work instance for database operations
            batch_size: Number of records per batch
        """
        self.uow = uow
        self.batch_size = batch_size

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]):
        """
        Ingest results with savepoint-based batch processing.

        Args:
            program_id: Target program identifier
            results: List of raw result dictionaries from scanner
        """
        async with self.uow as uow:
            for batch_index, batch in enumerate(self._chunks(results, self.batch_size)):
                savepoint_name = f"batch_{batch_index}"
                await uow.create_savepoint(savepoint_name)

                try:
                    await self._process_batch(uow, program_id, batch)
                    await uow.release_savepoint(savepoint_name)
                except Exception as exc:
                    await uow.rollback_to_savepoint(savepoint_name)
                    logger.error("Batch %d failed: %s", batch_index, exc)
            await uow.commit()

    @abstractmethod
    async def _process_batch(self, uow, program_id: UUID, batch: List[Dict[str, Any]]):
        """
        Process a single batch of records.
        Must be implemented by subclasses to handle tool-specific ingestion logic.

        Args:
            uow: Unit of Work instance
            program_id: Target program identifier
            batch: Batch of result records to process
        """
        pass

    def _chunks(self, data: List[Any], size: int):
        """
        Split data into chunks of given size.

        Args:
            data: List to split into chunks
            size: Chunk size

        Yields:
            Chunks of data
        """
        for i in range(0, len(data), size):
            yield data[i:i + size]
