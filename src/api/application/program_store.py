"""Application boundary for program persistence use cases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from api.domain.models import ProgramModel, RootInputModel, ScopeRuleModel


@dataclass(frozen=True)
class ProgramRelations:
    program: ProgramModel
    scope_rules: list[ScopeRuleModel]
    root_inputs: list[RootInputModel]


class ProgramStore(Protocol):
    async def create_with_relations(
        self,
        program: ProgramModel,
        scope_rules: list[ScopeRuleModel],
        root_inputs: list[RootInputModel],
    ) -> ProgramRelations:
        raise NotImplementedError

    async def get_with_relations(self, program_id: UUID) -> ProgramRelations | None:
        raise NotImplementedError

    async def get(self, program_id: UUID) -> ProgramModel | None:
        raise NotImplementedError

    async def list_many(self, *, limit: int, offset: int) -> list[ProgramModel]:
        raise NotImplementedError

    async def update_with_relations(
        self,
        *,
        program_id: UUID,
        name: str | None,
        scope_rules: list[ScopeRuleModel] | None,
        root_inputs: list[RootInputModel] | None,
    ) -> ProgramRelations | None:
        raise NotImplementedError

    async def update_name(self, program_id: UUID, new_name: str) -> ProgramModel | None:
        raise NotImplementedError

    async def delete(self, program_id: UUID) -> bool:
        raise NotImplementedError

    async def add_scope_rule(
        self,
        program_id: UUID,
        scope_rule: ScopeRuleModel,
    ) -> ScopeRuleModel | None:
        raise NotImplementedError

    async def add_root_input(
        self,
        program_id: UUID,
        root_input: RootInputModel,
    ) -> RootInputModel | None:
        raise NotImplementedError
