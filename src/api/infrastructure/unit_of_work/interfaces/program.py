from abc import ABC

from api.infrastructure.repositories.interfaces.program import \
    ProgramRepository
from api.infrastructure.repositories.interfaces.root_input import \
    RootInputRepository
from api.infrastructure.repositories.interfaces.scope_rule import \
    ScopeRuleRepository
from api.infrastructure.unit_of_work.interfaces.base import AbstractUnitOfWork


class ProgramUnitOfWork(AbstractUnitOfWork, ABC):
    programs: ProgramRepository
    scope_rules: ScopeRuleRepository
    root_inputs: RootInputRepository