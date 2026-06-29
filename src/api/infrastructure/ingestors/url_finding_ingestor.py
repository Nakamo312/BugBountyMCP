"""URL evidence ingestor."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import UrlFinding
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class UrlFindingIngestor:
    """Collect discovered URLs without materializing inventory endpoints."""

    async def ingest(
        self,
        program_id: UUID,
        findings: list[UrlFinding],
        context: IngestContext | None = None,
    ) -> IngestResult:
        urls: list[str] = []
        js_files: list[str] = []
        seen: set[str] = set()
        seen_js: set[str] = set()
        for finding in findings:
            if not isinstance(finding, UrlFinding):
                raise TypeError(
                    f"UrlFindingIngestor expects UrlFinding, got {type(finding).__name__}"
                )
            url = finding.url.strip()
            if not url:
                continue
            if finding.metadata.get("asset_type") == "javascript" and url not in seen_js:
                seen_js.add(url)
                js_files.append(url)
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)

        logger.info(
            "URL findings collected: program=%s count=%s",
            program_id,
            len(urls),
        )
        return IngestResult(urls=urls, js_files=js_files)
