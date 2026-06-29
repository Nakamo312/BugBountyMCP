"""Compatibility ingestor for legacy LinkFinder result payloads."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import JavaScriptReferenceFinding, UrlFinding
from api.infrastructure.ingestors.ingest_result import IngestResult
from api.infrastructure.ingestors.javascript_reference_finding_ingestor import (
    JavaScriptReferenceFindingIngestor,
)
from api.infrastructure.ingestors.url_finding_ingestor import UrlFindingIngestor


class LinkFinderResultIngestor:
    """Adapt legacy LinkFinder dict payloads into canonical URL evidence."""

    def __init__(self, *args, **kwargs) -> None:
        self.url_findings = UrlFindingIngestor()
        self.javascript_references = JavaScriptReferenceFindingIngestor()

    async def ingest(
        self,
        program_id: UUID,
        results: list[dict[str, Any]],
        context: IngestContext | None = None,
    ) -> IngestResult:
        url_records: list[UrlFinding] = []
        javascript_reference_records: list[JavaScriptReferenceFinding] = []

        for result in results:
            source_js = str(result.get("source_js") or "").strip()
            source_target = str(result.get("host") or "").strip() or None
            for url in result.get("urls") or []:
                url = str(url).strip()
                if not url:
                    continue
                url_records.append(
                    UrlFinding(
                        url=url,
                        source_tool="linkfinder",
                        source_target=source_target,
                        discovered_from=source_js or None,
                        raw=result,
                    )
                )
                if source_js:
                    javascript_reference_records.append(
                        JavaScriptReferenceFinding(
                            source_url=source_js,
                            referenced_url=url,
                            source_tool="linkfinder",
                            source_target=source_target,
                            raw=result,
                        )
                    )

        result = IngestResult()
        if javascript_reference_records:
            result = result.merge(
                await self.javascript_references.ingest(
                    program_id,
                    javascript_reference_records,
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
