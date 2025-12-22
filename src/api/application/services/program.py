# api/application/services/program_service.py
from typing import List, Optional
from uuid import UUID, uuid4
from xml.dom import NotFoundErr

from api.application.dto.program import (ProgramCreateDTO,
                                         ProgramFullResponseDTO,
                                         ProgramResponseDTO,
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
                    pattern=rule_dto.pattern
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
            
            return ProgramFullResponseDTO(
                program=ProgramResponseDTO(
                    id=created_program.id,
                    name=created_program.name
                ),
                scope_rules=[
                    ScopeRuleResponseDTO(
                        id=rule.id,
                        program_id=rule.program_id,
                        rule_type=rule.rule_type,
                        pattern=rule.pattern
                    ) for rule in scope_rules
                ],
                root_inputs=[
                    RootInputResponseDTO(
                        id=input.id,
                        program_id=input.program_id,
                        value=input.value,
                        input_type=input.input_type
                    ) for input in root_inputs
                ]
            )
    
    async def get_program_with_relations(self, program_id: UUID) -> ProgramFullResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            scope_rules = await uow.scope_rules.find_by_program(program_id)
            root_inputs = await uow.root_inputs.find_by_program(program_id)
            
            return ProgramFullResponseDTO(
                program=ProgramResponseDTO(
                    id=program.id,
                    name=program.name
                ),
                scope_rules=[
                    ScopeRuleResponseDTO(
                        id=rule.id,
                        program_id=rule.program_id,
                        rule_type=rule.rule_type,
                        pattern=rule.pattern
                    ) for rule in scope_rules
                ],
                root_inputs=[
                    RootInputResponseDTO(
                        id=input.id,
                        program_id=input.program_id,
                        value=input.value,
                        input_type=input.input_type
                    ) for input in root_inputs
                ]
            )
    
    async def get_program(self, program_id: UUID) -> Optional[ProgramResponseDTO]:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                return None
            
            return ProgramResponseDTO(
                id=program.id,
                name=program.name
            )
    
    async def list_programs(self, limit: int = 100, offset: int = 0) -> List[ProgramResponseDTO]:
        async with self.uow as uow:
            programs = await uow.programs.find_many(limit=limit, offset=offset)
            
            return [
                ProgramResponseDTO(
                    id=program.id,
                    name=program.name
                ) for program in programs
            ]
    
    async def update_program_name(self, program_id: UUID, new_name: str) -> ProgramResponseDTO:
        async with self.uow as uow:
            program = await uow.programs.get(program_id)
            if not program:
                raise NotFoundErr(f"Program {program_id} not found")
            
            updated_program = program.copy(update={"name": new_name})
            result = await uow.programs.update(program_id, updated_program)
            
            await uow.commit()
            
            return ProgramResponseDTO(
                id=result.id,
                name=result.name
            )
    
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
                pattern=rule_dto.pattern
            )
            created_rule = await uow.scope_rules.create(rule)
            
            await uow.commit()
            
            return ScopeRuleResponseDTO(
                id=created_rule.id,
                program_id=created_rule.program_id,
                rule_type=created_rule.rule_type,
                pattern=created_rule.pattern
            )
    
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
            
            return RootInputResponseDTO(
                id=created_input.id,
                program_id=created_input.program_id,
                value=created_input.value,
                input_type=created_input.input_type
            )