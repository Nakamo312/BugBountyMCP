"""Batch processors for typed canonical records."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from api.application.pipeline.records import (
    CanonicalRecord,
    FuzzFinding,
    JavaScriptReferenceFinding,
    ServiceFinding,
    UrlFinding,
)
from api.application.services.batch_processor import BaseBatchProcessor
from api.config import Settings


class CanonicalBatchProcessor(BaseBatchProcessor[CanonicalRecord]):
    """Batch ProcessEvent(type='canonical_record') payloads."""

    def _get_batch_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "min": settings.HOST_FINDING_BATCH_MIN,
            "max": settings.HOST_FINDING_BATCH_MAX,
            "timeout": settings.HOST_FINDING_BATCH_TIMEOUT,
        }

    def _extract_item(self, event) -> CanonicalRecord | None:
        if event.type == "canonical_record" and event.payload:
            return event.payload
        return None


class UrlEvidenceBatchProcessor(BaseBatchProcessor[CanonicalRecord]):
    """Batch URL-like evidence records without lossy URL-resource dedupe."""

    def _get_batch_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "min": settings.URL_FINDING_BATCH_MIN,
            "max": settings.URL_FINDING_BATCH_MAX,
            "timeout": settings.URL_FINDING_BATCH_TIMEOUT,
        }

    async def batch_stream(self, stream) -> AsyncIterator[list[CanonicalRecord]]:
        batch: list[CanonicalRecord] = []
        last_batch_time = asyncio.get_event_loop().time()
        seen_references: set[tuple[str, str]] = set()
        seen_fuzz: set[tuple[object, ...]] = set()

        async for event in stream:
            item = self._extract_item(event)
            if item is None:
                continue
            if isinstance(item, JavaScriptReferenceFinding):
                key = (item.source_url, item.referenced_url)
                if key in seen_references:
                    continue
                seen_references.add(key)
            elif isinstance(item, FuzzFinding):
                key = (
                    item.url,
                    item.status_code,
                    item.length,
                    item.words,
                    item.lines,
                    item.redirect_location,
                )
                if key in seen_fuzz:
                    continue
                seen_fuzz.add(key)

            batch.append(item)
            current_time = asyncio.get_event_loop().time()
            time_elapsed = current_time - last_batch_time

            if len(batch) >= self.batch_size_max:
                yield batch
                batch = []
                last_batch_time = current_time
            elif len(batch) >= self.batch_size_min and time_elapsed >= self.batch_timeout:
                yield batch
                batch = []
                last_batch_time = current_time

        if batch:
            yield batch

    def _extract_item(self, event) -> CanonicalRecord | None:
        if event.type == "canonical_record" and isinstance(
            event.payload,
            (UrlFinding, JavaScriptReferenceFinding, FuzzFinding),
        ):
            return event.payload
        return None


# Compatibility alias for older pipeline/catalog references.
UrlFindingBatchProcessor = UrlEvidenceBatchProcessor



class ServiceFindingBatchProcessor(BaseBatchProcessor[ServiceFinding]):
    """Batch service canonical records with port-scan sizing."""

    def _get_batch_config(self, settings: Settings) -> dict[str, Any]:
        return {
            "min": settings.SERVICE_FINDING_BATCH_MIN,
            "max": settings.SERVICE_FINDING_BATCH_MAX,
            "timeout": settings.SERVICE_FINDING_BATCH_TIMEOUT,
        }

    def _extract_item(self, event) -> ServiceFinding | None:
        if event.type == "canonical_record" and isinstance(event.payload, ServiceFinding):
            return event.payload
        return None
