"""Subjack result ingestor for subdomain takeover findings"""
import logging
from typing import Any
from uuid import UUID

from api.config import Settings
from api.domain.models import FindingModel, VulnTypeModel
from api.domain.enums import Severity
from api.infrastructure.events.event_bus import EventBus
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.unit_of_work.interfaces.httpx import HTTPXUnitOfWork

logger = logging.getLogger(__name__)

SUBDOMAIN_TAKEOVER_CODE = "subdomain_takeover"


class SubjackResultIngestor(BaseResultIngestor):
    """
    Handles batch ingestion of Subjack subdomain takeover scan results.
    Creates findings for vulnerable subdomains with host_id reference.
    """

    def __init__(self, uow: HTTPXUnitOfWork, bus: EventBus, settings: Settings):
        super().__init__(uow, settings.HTTPX_INGESTOR_BATCH_SIZE)
        self.bus = bus
        self.settings = settings

    async def _process_batch(self, uow: HTTPXUnitOfWork, program_id: UUID, batch: list[dict[str, Any]]):
        """Process a batch of Subjack results"""
        vuln_type = await self._ensure_vuln_type(uow)

        for data in batch:
            await self._process_result(uow, program_id, vuln_type.id, data)

    async def _ensure_vuln_type(self, uow: HTTPXUnitOfWork) -> VulnTypeModel:
        """Ensure subdomain_takeover vuln_type exists"""
        existing = await uow.vuln_types.get_by_fields(code=SUBDOMAIN_TAKEOVER_CODE)
        if existing:
            return existing

        vuln_type = VulnTypeModel(
            code=SUBDOMAIN_TAKEOVER_CODE,
            severity=Severity.HIGH,
            category="infrastructure"
        )
        await uow.vuln_types.add(vuln_type)
        return vuln_type

    async def _process_result(
        self,
        uow: HTTPXUnitOfWork,
        program_id: UUID,
        vuln_type_id: UUID,
        data: dict[str, Any]
    ):
        """Process single Subjack result and create finding"""
        subdomain = data.get("subdomain")
        service = data.get("service")
        vulnerable = data.get("vulnerable", False)
        cname = data.get("cname")

        if not subdomain or not vulnerable:
            logger.debug("Skipping non-vulnerable or invalid Subjack result")
            return

        host = await uow.hosts.get_by_fields(program_id=program_id, host=subdomain)
        if not host:
            logger.warning(f"Host {subdomain} not found in program {program_id}, skipping finding")
            return

        description = f"Subdomain takeover detected on {subdomain} via {service}"
        if cname:
            description += f" (CNAME: {cname})"

        evidence = {
            "subdomain": subdomain,
            "service": service,
            "cname": cname,
            "tool": "subjack"
        }

        finding = FindingModel(
            program_id=program_id,
            vuln_type_id=vuln_type_id,
            host_id=host.id,
            description=description,
            evidence=evidence,
            verified=False,
            false_positive=False
        )

        await uow.findings.ensure(
            program_id=program_id,
            vuln_type_id=vuln_type_id,
            host_id=host.id,
            unique_fields=["program_id", "vuln_type_id", "host_id"]
        )

        logger.info(f"Created subdomain takeover finding: {subdomain} ({service})")
