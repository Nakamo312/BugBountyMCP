"""Deprecated compatibility import for pipeline wiring.

Real pipeline wiring lives in :mod:`api.infrastructure.providers.pipeline`
because it constructs infrastructure adapters for application ports. Do not add
new imports of this module; migrate call sites to the infrastructure provider
path and remove this alias once legacy wiring is gone.
"""
from api.infrastructure.providers.pipeline import PipelineProvider

deprecated_compatibility_import = True

__all__ = ["PipelineProvider"]
