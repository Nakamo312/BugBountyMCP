"""Deprecated compatibility alias for infrastructure pipeline component catalog.

The concrete catalog wires CLI runners, parsers, ingestors, and processors, so the
implementation lives in ``api.infrastructure.pipeline.catalog``. Do not add new
component registrations here.
"""
from __future__ import annotations

from api.infrastructure.pipeline.catalog import (  # noqa: F401
    INGESTORS,
    LEGACY_CLI_RUNNERS,
    PARSERS,
    PROCESSORS,
    RUNNERS,
    RunnerRef,
    resolve_component,
    resolve_parser_ref,
    resolve_runner_ref,
    validate_component_refs,
)

__all__ = [
    "INGESTORS",
    "LEGACY_CLI_RUNNERS",
    "PARSERS",
    "PROCESSORS",
    "RUNNERS",
    "RunnerRef",
    "resolve_component",
    "resolve_parser_ref",
    "resolve_runner_ref",
    "validate_component_refs",
]
