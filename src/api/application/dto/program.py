from pydantic import BaseModel, ConfigDict
from typing import List
from uuid import UUID
from api.domain.models import RuleType, InputType


class ScopeRuleCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_type: RuleType
    pattern: str


class RootInputCreateDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")
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