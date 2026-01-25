"""Smap Result Ingestor"""

import logging
from uuid import UUID
from typing import Any, List, Set, Dict

from api.domain.models import ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.config import Settings
from api.application.utils.scope_checker import ScopeChecker

logger = logging.getLogger(__name__)


class SmapResultIngestor(BaseResultIngestor):
    """
    Ingests Smap port scan results into database.

    Processing flow:
    1. Ensure IP address exists
    2. If hostnames exist and in scope - create host records
    3. Create service records for each port
    4. Batch processing with savepoint recovery

    Smap result format:
    {
        "ip": "217.12.106.105",
        "hostnames": ["suoext.alfabank.ru"],
        "ports": [
            {"port": 443, "service": "https?", "protocol": "tcp"}
        ],
        "start_time": "2026-01-16T02:34:41.519350018Z",
        "end_time": "2026-01-16T02:34:42.143294138Z"
    }
    """

    def __init__(self, uow: AbstractNaabuUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=settings.NAABU_INGESTOR_BATCH_SIZE)
        self._scope_rules: List[ScopeRuleModel] = []
        self._discovered_ips: Set[str] = set()
        self._discovered_hostnames: Set[str] = set()
        self._processed = 0
        self._skipped = 0

    async def ingest(self, program_id: UUID, results: List[Dict[str, Any]]) -> IngestResult:
        """
        Ingest Smap port scan results into database.

        Args:
            program_id: Program UUID for scope association
            results: List of Smap JSON results

        Returns:
            IngestResult with discovered IPs and hostnames
        """
        self._discovered_ips = set()
        self._discovered_hostnames = set()
        self._processed = 0
        self._skipped = 0

        total_results = len(results)
        successful_batches = 0
        failed_batches = 0

        logger.info(
            f"SmapResultIngestor: Starting ingestion program={program_id} total_results={total_results}"
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
                        f"SmapResultIngestor: Batch {batch_index} failed (size={len(batch)}): {exc}"
                    )
            await uow.commit()

        logger.info(
            f"SmapResultIngestor: Ingestion completed program={program_id} "
            f"total={total_results} batches_ok={successful_batches} batches_failed={failed_batches} "
            f"processed={self._processed} skipped={self._skipped} "
            f"ips={len(self._discovered_ips)} hostnames={len(self._discovered_hostnames)}"
        )

        return IngestResult(
            ips=list(self._discovered_ips),
            raw_domains=list(self._discovered_hostnames)
        )

    def _chunks(self, data: List[Any], size: int):
        """Split data into chunks of given size"""
        for i in range(0, len(data), size):
            yield data[i:i + size]

    async def _process_batch(self, uow: AbstractNaabuUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """Process a single batch of Smap results"""
        for result in batch:
            try:
                ip_address = result.get("ip")
                ports = result.get("ports", [])
                hostnames = result.get("hostnames", [])

                if not ip_address:
                    logger.warning(f"Invalid Smap result, missing ip: {result}")
                    self._skipped += 1
                    continue

                if not ports:
                    logger.debug(f"Smap result has no ports: {ip_address}")
                    self._skipped += 1
                    continue

                ip_obj = await uow.ip_addresses.ensure(
                    program_id=program_id,
                    address=ip_address,
                    in_scope=True
                )

                self._discovered_ips.add(ip_address)

                if hostnames:
                    for hostname in hostnames:
                        if ScopeChecker.is_in_scope(hostname, self._scope_rules):
                            self._discovered_hostnames.add(hostname)
                            await uow.hosts.ensure(
                                program_id=program_id,
                                host=hostname,
                                in_scope=True
                            )

                for port_info in ports:
                    port = port_info.get("port")
                    service_name = port_info.get("service", "")

                    if port is None:
                        continue

                    scheme = "https" if int(port) == 443 else "http"

                    await uow.services.ensure(
                        ip_id=ip_obj.id,
                        scheme=scheme,
                        port=int(port),
                        technologies={"service": service_name} if service_name else {}
                    )

                self._processed += 1

            except Exception as e:
                logger.error(
                    f"Failed to process Smap result {result}: {e}",
                    exc_info=True
                )
                self._skipped += 1
                continue
