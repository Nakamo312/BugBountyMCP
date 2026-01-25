"""Host/Domain Ingestor"""

import json
import logging
from uuid import UUID
from typing import List, Dict, Any

from api.domain.models import ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.application.utils.scope_checker import ScopeChecker
from api.config import Settings

logger = logging.getLogger(__name__)


class HostIngestor(BaseResultIngestor):
    """
    Universal ingestor for saving discovered hosts/domains.

    Used by multiple scanners (subfinder, smap, etc.) to persist all in scope
    domains regardless of HTTP probe results. Prevents losing domains if httpx
    cannot connect.

    Input format:
    {
        "host": "subdomain.example.com"
    }
    """

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=50)
        self.settings = settings
        self._scope_rules: List[ScopeRuleModel] = []
        self._in_scope_count = 0
        self._out_of_scope_count = 0
        self._saved_hosts: List[str] = []

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest discovered hosts and save in scope domains.

        Args:
            program_id: Target program ID
            results: List of results with 'host' key

        Returns:
            IngestResult with saved hosts for downstream processing
        """
        self._in_scope_count = 0
        self._out_of_scope_count = 0
        self._saved_hosts = []

        total_results = len(results)
        successful_batches = 0
        failed_batches = 0

        logger.info(
            f"HostIngestor: Starting ingestion program={program_id} total_results={total_results}"
        )

        async with self.uow as uow:
            self._scope_rules = await uow.scope_rules.find_by_program(program_id)

            for batch_index, batch in enumerate(self._chunks(results, self.batch_size)):
                savepoint_name = f"batch_{batch_index}"
                await uow.create_savepoint(savepoint_name)

                try:
                    await self._process_batch(uow, program_id, batch)
                    await uow.release_savepoint(savepoint_name)
                    successful_batches += 1
                except Exception as exc:
                    await uow.rollback_to_savepoint(savepoint_name)
                    failed_batches += 1
                    logger.error(
                        f"HostIngestor: Batch {batch_index} failed (size={len(batch)}): {exc}"
                    )
            await uow.commit()

        logger.info(
            f"HostIngestor: Ingestion completed program={program_id} "
            f"total={total_results} batches_ok={successful_batches} batches_failed={failed_batches} "
            f"in_scope={self._in_scope_count} out_of_scope={self._out_of_scope_count} "
            f"new={len(self._saved_hosts)}"
        )

        return IngestResult(raw_domains=self._saved_hosts)

    def _chunks(self, data: List[Any], size: int):
        """Split data into chunks of given size"""
        for i in range(0, len(data), size):
            yield data[i:i + size]

    async def _process_batch(self, uow: DNSxUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a batch of host results"""
        for result in batch:
            try:
                if isinstance(result, str):
                    result = json.loads(result)
                host_name = result.get("host")

                if not host_name:
                    logger.warning(f"Invalid host result, missing host: {result}")
                    continue

                if ScopeChecker.is_in_scope(host_name, self._scope_rules):
                    existing = await uow.hosts.get_by_fields(program_id=program_id, host=host_name)

                    await uow.hosts.ensure(
                        program_id=program_id,
                        host=host_name,
                        in_scope=True
                    )
                    self._in_scope_count += 1

                    if not existing:
                        self._saved_hosts.append(host_name)
                else:
                    self._out_of_scope_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to process host result {result}: {e}",
                    exc_info=True
                )
                continue
