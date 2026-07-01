# api/application/services/program_service.py
from typing import List, Optional
from uuid import UUID, uuid4
from xml.dom import NotFoundErr

from api.application.dto.program import (ProgramCreateDTO,
                                         ProgramFullResponseDTO,
                                         ProgramResponseDTO,
                                         ProgramUpdateDTO,
                                         RootInputResponseDTO,
                                         ScopeRuleResponseDTO)
from api.application.program_store import ProgramRelations, ProgramStore
from api.domain.models import ProgramModel, RootInputModel, ScopeRuleModel


class ProgramService:
    def __init__(self, store: ProgramStore):
        self._store = store

    async def create_program(self, dto: ProgramCreateDTO) -> ProgramFullResponseDTO:
        program = ProgramModel(id=uuid4(), name=dto.name)
        relations = await self._store.create_with_relations(
            program=program,
            scope_rules=_scope_rule_models(program.id, dto.scope_rules),
            root_inputs=_root_input_models(program.id, dto.root_inputs),
        )
        return _program_full_response(relations)

    async def get_program_with_relations(self, program_id: UUID) -> ProgramFullResponseDTO:
        relations = await self._store.get_with_relations(program_id)
        if not relations:
            raise NotFoundErr(f"Program {program_id} not found")
        return _program_full_response(relations)

    async def get_program(self, program_id: UUID) -> Optional[ProgramResponseDTO]:
        program = await self._store.get(program_id)
        return _program_response(program) if program else None

    async def list_programs(self, limit: int = 100, offset: int = 0) -> List[ProgramResponseDTO]:
        return [
            _program_response(program)
            for program in await self._store.list_many(limit=limit, offset=offset)
        ]

    async def update_program(self, program_id: UUID, dto: ProgramUpdateDTO) -> ProgramFullResponseDTO:
        relations = await self._store.update_with_relations(
            program_id=program_id,
            name=dto.name,
            scope_rules=(
                _scope_rule_models(program_id, dto.scope_rules)
                if dto.scope_rules is not None
                else None
            ),
            root_inputs=(
                _root_input_models(program_id, dto.root_inputs)
                if dto.root_inputs is not None
                else None
            ),
        )
        if not relations:
            raise NotFoundErr(f"Program {program_id} not found")
        return _program_full_response(relations)

    async def update_program_name(self, program_id: UUID, new_name: str) -> ProgramResponseDTO:
        program = await self._store.update_name(program_id, new_name)
        if not program:
            raise NotFoundErr(f"Program {program_id} not found")
        return _program_response(program)

    async def delete_program(self, program_id: UUID) -> None:
        deleted = await self._store.delete(program_id)
        if not deleted:
            raise NotFoundErr(f"Program {program_id} not found")

    async def add_scope_rule(self, program_id: UUID, rule_dto) -> ScopeRuleResponseDTO:
        rule = _scope_rule_models(program_id, [rule_dto])[0]
        created_rule = await self._store.add_scope_rule(program_id, rule)
        if not created_rule:
            raise NotFoundErr(f"Program {program_id} not found")
        return _scope_rule_response(created_rule)

    async def add_root_input(self, program_id: UUID, input_dto) -> RootInputResponseDTO:
        root_input = _root_input_models(program_id, [input_dto])[0]
        created_input = await self._store.add_root_input(program_id, root_input)
        if not created_input:
            raise NotFoundErr(f"Program {program_id} not found")
        return _root_input_response(created_input)


def _scope_rule_models(program_id: UUID, rule_dtos) -> list[ScopeRuleModel]:
    return [
        ScopeRuleModel(
            id=uuid4(),
            program_id=program_id,
            rule_type=rule_dto.rule_type,
            pattern=rule_dto.pattern,
            action=rule_dto.action,
        )
        for rule_dto in rule_dtos
    ]


def _root_input_models(program_id: UUID, input_dtos) -> list[RootInputModel]:
    return [
        RootInputModel(
            id=uuid4(),
            program_id=program_id,
            value=input_dto.value,
            input_type=input_dto.input_type,
        )
        for input_dto in input_dtos
    ]


def _program_full_response(relations: ProgramRelations) -> ProgramFullResponseDTO:
    return ProgramFullResponseDTO(
        program=_program_response(relations.program),
        scope_rules=[_scope_rule_response(rule) for rule in relations.scope_rules],
        root_inputs=[_root_input_response(root_input) for root_input in relations.root_inputs],
    )


def _program_response(program: ProgramModel) -> ProgramResponseDTO:
    return ProgramResponseDTO(id=program.id, name=program.name)


def _scope_rule_response(rule: ScopeRuleModel) -> ScopeRuleResponseDTO:
    return ScopeRuleResponseDTO(
        id=rule.id,
        program_id=rule.program_id,
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        action=rule.action,
    )


def _root_input_response(root_input: RootInputModel) -> RootInputResponseDTO:
    return RootInputResponseDTO(
        id=root_input.id,
        program_id=root_input.program_id,
        value=root_input.value,
        input_type=root_input.input_type,
    )
