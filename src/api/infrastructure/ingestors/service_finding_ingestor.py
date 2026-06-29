"""Fact-oriented ingestion for exposed network services."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import ServiceFinding
from api.infrastructure.ingestors.base_result_ingestor import BaseResultIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork

logger = logging.getLogger(__name__)


class ServiceFindingIngestor(BaseResultIngestor):
    """Persist service facts, independent of source scanner."""

    def __init__(self, uow: AbstractNaabuUnitOfWork, batch_size: int = 100):
        super().__init__(uow, batch_size=batch_size)
        self._processed = 0
        self._skipped = 0
        self._ips: set[str] = set()

    async def before_ingest(
        self,
        uow: AbstractNaabuUnitOfWork,
        program_id: UUID,
        results: list[ServiceFinding],
        context: IngestContext | None = None,
    ) -> None:
        self._processed = 0
        self._skipped = 0
        self._ips = set()

    def build_result(self) -> IngestResult:
        return IngestResult(ips=sorted(self._ips))

    def log_extra(self) -> str:
        return f"processed={self._processed} skipped={self._skipped} ips={len(self._ips)}"

    async def process_record(
        self,
        uow: AbstractNaabuUnitOfWork,
        program_id: UUID,
        finding: ServiceFinding,
        context: IngestContext | None = None,
    ) -> None:
        if not isinstance(finding, ServiceFinding):
            raise TypeError("ServiceFindingIngestor expects ServiceFinding records")

        ip_address = finding.ip.strip()
        if not ip_address:
            logger.warning("Invalid service finding, missing ip: %r", finding)
            self._skipped += 1
            return

        try:
            port = int(finding.port)
        except (TypeError, ValueError):
            logger.warning("Invalid service finding port: %r", finding)
            self._skipped += 1
            return

        scheme = finding.scheme or self._default_scheme(port)
        technologies = dict(finding.technologies)
        if finding.service_name:
            technologies.setdefault("service", finding.service_name)
        technologies.setdefault("source_tool", finding.source_tool)

        ip_obj = await uow.ip_addresses.ensure(
            program_id=program_id,
            address=ip_address,
            in_scope=True,
        )
        await uow.services.ensure(
            ip_id=ip_obj.id,
            scheme=scheme,
            port=port,
            technologies=technologies,
        )

        self._ips.add(ip_address)
        self._processed += 1

    @staticmethod
    def _default_scheme(port: int) -> str:
        return "https" if port == 443 else "http"
