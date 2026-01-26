"""Amass Result Ingestor"""

import logging
from typing import Any, List, Set, Dict
from uuid import UUID

from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork
from api.infrastructure.parsers.amass_parser import AmassGraphParser

logger = logging.getLogger(__name__)


class AmassResultIngestor(BaseResultIngestor):
    """
    Ingests Amass graph output into database.
    """

    def __init__(self, uow: InfrastructureUnitOfWork, settings: Settings):
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
                "ips": parsed_data["ips"],
                "cidrs": parsed_data.get("cidrs", set()),
                "asns": parsed_data.get("asns", set())
            })
        
        await super().ingest(program_id, result_dicts)
        
        return IngestResult(
            raw_domains=list(parsed_data["domains"]),
            ips=list(parsed_data["ips"]),
            cidrs=list(parsed_data.get("cidrs", [])),
            asns=[str(asn) for asn in parsed_data.get("asns", [])]
        )

    async def _process_batch(self, uow: InfrastructureUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]]):
        """
        Process a batch of Amass results.
        """
        all_domains = set()
        all_ips = set()
        all_cidrs = set()
        all_asns = set()

        for item in batch:
            domains = item.get("domains", [])
            ips = item.get("ips", [])
            cidrs = item.get("cidrs", [])
            asns = item.get("asns", [])

            all_domains.update(domains)
            all_ips.update(ips)
            all_cidrs.update(cidrs)
            all_asns.update(asns)

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
                await uow.ips.ensure(
                    program_id=program_id,
                    address=ip,
                    in_scope=True
                )
            except Exception as e:
                logger.error(f"Failed to process IP {ip}: {e}", exc_info=True)

        for cidr in all_cidrs:
            try:
                existing = await uow.cidrs.get_by_fields(
                    program_id=program_id,
                    cidr=cidr
                )
                if not existing:
                    await uow.cidrs.ensure(
                        program_id=program_id,
                        cidr=cidr
                    )
            except Exception as e:
                logger.error(f"Failed to process CIDR {cidr}: {e}", exc_info=True)

        for asn in all_asns:
            try:
                existing = await uow.asns.get_by_fields(
                    program_id=program_id,
                    asn_number=asn
                )
                if not existing:
                    await uow.asns.ensure(
                        program_id=program_id,
                        asn_number=asn
                    )
            except Exception as e:
                logger.error(f"Failed to process ASN {asn}: {e}", exc_info=True)