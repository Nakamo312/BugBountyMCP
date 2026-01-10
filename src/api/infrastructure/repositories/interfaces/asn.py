"""ASN repository interface"""

from abc import ABC
from uuid import UUID

from api.domain.models import ASNModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class ASNRepository(AbstractRepository[ASNModel], ABC):
    """Repository for ASN entities"""

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
        raise NotImplementedError
