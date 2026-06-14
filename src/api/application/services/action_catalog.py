"""Action catalog application service."""
from __future__ import annotations

from uuid import UUID

from api.application.action_catalog import ActionCatalogStore, CatalogDetail, CatalogItem


class ActionCatalogService:
    """Read-only service for the active action catalog."""

    def __init__(self, store: ActionCatalogStore):
        self.store = store

    async def list_items(self) -> list[CatalogItem]:
        return await self.store.list_items()

    async def get_detail(self, item_id: UUID) -> CatalogDetail:
        return await self.store.get_detail(item_id)

    async def find_detail(self, *, capability: str, profile: str) -> CatalogDetail:
        return await self.store.find_detail(capability=capability, profile=profile)

    async def find_detail_by_event(
        self,
        *,
        event: str,
        profile: str | None = None,
    ) -> CatalogDetail:
        return await self.store.find_detail_by_event(event=event, profile=profile)
