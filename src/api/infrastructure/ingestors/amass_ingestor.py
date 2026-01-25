"""Amass Result Ingestor"""

import logging
from typing import Any, List, Set, Dict
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
    """

    def __init__(self, uow: DNSxUnitOfWork, settings: Settings):
        super().__init__(uow, settings.AMASS_INGESTOR_BATCH_SIZE)
        self.settings = settings

    async def ingest(self, program_id: UUID, results: List[str]) -> IngestResult:
        """
        Ingest Amass graph lines into database.

        Args:
            program_id: Program UUID
            results: List of graph output lines

        Returns:
            IngestResult with domains and IPs
        """
        parsed_data = AmassGraphParser.extract_domains_and_ips(results)
        
        result_dicts = []
        for line in results:
            result_dicts.append({
                "raw_line": line,
                "domains": parsed_data["domains"],
                "ips": parsed_data["ips"]
            })
        
        await super().ingest(program_id, result_dicts)
        
        return IngestResult(
            raw_domains=list(parsed_data["domains"]),
            ips=list(parsed_data["ips"])
        )

    async def _process_batch(self, uow: DNSxUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """
        Process a batch of Amass results.
        """
        all_domains = set()
        all_ips = set()
        
        for item in batch:
            domains = item.get("domains", [])
            ips = item.get("ips", [])
            all_domains.update(domains)
            all_ips.update(ips)
        
        for domain in all_domains:
            try:
                await uow.hosts.ensure(
                    program_id=program_id,
                    host=domain,
                    in_scope=True
                )
            except Exception as e:
                logger.error(f"Failed to process domain {domain}: {e}", exc_info=True)

        for ip in all_ips:
            try:
                await uow.ip_addresses.ensure(
                    program_id=program_id,
                    address=ip,
                    in_scope=True
                )
            except Exception as e:
                logger.error(f"Failed to process IP {ip}: {e}", exc_info=True)