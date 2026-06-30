"""Deprecated compatibility import for terminal run reporting.

Use :mod:`api.application.pipeline.run_completion_reporter` for new imports.
This alias exists only to keep older tests/adapters importable during migration.
"""
from api.application.pipeline.run_completion_reporter import RunCompletionReporter

RunStateReporter = RunCompletionReporter
deprecated_compatibility_import = True

__all__ = ["RunCompletionReporter", "RunStateReporter"]
