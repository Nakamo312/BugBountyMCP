"""PostgreSQL-backed action catalog read model."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.action_catalog import (
    CatalogDetail,
    CatalogItem,
    CatalogItemNotFound,
    CatalogNotReady,
)
from api.application.execution_limits import ExecutionBudget, ToolOptionSpec
from api.infrastructure.adapters.orm import tool_catalog_entries, tool_catalog_snapshots


class SqlActionCatalogStore:
    """Reads the active tool catalog from PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    @staticmethod
    def _item(row) -> CatalogItem:
        return CatalogItem(
            id=row["id"],
            capability=row["capability_id"],
            profile=row["profile_id"],
            capability_label=row["capability_label"],
            profile_label=row["profile_label"],
            safety_level=row["safety_class"],
            requires_approval=bool(row["requires_approval"]),
            mode=row["mode"],
        )

    @staticmethod
    def _submit(row) -> dict:
        return {
            "method": "POST",
            "path": "/api/v1/actions",
            "body": {
                "catalog_id": str(row["id"]),
                "targets": [],
                "options": {},
            },
        }

    @staticmethod
    def _detail(row) -> CatalogDetail:
        manifest_fragment = dict(row.get("manifest_fragment") or {})
        profile_fragment = dict(manifest_fragment.get("profile") or {})
        option_schema = {
            name: ToolOptionSpec.model_validate(spec)
            for name, spec in dict(profile_fragment.get("options") or {}).items()
        }
        return CatalogDetail(
            **SqlActionCatalogStore._item(row).model_dump(),
            snapshot_id=row["snapshot_id"],
            queue=row["queue"],
            request_event=row["request_event"],
            default_profile=row["default_profile"],
            scope_policy=row["scope_policy"],
            allowed_options=list(row["allowed_options"] or []),
            option_schema=option_schema,
            execution_budget=ExecutionBudget.model_validate(
                profile_fragment.get("budgets") or {}
            ),
            frontend=dict(row["frontend"] or {}),
            submit=SqlActionCatalogStore._submit(row),
        )

    @staticmethod
    def _base_select():
        return (
            select(
                tool_catalog_entries.c.id,
                tool_catalog_entries.c.snapshot_id,
                tool_catalog_entries.c.capability_id,
                tool_catalog_entries.c.profile_id,
                tool_catalog_entries.c.capability_label,
                tool_catalog_entries.c.profile_label,
                tool_catalog_entries.c.request_event,
                tool_catalog_entries.c.queue,
                tool_catalog_entries.c.default_profile,
                tool_catalog_entries.c.mode,
                tool_catalog_entries.c.scope_policy,
                tool_catalog_entries.c.safety_class,
                tool_catalog_entries.c.allowed_options,
                tool_catalog_entries.c.requires_approval,
                tool_catalog_entries.c.frontend,
                tool_catalog_entries.c.manifest_fragment,
            )
            .select_from(
                tool_catalog_entries.join(
                    tool_catalog_snapshots,
                    tool_catalog_entries.c.snapshot_id == tool_catalog_snapshots.c.id,
                )
            )
            .where(
                tool_catalog_entries.c.active.is_(True),
                tool_catalog_snapshots.c.deactivated_at.is_(None),
                tool_catalog_snapshots.c.activated_at.is_not(None),
            )
        )

    async def list_items(self) -> list[CatalogItem]:
        async with self.session_factory() as session:
            result = await session.execute(
                self._base_select().order_by(
                    tool_catalog_entries.c.capability_id.asc(),
                    tool_catalog_entries.c.profile_id.asc(),
                )
            )
            rows = result.mappings().all()

        if not rows:
            raise CatalogNotReady("active action catalog is not ready")
        return [self._item(row) for row in rows]

    async def get_detail(self, item_id: UUID) -> CatalogDetail:
        async with self.session_factory() as session:
            snapshot = await session.execute(
                select(tool_catalog_snapshots.c.id).where(
                    tool_catalog_snapshots.c.deactivated_at.is_(None),
                    tool_catalog_snapshots.c.activated_at.is_not(None),
                )
            )
            if snapshot.scalar_one_or_none() is None:
                raise CatalogNotReady("active action catalog is not ready")

            result = await session.execute(
                self._base_select().where(tool_catalog_entries.c.id == item_id)
            )
            row = result.mappings().one_or_none()

        if row is None:
            raise CatalogItemNotFound(f"action catalog item not found: {item_id}")
        return self._detail(row)
    async def find_detail(self, *, capability: str, profile: str) -> CatalogDetail:
        async with self.session_factory() as session:
            snapshot = await session.execute(
                select(tool_catalog_snapshots.c.id).where(
                    tool_catalog_snapshots.c.deactivated_at.is_(None),
                    tool_catalog_snapshots.c.activated_at.is_not(None),
                )
            )
            if snapshot.scalar_one_or_none() is None:
                raise CatalogNotReady("active action catalog is not ready")

            result = await session.execute(
                self._base_select().where(
                    tool_catalog_entries.c.capability_id == capability,
                    tool_catalog_entries.c.profile_id == profile,
                )
            )
            row = result.mappings().one_or_none()

        if row is None:
            raise CatalogItemNotFound(f"action catalog item not found: {capability}/{profile}")
        return self._detail(row)

    async def find_detail_by_event(
        self,
        *,
        event: str,
        profile: str | None = None,
    ) -> CatalogDetail:
        async with self.session_factory() as session:
            snapshot = await session.execute(
                select(tool_catalog_snapshots.c.id).where(
                    tool_catalog_snapshots.c.deactivated_at.is_(None),
                    tool_catalog_snapshots.c.activated_at.is_not(None),
                )
            )
            if snapshot.scalar_one_or_none() is None:
                raise CatalogNotReady("active action catalog is not ready")

            query = self._base_select().where(tool_catalog_entries.c.request_event == event)
            if profile is None:
                query = query.where(
                    tool_catalog_entries.c.profile_id == tool_catalog_entries.c.default_profile
                )
            else:
                query = query.where(tool_catalog_entries.c.profile_id == profile)

            result = await session.execute(query)
            row = result.mappings().one_or_none()

        if row is None:
            if profile is None:
                raise CatalogItemNotFound(f"action catalog item not found for event: {event}")
            raise CatalogItemNotFound(
                f"action catalog item not found for event/profile: {event}/{profile}"
            )
        return self._detail(row)
