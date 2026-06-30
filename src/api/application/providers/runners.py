"""Deprecated compatibility import for infrastructure provider wiring.

Real provider wiring lives in :mod:`api.infrastructure.providers.runners` because
providers construct infrastructure adapters and external runtime integrations. Do
not add new imports of this module; migrate call sites to the infrastructure
provider path and remove this alias after legacy wiring is gone.
"""
from api.infrastructure.providers.runners import CLIRunnerProvider

deprecated_compatibility_import = True

__all__ = ['CLIRunnerProvider']
