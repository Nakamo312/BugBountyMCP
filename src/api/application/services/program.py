# api/application/services/program_service.py
from dataclasses import replace
from typing import List, Optional
from uuid import UUID, uuid4
from xml.dom import NotFoundErr

from api.application.dto.program import (ProgramCreateDTO,
                                         ProgramFullResponseDTO,
                                         ProgramResponseDTO,
                                         ProgramUpdateDTO,
                                         RootInputResponseDTO,
                                         ScopeRuleResponseDTO)
from api.domain.models import ProgramModel, RootInputModel, ScopeRuleModel
from api.infrastructure.unit_of_work.interfaces.program import \
    ProgramUnitOfWork


class ProgramService:
    def __init__(self, uow: ProgramUnitOfWork):
        self.uow = uow
    
    async def create_program(self, dto: ProgramCreateDTO) -> ProgramFullResponseDTO:
        async with self.uow as uow:
            program = ProgramModel(id=uuid4(), name=dto.name)
            created_program = await uow.programs.create(program)
            
            scope_rules = []
            for rule_dto in dto.scope_rules:
                rule = ScopeRuleModel(
                    id=uuid4(),
                    program_id=created_program.id,
                    rule_type=rule_dto.rule_type,
                    pattern=rule_dto.pattern,
                    action=rule_dto.action
                )
                created_rule = await uow.scope_rules.create(rule)
                scope_rules.append(created_rule)
            
            root_inputs = []
            for input_dto in dto.root_inputs:
                root_input = RootInputModel(
                    id=uuid4(),
                    program_id=created_program.id,
                    value=input_dto.value,
                    input_type=input_dto.input_type
                )
                created_input = await uow.root_inputs.create(root_input)
                root_inputs.append(created_input)
            
            await uow.commit()
            
            return _program_full_response(created_program, scope_rules, root_inputs)
    
    async def get_program_with_relations(self, program_id: UUID) -> ProgramFullResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            scope_rules = await uow.scope_rules.find_by_program(program_id)
            root_inputs = await uow.root_inputs.find_by_program(program_id)
            
            return _program_full_response(program, scope_rules, root_inputs)
    
    async def get_program(self, program_id: UUID) -> Optional[ProgramResponseDTO]:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            
            return _program_response(program)
    
    async def list_programs(self, limit: int = 100, offset: int = 0) -> List[ProgramResponseDTO]:
        async with self.uow as uow:
            programs = await uow.programs.find_many(limit=limit, offset=offset)
            
            return [
                _program_response(program) for program in programs
            ]
    
    async def update_program(self, program_id: UUID, dto: ProgramUpdateDTO) -> ProgramFullResponseDTO:
        """
        Update program with optional fields.

        Args:
            program_id: Program UUID
            dto: Update DTO with optional name, scope_rules, root_inputs

        Returns:
            Updated program with all relations
        """
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")

            if dto.name is not None:
                updated_program = replace(program, name=dto.name)
                program = await uow.programs.update(program_id, updated_program)

            if dto.scope_rules is not None:
                await uow.scope_rules.delete_by_program(program_id)

                for rule_dto in dto.scope_rules:
                    rule = ScopeRuleModel(
                        id=uuid4(),
                        program_id=program_id,
                        rule_type=rule_dto.rule_type,
                        pattern=rule_dto.pattern,
                        action=rule_dto.action
                    )
                    await uow.scope_rules.create(rule)

            if dto.root_inputs is not None:
                await uow.root_inputs.delete_by_program(program_id)

                for input_dto in dto.root_inputs:
                    root_input = RootInputModel(
                        id=uuid4(),
                        program_id=program_id,
                        value=input_dto.value,
                        input_type=input_dto.input_type
                    )
                    await uow.root_inputs.create(root_input)

            await uow.commit()

            scope_rules = await uow.scope_rules.find_by_program(program_id)
            root_inputs = await uow.root_inputs.find_by_program(program_id)

            return _program_full_response(program, scope_rules, root_inputs)

    async def update_program_name(self, program_id: UUID, new_name: str) -> ProgramResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")

            updated_program = replace(program, name=new_name)
            result = await uow.programs.update(program_id, updated_program)

            await uow.commit()

            return _program_response(result)
    
    async def delete_program(self, program_id: UUID) -> None:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            await uow.scope_rules.delete_by_program(program_id)
            await uow.root_inputs.delete_by_program(program_id)
            await uow.programs.delete(program_id)
            
            await uow.commit()
    
    async def add_scope_rule(self, program_id: UUID, rule_dto) -> ScopeRuleResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            rule = ScopeRuleModel(
                id=uuid4(),
                program_id=program_id,
                rule_type=rule_dto.rule_type,
                pattern=rule_dto.pattern,
                action=rule_dto.action
            )
            created_rule = await uow.scope_rules.create(rule)

            await uow.commit()

            return _scope_rule_response(created_rule)
    
    async def add_root_input(self, program_id: UUID, input_dto) -> RootInputResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            root_input = RootInputModel(
                id=uuid4(),
                program_id=program_id,
                value=input_dto.value,
                input_type=input_dto.input_type
            )
            created_input = await uow.root_inputs.create(root_input)
            
            await uow.commit()
            
            return _root_input_response(created_input)


def _program_full_response(
    program: ProgramModel,
    scope_rules: list[ScopeRuleModel],
    root_inputs: list[RootInputModel],
) -> ProgramFullResponseDTO:
    return ProgramFullResponseDTO(
        program=_program_response(program),
        scope_rules=[_scope_rule_response(rule) for rule in scope_rules],
        root_inputs=[_root_input_response(root_input) for root_input in root_inputs],
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
