"""Organization repository interface"""

from abc import ABC
from uuid import UUID

from api.domain.models import OrganizationModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class OrganizationRepository(AbstractRepository[OrganizationModel], ABC):
    """Repository for Organization entities"""

    async def ensure(
        self,
        program_id: UUID,
        name: str,
        metadata: dict | None = None,
    ) -> OrganizationModel:
        """Get or create organization"""
        raise NotImplementedError
