"""Amass Result Ingestor"""

import logging
from typing import Any, List, Set, Dict
from uuid import UUID

from api.application.contracts import IngestContext
from api.config import Settings
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.infrastructure import InfrastructureUnitOfWork

logger = logging.getLogger(__name__)


class AmassResultIngestor(BaseResultIngestor):
    """
    Ingests Amass graph output into database.
    """

    def __init__(self, uow: InfrastructureUnitOfWork, settings: Settings):
        super().__init__(uow, settings.AMASS_INGESTOR_BATCH_SIZE)
        self.settings = settings

    async def before_ingest(
        self,
        uow: InfrastructureUnitOfWork,
        program_id: UUID,
        results: List[Dict[str, Any]],
        context: IngestContext | None = None,
    ) -> None:
        self._parsed_data = self._collect_facts(results)

    def build_result(self) -> IngestResult:
        return IngestResult(
            raw_domains=list(self._parsed_data["domains"]),
            ips=list(self._parsed_data["ips"]),
            cidrs=list(self._parsed_data.get("cidrs", [])),
            asns=[str(asn) for asn in self._parsed_data.get("asns", [])],
        )

    @staticmethod
    def _collect_facts(results: List[Dict[str, Any]]) -> Dict[str, Set[str]]:
        domains: Set[str] = set()
        ips: Set[str] = set()
        cidrs: Set[str] = set()
        asns: Set[str] = set()

        for item in results:
            domains.update(str(value) for value in item.get("domains", []) if value)
            ips.update(str(value) for value in item.get("ips", []) if value)
            cidrs.update(str(value) for value in item.get("cidrs", []) if value)
            asns.update(str(value) for value in item.get("asns", []) if value)

        return {
            "domains": domains,
            "ips": ips,
            "cidrs": cidrs,
            "asns": asns,
        }

    async def _process_batch(self, uow: InfrastructureUnitOfWork, program_id: UUID, batch: List[Dict[str, Any]], context: IngestContext | None = None) -> None:
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
                asn_number = int(str(asn).removeprefix("AS"))
                existing = await uow.asns.get_by_fields(
                    program_id=program_id,
                    asn_number=asn_number
                )
                if not existing:
                    await uow.asns.ensure(
                        program_id=program_id,
                        asn_number=asn_number
                    )
            except (TypeError, ValueError):
                logger.warning(f"Skipping invalid ASN from Amass result: {asn}")
            except Exception as e:
                logger.error(f"Failed to process ASN {asn}: {e}", exc_info=True)
