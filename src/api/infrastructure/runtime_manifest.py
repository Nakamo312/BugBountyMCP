"""Runtime manifest activation and lookup.

The pipeline YAML is an input manifest. PostgreSQL stores the active runtime
snapshot used by API catalog reads, action submission, and pipeline startup.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.capability_catalog import ToolCatalogSnapshot
from api.application.action_catalog import CatalogNotReady
from api.infrastructure.adapters.orm import tool_catalog_entries, tool_catalog_snapshots


@dataclass(frozen=True)
class ActivationResult:
    snapshot_id: uuid.UUID
    catalog_hash: str
    changed: bool
    entry_count: int


class ManifestActivator:
    """Activate a validated runtime manifest in PostgreSQL."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def activate(self, snapshot: ToolCatalogSnapshot) -> ActivationResult:
        """Make a manifest snapshot active, unless the same hash is already active."""
        async with self.session_factory() as session:
            existing = await session.execute(
                select(tool_catalog_snapshots.c.id).where(
                    tool_catalog_snapshots.c.catalog_hash == snapshot.catalog_hash,
                    tool_catalog_snapshots.c.deactivated_at.is_(None),
                    tool_catalog_snapshots.c.activated_at.is_not(None),
                )
            )
            existing_id = existing.scalar_one_or_none()
            if existing_id is not None:
                return ActivationResult(
                    snapshot_id=existing_id,
                    catalog_hash=snapshot.catalog_hash,
                    changed=False,
                    entry_count=len(snapshot.entries),
                )

            now = datetime.now(timezone.utc)
            snapshot_id = uuid.uuid4()
            await session.execute(
                update(tool_catalog_snapshots)
                .where(tool_catalog_snapshots.c.deactivated_at.is_(None))
                .values(deactivated_at=now)
            )
            await session.execute(
                update(tool_catalog_entries)
                .where(tool_catalog_entries.c.active.is_(True))
                .values(active=False)
            )
            await session.execute(
                insert(tool_catalog_snapshots).values(
                    id=snapshot_id,
                    catalog_hash=snapshot.catalog_hash,
                    source_hash=snapshot.source_hash,
                    source_path=snapshot.source_path,
                    manifest_json=snapshot.manifest_json,
                    schema_version=snapshot.schema_version,
                    created_at=now,
                    activated_at=now,
                )
            )
            for entry in snapshot.entries:
                await session.execute(
                    insert(tool_catalog_entries).values(
                        id=uuid.uuid4(),
                        snapshot_id=snapshot_id,
                        capability_id=entry.capability_id,
                        profile_id=entry.profile_id,
                        capability_label=entry.capability_label,
                        profile_label=entry.profile_label,
                        request_event=entry.request_event,
                        queue=entry.queue,
                        default_profile=entry.default_profile,
                        mode=entry.mode,
                        scope_policy=entry.scope_policy,
                        safety_class=entry.safety_class,
                        allowed_options=list(entry.allowed_options),
                        requires_approval=entry.requires_approval,
                        frontend=entry.frontend,
                        manifest_fragment=entry.manifest_fragment,
                        active=True,
                        created_at=now,
                    )
                )
            await session.commit()

        return ActivationResult(
            snapshot_id=snapshot_id,
            catalog_hash=snapshot.catalog_hash,
            changed=True,
            entry_count=len(snapshot.entries),
        )

    async def active_manifest(self) -> dict[str, Any]:
        """Return the active manifest JSON from PostgreSQL."""
        async with self.session_factory() as session:
            result = await session.execute(
                select(tool_catalog_snapshots.c.manifest_json).where(
                    tool_catalog_snapshots.c.deactivated_at.is_(None),
                    tool_catalog_snapshots.c.activated_at.is_not(None),
                )
            )
            manifest = result.scalar_one_or_none()
        if manifest is None:
            raise CatalogNotReady("active runtime manifest is not ready")
        return dict(manifest)
