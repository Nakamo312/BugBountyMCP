"""ASNMap Result Ingestor"""

import logging
from typing import Any, List
from uuid import UUID

from api.config import Settings
from api.domain.models import ASNModel, CIDRModel, OrganizationModel
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.events.event_types import EventType
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.unit_of_work.interfaces.asnmap import ASNMapUnitOfWork

logger = logging.getLogger(__name__)


class ASNMapResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of ASNMap scan results into domain entities.

    Processes ASNMap output format:
    {
        "timestamp": "2026-01-09 13:50:57...",
        "input": "example.com",
        "as_number": "AS15169",
        "as_name": "GOOGLE",
        "as_country": "US",
        "as_range": ["8.8.8.0/24", "8.8.4.0/24"]
    }

    Creates/updates:
    - Organizations (optional, from as_name)
    - ASNs (as_number, as_name, as_country)
    - CIDRs (as_range)

    Publishes events:
    - ASN_DISCOVERED (for each unique ASN)
    - CIDR_DISCOVERED (for each unique CIDR)
    """

    def __init__(self, uow: ASNMapUnitOfWork, bus: EventBus, settings: Settings):
        super().__init__(uow, settings.ASNMAP_INGESTOR_BATCH_SIZE)
        self.bus = bus
        self.settings = settings
        self._discovered_asns: set[str] = set()
        self._discovered_cidrs: set[str] = set()

    async def ingest(self, program_id: UUID, results: List[dict[str, Any]]):
        """Ingest ASNMap results and publish discovery events"""
        self._discovered_asns = set()
        self._discovered_cidrs = set()

        await super().ingest(program_id, results)

        if self._discovered_asns:
            await self._publish_asn_discovered(program_id, list(self._discovered_asns))

        if self._discovered_cidrs:
            await self._publish_cidr_discovered(program_id, list(self._discovered_cidrs))

    async def _process_batch(self, uow: ASNMapUnitOfWork, program_id: UUID, batch: List[dict[str, Any]]):
        """Process batch of ASNMap results"""
        for data in batch:
            await self._process_record(uow, program_id, data)

    async def _process_record(
        self,
        uow: ASNMapUnitOfWork,
        program_id: UUID,
        data: dict[str, Any]
    ):
        """
        Process single ASNMap result.

        Creates:
        1. Organization (optional)
        2. ASN
        3. CIDRs (one per as_range entry)
        """
        as_number_str = data.get("as_number")
        as_name = data.get("as_name")
        as_country = data.get("as_country")
        as_ranges = data.get("as_range", [])

        if not as_number_str:
            logger.debug("Skipping ASNMap result without as_number")
            return

        try:
            asn_number = int(as_number_str.replace("AS", ""))
        except (ValueError, AttributeError):
            logger.warning(f"Invalid ASN format: {as_number_str}")
            return

        if not as_name:
            logger.debug(f"Skipping ASN {as_number_str} without organization name")
            return

        organization_id = None
        if as_name:
            org = await uow.organizations.ensure(
                program_id=program_id,
                name=as_name,
                metadata={"country": as_country} if as_country else {}
            )
            organization_id = org.id

        asn = await uow.asns.ensure(
            program_id=program_id,
            asn_number=asn_number,
            organization_name=as_name,
            country_code=as_country,
            description=None,
            organization_id=organization_id
        )

        self._discovered_asns.add(as_number_str)

        for cidr_str in as_ranges:
            if not cidr_str:
                continue

            ip_count = self._calculate_ip_count(cidr_str)

            await uow.cidrs.ensure(
                program_id=program_id,
                cidr=cidr_str,
                asn_id=asn.id,
                ip_count=ip_count,
                expanded=False,
                in_scope=True
            )

            self._discovered_cidrs.add(cidr_str)

        logger.debug(
            f"Processed ASNMap result: asn={as_number_str} "
            f"org={as_name} cidrs={len(as_ranges)}"
        )

    def _calculate_ip_count(self, cidr: str) -> int:
        """Calculate number of IPs in CIDR block"""
        try:
            if "/" not in cidr:
                return 1

            prefix = int(cidr.split("/")[1])

            if ":" in cidr:
                return 2 ** (128 - prefix)
            else:
                return 2 ** (32 - prefix)
        except (ValueError, IndexError):
            logger.warning(f"Failed to calculate IP count for CIDR: {cidr}")
            return 0

    async def _publish_asn_discovered(self, program_id: UUID, asns: list[str]):
        """Publish ASN_DISCOVERED event"""
        logger.info(f"Publishing ASN discovered event: program={program_id} count={len(asns)}")
        await self.bus.publish(
            EventType.ASN_DISCOVERED,
            {
                "program_id": str(program_id),
                "asns": asns
            }
        )

    async def _publish_cidr_discovered(self, program_id: UUID, cidrs: list[str]):
        """Publish CIDR_DISCOVERED event"""
        logger.info(f"Publishing CIDR discovered event: program={program_id} count={len(cidrs)}")
        await self.bus.publish(
            EventType.CIDR_DISCOVERED,
            {
                "program_id": str(program_id),
                "cidrs": cidrs
            }
        )
