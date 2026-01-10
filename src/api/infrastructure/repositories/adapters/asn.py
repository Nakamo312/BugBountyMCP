"""ASN repository implementation"""

from uuid import UUID

from api.domain.models import ASNModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.asn import ASNRepository


class SQLAlchemyASNRepository(SQLAlchemyAbstractRepository, ASNRepository):
    """SQLAlchemy implementation of ASN repository"""

    model = ASNModel

    async def ensure(
        self,
        program_id: UUID,
        asn_number: int,
        organization_name: str,
        country_code: str | None = None,
        description: str | None = None,
        organization_id: UUID | None = None,
    ) -> ASNModel:
        """Get or create ASN"""
        entity = ASNModel(
            program_id=program_id,
            asn_number=asn_number,
            organization_name=organization_name,
            country_code=country_code,
            description=description,
            organization_id=organization_id
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "asn_number"],
            update_fields=["organization_name", "country_code", "description", "organization_id"]
        )
