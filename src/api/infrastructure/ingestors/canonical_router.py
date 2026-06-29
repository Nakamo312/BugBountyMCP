"""Route canonical records to fact-specific ingestors."""
from __future__ import annotations

from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import (
    CanonicalRecord,
    FuzzFinding,
    HostFinding,
    JavaScriptReferenceFinding,
    ServiceFinding,
    UrlFinding,
)
from api.infrastructure.ingestors.fuzz_finding_ingestor import FuzzFindingIngestor
from api.infrastructure.ingestors.host_finding_ingestor import HostFindingIngestor
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.service_finding_ingestor import ServiceFindingIngestor
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor


class CanonicalIngestorRouter:
    """Dispatch canonical records by fact type without tool-specific ingestors."""

    def __init__(
        self,
        host_findings: HostFindingIngestor,
        url_findings: UrlFindingIngestor,
        javascript_references: JavaScriptReferenceFindingIngestor,
        fuzz_findings: FuzzFindingIngestor,
        service_findings: ServiceFindingIngestor,
    ):
        self.host_findings = host_findings
        self.url_findings = url_findings
        self.javascript_references = javascript_references
        self.fuzz_findings = fuzz_findings
        self.service_findings = service_findings

    async def ingest(
        self,
        program_id: UUID,
        records: list[CanonicalRecord],
        context: IngestContext | None = None,
    ) -> IngestResult:
        host_records: list[HostFinding] = []
        url_records: list[UrlFinding] = []
        javascript_reference_records: list[JavaScriptReferenceFinding] = []
        fuzz_records: list[FuzzFinding] = []
        service_records: list[ServiceFinding] = []

        for record in records:
            if isinstance(record, HostFinding):
                host_records.append(record)
            elif isinstance(record, UrlFinding):
                url_records.append(record)
            elif isinstance(record, JavaScriptReferenceFinding):
                javascript_reference_records.append(record)
            elif isinstance(record, FuzzFinding):
                fuzz_records.append(record)
            elif isinstance(record, ServiceFinding):
                service_records.append(record)
            else:
                raise TypeError(
                    f"Unsupported canonical record type: {type(record).__name__}"
                )

        result = IngestResult()
        if host_records:
            result = result.merge(
                await self.host_findings.ingest(
                    program_id,
                    host_records,
                    context=context,
                )
            )
        if javascript_reference_records:
            result = result.merge(
                await self.javascript_references.ingest(
                    program_id,
                    javascript_reference_records,
                    context=context,
                )
            )
        if fuzz_records:
            result = result.merge(
                await self.fuzz_findings.ingest(
                    program_id,
                    fuzz_records,
                    context=context,
                )
            )
        if service_records:
            result = result.merge(
                await self.service_findings.ingest(
                    program_id,
                    service_records,
                    context=context,
                )
            )
        if url_records:
            result = result.merge(
                await self.url_findings.ingest(
                    program_id,
                    url_records,
                    context=context,
                )
            )
        return result
