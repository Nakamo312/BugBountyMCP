"""HTTPX raw process event parser."""
from __future__ import annotations

from api.infrastructure.parsers.process_event_parsers import JSONStdoutProcessEventParser


class HTTPXProcessEventParser(JSONStdoutProcessEventParser):
    """Convert HTTPX JSON stdout lines into normalized result events."""
