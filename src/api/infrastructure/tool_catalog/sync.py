"""Compatibility wrapper for runtime manifest activation."""
from __future__ import annotations

from api.infrastructure.runtime_manifest import ActivationResult, ManifestActivator

ToolCatalogSyncResult = ActivationResult


class ToolCatalogSyncService(ManifestActivator):
    """Backward-compatible name for older imports."""

    async def sync(self, snapshot):
        return await self.activate(snapshot)
