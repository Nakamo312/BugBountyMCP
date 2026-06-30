"""Deprecated compatibility import for the application process-event contract.

The source of truth is :mod:`api.application.process_event_contracts`. Keep this
alias only for old infrastructure imports while call sites migrate.
"""
from api.application.process_event_contracts import ProcessEvent

deprecated_compatibility_import = True

__all__ = ["ProcessEvent"]
