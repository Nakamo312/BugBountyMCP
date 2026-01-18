"""Smap Result Ingestor"""

import logging
from uuid import UUID
from typing import Any, List, Set

from api.domain.models import IPAddressModel, ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.config import Settings
from api.application.utils.scope_checker import ScopeChecker

logger = logging.getLogger(__name__)


class SmapResultIngestor:
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
        self.uow = uow
        self.batch_size = settings.NAABU_INGESTOR_BATCH_SIZE
        self._scope_rules: List[ScopeRuleModel] = []
        self._discovered_ips: Set[str] = set()
        self._discovered_hostnames: Set[str] = set()

    async def ingest(
        self,
        program_id: UUID,
        results: list[dict[str, Any]]
    ) -> IngestResult:
        """
        Ingest Smap port scan results into database.

        Args:
            program_id: Program UUID for scope association
            results: List of Smap JSON results

        Returns:
            IngestResult with discovered IPs and hostnames
        """
        if not results:
            logger.info("No Smap results to ingest")
            return IngestResult()

        logger.info(
            f"Starting Smap ingestion: program={program_id} results={len(results)} "
            f"batch_size={self.batch_size}"
        )

        self._discovered_ips = set()
        self._discovered_hostnames = set()

        async with self.uow as uow:
            self._scope_rules = await uow.scope_rules.find_by_program(program_id)

        batches = [
            results[i : i + self.batch_size]
            for i in range(0, len(results), self.batch_size)
        ]

        async with self.uow:
            processed = 0
            failed = 0
            skipped = 0

            for i, batch in enumerate(batches):
                savepoint = f"smap_batch_{i}"
                await self.uow.create_savepoint(savepoint)

                try:
                    batch_stats = await self._process_batch(batch, program_id)
                    processed += batch_stats["processed"]
                    skipped += batch_stats["skipped"]
                    await self.uow.release_savepoint(savepoint)

                    logger.debug(
                        f"Smap batch {i+1}/{len(batches)} completed: "
                        f"processed={batch_stats['processed']} skipped={batch_stats['skipped']}"
                    )

                except Exception as e:
                    failed += len(batch)
                    await self.uow.rollback_to_savepoint(savepoint)
                    logger.error(
                        f"Smap batch {i+1}/{len(batches)} failed: {e}",
                        exc_info=True
                    )

            await self.uow.commit()

        logger.info(
            f"Smap ingestion completed: program={program_id} "
            f"processed={processed} skipped={skipped} failed={failed} total={len(results)} "
            f"ips={len(self._discovered_ips)} hostnames={len(self._discovered_hostnames)}"
        )

        return IngestResult(
            ips=list(self._discovered_ips),
            hostnames=list(self._discovered_hostnames)
        )

    async def _process_batch(
        self,
        batch: list[dict[str, Any]],
        program_id: UUID
    ) -> dict[str, int]:
        """
        Process a single batch of Smap results.

        Args:
            batch: Batch of Smap results
            program_id: Program UUID

        Returns:
            Dictionary with processing statistics
        """
        processed = 0
        skipped = 0

        for result in batch:
            try:
                ip_address = result.get("ip")
                ports = result.get("ports", [])
                hostnames = result.get("hostnames", [])

                if not ip_address:
                    logger.warning(f"Invalid Smap result, missing ip: {result}")
                    skipped += 1
                    continue

                if not ports:
                    logger.debug(f"Smap result has no ports: {ip_address}")
                    skipped += 1
                    continue

                ip_obj = await self.uow.ip_addresses.ensure(
                    program_id=program_id,
                    address=ip_address,
                    in_scope=True
                )

                self._discovered_ips.add(ip_address)

                if hostnames:
                    for hostname in hostnames:
                        if ScopeChecker.is_in_scope(hostname, self._scope_rules):
                            self._discovered_hostnames.add(hostname)

                for port_info in ports:
                    port = port_info.get("port")
                    service_name = port_info.get("service", "")

                    if port is None:
                        continue

                    scheme = "https" if int(port) == 443 else "http"

                    await self.uow.services.ensure(
                        ip_id=ip_obj.id,
                        scheme=scheme,
                        port=int(port),
                        technologies={"service": service_name} if service_name else {}
                    )

                processed += 1

            except Exception as e:
                logger.error(
                    f"Failed to process Smap result {result}: {e}",
                    exc_info=True
                )
                skipped += 1
                continue

        return {"processed": processed, "skipped": skipped}
