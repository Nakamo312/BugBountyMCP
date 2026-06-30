"""Reusable parsers for raw ProcessEvent streams."""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from api.application.process_event_contracts import ProcessEvent

logger = logging.getLogger(__name__)


class JSONStdoutProcessEventParser:
    """Convert JSON-object stdout lines into normalized result events."""

    async def parse_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
    ) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue

            data = self._parse_payload(event.payload)
            if data is None:
                continue

            yield ProcessEvent(type="result", payload=data)

    def _parse_payload(self, payload: str) -> dict[str, Any] | None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.debug("Non-JSON stdout line skipped: %r", payload)
            return None

        return data if isinstance(data, dict) else None


class JSONStdoutItemsProcessEventParser(JSONStdoutProcessEventParser):
    """Convert JSON-object or JSON-array stdout lines into result events."""

    async def parse_stream(
        self,
        stream: AsyncIterator[ProcessEvent],
    ) -> AsyncIterator[ProcessEvent]:
        async for event in stream:
            if event.type != "stdout" or not event.payload:
                continue

            try:
                data = json.loads(event.payload)
            except json.JSONDecodeError:
                logger.debug("Non-JSON stdout line skipped: %r", event.payload)
                continue

            if isinstance(data, dict):
                yield ProcessEvent(type="result", payload=data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        yield ProcessEvent(type="result", payload=item)
