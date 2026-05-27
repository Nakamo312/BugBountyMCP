"""Helpers for invoking optional ingestor capabilities."""
from __future__ import annotations

from inspect import signature
from typing import Any
from uuid import UUID

from api.application.contracts import IngestContext


async def ingest_with_optional_context(
    ingestor: Any,
    program_id: UUID,
    batch: list[Any],
    context: IngestContext | None,
) -> Any:
    """Call ingestor.ingest with context only when the ingestor declares it."""
    if context is not None and "context" in signature(ingestor.ingest).parameters:
        return await ingestor.ingest(program_id, batch, context=context)
    return await ingestor.ingest(program_id, batch)
