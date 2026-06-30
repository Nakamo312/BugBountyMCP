"""Deprecated compatibility import for application event type contracts.

Event type contracts live in :mod:`api.application.event_contracts`. This
infrastructure path is kept temporarily for legacy imports. New application code
must import ``EventType`` from the application contract.
"""

from api.application.event_contracts import EventType

deprecated_compatibility_import = True

__all__ = ["EventType"]
