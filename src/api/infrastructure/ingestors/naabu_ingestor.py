"""Compatibility facade for legacy Naabu ingestion payloads."""
from __future__ import annotations

from typing import Any

from api.application.contracts import IngestContext
from api.application.pipeline.records import ServiceFinding
from api.config import Settings
from api.infrastructure.ingestors.service_finding_ingestor import ServiceFindingIngestor
from api.infrastructure.unit_of_work.interfaces.naabu import AbstractNaabuUnitOfWork


class NaabuResultIngestor(ServiceFindingIngestor):
    """Adapt legacy Naabu dict payloads to ServiceFinding records."""

    def __init__(self, uow: AbstractNaabuUnitOfWork, settings: Settings):
        super().__init__(uow, batch_size=settings.NAABU_INGESTOR_BATCH_SIZE)

    async def ingest(
        self,
        program_id,
        results: list[dict[str, Any]] | list[ServiceFinding],
        context: IngestContext | None = None,
    ):
        return await super().ingest(
            program_id,
            [self._adapt(result) for result in results],
            context=context,
        )

    @staticmethod
    def _adapt(result: dict[str, Any] | ServiceFinding) -> ServiceFinding:
        if isinstance(result, ServiceFinding):
            return result

        ip = result.get("ip") or result.get("host")
        port = result.get("port")
        if not ip or port is None:
            return ServiceFinding(
                ip="",
                port=0,
                source_tool="naabu",
                raw=result,
            )

        port_number = int(port)
        return ServiceFinding(
            ip=str(ip),
            port=port_number,
            protocol=str(result.get("protocol") or "tcp"),
            source_tool="naabu",
            host=str(result.get("host")) if result.get("host") else None,
            scheme="https" if port_number == 443 else "http",
            raw=result,
        )
