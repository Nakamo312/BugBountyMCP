"""Organization repository implementation"""

from uuid import UUID

from api.domain.models import OrganizationModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.organization import OrganizationRepository


class SQLAlchemyOrganizationRepository(SQLAlchemyAbstractRepository, OrganizationRepository):
    """SQLAlchemy implementation of Organization repository"""

    model = OrganizationModel

    async def ensure(
        self,
        program_id: UUID,
        name: str,
        metadata: dict | None = None,
    ) -> OrganizationModel:
        """Get or create organization"""
        entity = OrganizationModel(
            program_id=program_id,
            name=name,
            metadata=metadata or {}
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "name"],
            update_fields=["metadata"]
        )
