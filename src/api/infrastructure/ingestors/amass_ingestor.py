"""Amass Result Ingestor"""

import logging
from typing import Any, List, Set
from uuid import UUID

from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork
from api.infrastructure.parsers.amass_parser import AmassGraphParser

logger = logging.getLogger(__name__)


class AmassResultIngestor(BaseResultIngestor):
    """
    Ingests Amass graph output into database.

    Processing flow:
    1. Parse graph lines to extract domains and IPs
    2. Save domains to hosts table
    3. Save IPs to ip_addresses table
    4. Return domains and IPs for downstream processing

    Amass graph format:
    entity1 (type1) --> relationship --> entity2 (type2)
    """

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, settings.AMASS_INGESTOR_BATCH_SIZE)
        self._discovered_domains: Set[str] = set()
        self._discovered_ips: Set[str] = set()

    async def ingest(self, program_id: UUID, results: List[str]) -> IngestResult:
        """
        Ingest Amass graph lines into database.

        Args:
            program_id: Program UUID
            results: List of graph output lines

        Returns:
            IngestResult with domains and IPs
        """
        self._discovered_domains = set()
        self._discovered_ips = set()

        total_results = len(results)
        successful_batches = 0
        failed_batches = 0

        logger.info(
            f"AmassResultIngestor: Starting ingestion program={program_id} total_lines={total_results}"
        )

        parsed_data = AmassGraphParser.extract_domains_and_ips(results)
        self._discovered_domains = parsed_data["domains"]
        self._discovered_ips = parsed_data["ips"]

        async with self.uow as uow:
            domain_list = list(self._discovered_domains)
            ip_list = list(self._discovered_ips)

            for batch_index, batch in enumerate(self._chunks(domain_list, self.batch_size)):
                savepoint_name = f"domains_batch_{batch_index}"
                await uow.create_savepoint(savepoint_name)

                try:
                    await self._process_domain_batch(uow, program_id, batch)
                    await uow.release_savepoint(savepoint_name)
                    successful_batches += 1
                except Exception as exc:
                    await uow.rollback_to_savepoint(savepoint_name)
                    failed_batches += 1
                    logger.error(
                        f"AmassResultIngestor: Domain batch {batch_index} failed (size={len(batch)}): {exc}"
                    )

            for batch_index, batch in enumerate(self._chunks(ip_list, self.batch_size)):
                savepoint_name = f"ips_batch_{batch_index}"
                await uow.create_savepoint(savepoint_name)

                try:
                    await self._process_ip_batch(uow, program_id, batch)
                    await uow.release_savepoint(savepoint_name)
                    successful_batches += 1
                except Exception as exc:
                    await uow.rollback_to_savepoint(savepoint_name)
                    failed_batches += 1
                    logger.error(
                        f"AmassResultIngestor: IP batch {batch_index} failed (size={len(batch)}): {exc}"
                    )

            await uow.commit()

        logger.info(
            f"AmassResultIngestor: Ingestion completed program={program_id} "
            f"batches_ok={successful_batches} batches_failed={failed_batches} "
            f"domains={len(self._discovered_domains)} ips={len(self._discovered_ips)}"
        )

        return IngestResult(
            raw_domains=list(self._discovered_domains),
            ips=list(self._discovered_ips)
        )

    def _chunks(self, data: List[Any], size: int):
        """Split data into chunks of given size"""
        for i in range(0, len(data), size):
            yield data[i:i + size]

    async def _process_domain_batch(self, uow: DNSxUnitOfWork, program_id: UUID, batch: List[str]):
        """Process a batch of discovered domains"""
        for domain in batch:
            try:
                await uow.hosts.ensure(
                    program_id=program_id,
                    host=domain,
                    in_scope=True
                )
            except Exception as e:
                logger.error(
                    f"Failed to process domain {domain}: {e}",
                    exc_info=True
                )

    async def _process_ip_batch(self, uow: DNSxUnitOfWork, program_id: UUID, batch: List[str]):
        """Process a batch of discovered IP addresses"""
        for ip_address in batch:
            try:
                await uow.ip_addresses.ensure(
                    program_id=program_id,
                    address=ip_address,
                    in_scope=True
                )
            except Exception as e:
                logger.error(
                    f"Failed to process IP {ip_address}: {e}",
                    exc_info=True
                )
