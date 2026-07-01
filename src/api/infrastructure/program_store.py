"""Program persistence adapter backed by existing repositories."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.program_store import ProgramRelations, ProgramStore
from api.domain.models import ProgramModel, RootInputModel, ScopeRuleModel
from api.infrastructure.unit_of_work.adapters.program import SQLAlchemyProgramUnitOfWork


class RepositoryProgramStore(ProgramStore):
    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def create_with_relations(
        self,
        program: ProgramModel,
        scope_rules: list[ScopeRuleModel],
        root_inputs: list[RootInputModel],
    ) -> ProgramRelations:
        async with self._uow() as uow:
            created_program = await uow.programs.create(program)
            created_rules = [
                await uow.scope_rules.create(rule) for rule in scope_rules
            ]
            created_inputs = [
                await uow.root_inputs.create(root_input) for root_input in root_inputs
            ]
            await uow.commit()
            return ProgramRelations(created_program, created_rules, created_inputs)

    async def get_with_relations(self, program_id: UUID) -> ProgramRelations | None:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            return ProgramRelations(
                program=program,
                scope_rules=await uow.scope_rules.find_by_program(program_id),
                root_inputs=await uow.root_inputs.find_by_program(program_id),
            )

    async def get(self, program_id: UUID) -> ProgramModel | None:
        async with self._uow() as uow:
            return await uow.programs.get(program_id)

    async def list_many(self, *, limit: int, offset: int) -> list[ProgramModel]:
        async with self._uow() as uow:
            return await uow.programs.find_many(limit=limit, offset=offset)

    async def update_with_relations(
        self,
        *,
        program_id: UUID,
        name: str | None,
        scope_rules: list[ScopeRuleModel] | None,
        root_inputs: list[RootInputModel] | None,
    ) -> ProgramRelations | None:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None

            if name is not None:
                program = await uow.programs.update(
                    program_id,
                    replace(program, name=name),
                )

            if scope_rules is not None:
                await uow.scope_rules.delete_by_program(program_id)
                for rule in scope_rules:
                    await uow.scope_rules.create(rule)

            if root_inputs is not None:
                await uow.root_inputs.delete_by_program(program_id)
                for root_input in root_inputs:
                    await uow.root_inputs.create(root_input)

            await uow.commit()
            return ProgramRelations(
                program=program,
                scope_rules=await uow.scope_rules.find_by_program(program_id),
                root_inputs=await uow.root_inputs.find_by_program(program_id),
            )

    async def update_name(self, program_id: UUID, new_name: str) -> ProgramModel | None:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            result = await uow.programs.update(program_id, replace(program, name=new_name))
            await uow.commit()
            return result

    async def delete(self, program_id: UUID) -> bool:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return False
            await uow.scope_rules.delete_by_program(program_id)
            await uow.root_inputs.delete_by_program(program_id)
            await uow.programs.delete(program_id)
            await uow.commit()
            return True

    async def add_scope_rule(
        self,
        program_id: UUID,
        scope_rule: ScopeRuleModel,
    ) -> ScopeRuleModel | None:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            created_rule = await uow.scope_rules.create(scope_rule)
            await uow.commit()
            return created_rule

    async def add_root_input(
        self,
        program_id: UUID,
        root_input: RootInputModel,
    ) -> RootInputModel | None:
        async with self._uow() as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            created_input = await uow.root_inputs.create(root_input)
            await uow.commit()
            return created_input

    def _uow(self) -> SQLAlchemyProgramUnitOfWork:
        return SQLAlchemyProgramUnitOfWork(self._session_factory)
