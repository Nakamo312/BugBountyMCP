"""Public action catalog contracts."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.application.execution_limits import ExecutionBudget, ToolOptionSpec


class CatalogNotReady(RuntimeError):
    """Raised when PostgreSQL has no active catalog snapshot."""


class CatalogItemNotFound(LookupError):
    """Raised when an action catalog entry is missing or inactive."""


class CatalogItem(BaseModel):
    """Short action catalog item for selection lists."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    capability: str
    profile: str
    capability_label: str
    profile_label: str
    safety_level: str
    requires_approval: bool = False
    mode: str | None = None


class CatalogDetail(CatalogItem):
    """Full action helper for one catalog item."""

    snapshot_id: UUID
    queue: str
    request_event: str
    default_profile: str
    scope_policy: str
    allowed_options: list[str] = Field(default_factory=list)
    option_schema: dict[str, ToolOptionSpec] = Field(default_factory=dict)
    execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    frontend: dict[str, Any] = Field(default_factory=dict)
    submit: dict[str, Any] = Field(default_factory=dict)


class ActionCatalogStore(Protocol):
    """Read model for active action catalog entries."""

    async def list_items(self) -> list[CatalogItem]: ...

    async def get_detail(self, item_id: UUID) -> CatalogDetail: ...

    async def find_detail(self, *, capability: str, profile: str) -> CatalogDetail: ...

    async def find_detail_by_event(
        self,
        *,
        event: str,
        profile: str | None = None,
    ) -> CatalogDetail: ...
