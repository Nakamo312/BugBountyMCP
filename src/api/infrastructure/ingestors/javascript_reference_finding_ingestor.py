"""JavaScript reference evidence ingestor."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import JavaScriptReferenceFinding
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class JavaScriptReferenceFindingIngestor:
    """Accept JS reference evidence without endpoint materialization side effects."""

    async def ingest(
        self,
        program_id: UUID,
        findings: list[JavaScriptReferenceFinding],
        context: IngestContext | None = None,
    ) -> IngestResult:
        for finding in findings:
            if not isinstance(finding, JavaScriptReferenceFinding):
                raise TypeError(
                    "JavaScriptReferenceFindingIngestor expects "
                    f"JavaScriptReferenceFinding, got {type(finding).__name__}"
                )

        logger.info(
            "JavaScript reference findings collected: program=%s count=%s",
            program_id,
            len(findings),
        )
        return IngestResult()
