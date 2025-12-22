# api/infrastructure/repositories/interfaces/scope_rule.py
from abc import ABC, abstractmethod
from typing import List
from uuid import UUID

from api.domain.models import ScopeRuleModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class ScopeRuleRepository(AbstractRepository[ScopeRuleModel], ABC):
    @abstractmethod
    async def find_by_program(self, program_id: UUID) -> List[ScopeRuleModel]:
        raise NotImplementedError