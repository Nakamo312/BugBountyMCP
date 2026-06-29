"""Compatibility facade for legacy host ingestion payloads."""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import HostFinding
from api.infrastructure.ingestors.host_finding_ingestor import HostFindingIngestor
from api.infrastructure.unit_of_work.interfaces.dnsx import DNSxUnitOfWork

logger = logging.getLogger(__name__)


class HostIngestor(HostFindingIngestor):
    """Backward-compatible name and input adapter for host finding ingestion."""

    async def process_record(
        self,
        uow: DNSxUnitOfWork,
        program_id: UUID,
        finding: HostFinding | dict[str, Any] | str,
        context: IngestContext | None = None,
    ) -> None:
        host_finding = self._coerce_host_finding(finding)
        if host_finding is None:
            logger.warning("Invalid host finding, missing host: %r", finding)
            return
        await super().process_record(
            uow,
            program_id,
            host_finding,
            context=context,
        )

    @staticmethod
    def _coerce_host_finding(finding: HostFinding | dict[str, Any] | str) -> HostFinding | None:
        if isinstance(finding, HostFinding):
            return finding
        if isinstance(finding, str):
            host = finding.strip()
            return HostFinding(host=host, source_tool="legacy") if host else None
        if isinstance(finding, dict):
            value = finding.get("host") or finding.get("hostname")
            host = str(value).strip() if value else ""
            return HostFinding(host=host, source_tool="legacy", raw=finding) if host else None
        return None
