from pydantic import BaseModel, ConfigDict
from typing import List
from uuid import UUID
from api.domain.models import RuleType, InputType, ScopeAction


class ScopeRuleCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_type: RuleType
    pattern: str
    action: ScopeAction = ScopeAction.INCLUDE


class ScopeRuleUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID | None = None
    rule_type: RuleType
    pattern: str
    action: ScopeAction = ScopeAction.INCLUDE


class RootInputCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    input_type: InputType


class RootInputUpdateDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: UUID | None = None
    value: str
    input_type: InputType


class ProgramCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    scope_rules: List[ScopeRuleCreateDTO] = []
    root_inputs: List[RootInputCreateDTO] = []


class ProgramResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str


class ScopeRuleResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    rule_type: RuleType
    pattern: str
    action: ScopeAction


class RootInputResponseDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    value: str
    input_type: InputType


class ProgramFullResponseDTO(BaseModel):
    program: ProgramResponseDTO
    scope_rules: List[ScopeRuleResponseDTO]
    root_inputs: List[RootInputResponseDTO]


class ProgramUpdateDTO(BaseModel):
    """DTO for updating program - all fields optional"""
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    scope_rules: List[ScopeRuleUpdateDTO] | None = None
    root_inputs: List[RootInputUpdateDTO] | None = None