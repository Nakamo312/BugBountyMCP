"""Scope filtering port consumed by pipeline context."""
from __future__ import annotations

from typing import Protocol
from uuid import UUID

from api.application.pipeline.scope_policy import ScopePolicy


class ScopeFilterPort(Protocol):
    async def filter_by_scope(
        self,
        *,
        program_id: UUID,
        targets: list[str],
        policy: ScopePolicy,
    ) -> tuple[list[str], list[str]]:
        ...
