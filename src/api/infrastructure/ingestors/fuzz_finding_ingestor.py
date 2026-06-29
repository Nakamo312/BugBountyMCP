"""Fuzzing evidence ingestor."""
from __future__ import annotations

import logging
from uuid import UUID

from api.application.contracts import IngestContext
from api.application.pipeline.records import FuzzFinding
from api.infrastructure.ingestors.ingest_result import IngestResult

logger = logging.getLogger(__name__)


class FuzzFindingIngestor:
    """Accept fuzzing observations without materializing inventory endpoints."""

    async def ingest(
        self,
        program_id: UUID,
        findings: list[FuzzFinding],
        context: IngestContext | None = None,
    ) -> IngestResult:
        count = 0
        for finding in findings:
            if not isinstance(finding, FuzzFinding):
                raise TypeError(
                    f"FuzzFindingIngestor expects FuzzFinding, got {type(finding).__name__}"
                )
            if finding.url.strip():
                count += 1

        logger.info(
            "Fuzz findings collected: program=%s count=%s",
            program_id,
            count,
        )
        return IngestResult()
