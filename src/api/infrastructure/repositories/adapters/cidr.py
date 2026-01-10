"""CIDR repository implementation"""

from uuid import UUID

from api.domain.models import CIDRModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.cidr import CIDRRepository


class SQLAlchemyCIDRRepository(SQLAlchemyAbstractRepository, CIDRRepository):
    """SQLAlchemy implementation of CIDR repository"""

    model = CIDRModel

    async def ensure(
        self,
        program_id: UUID,
        cidr: str,
        asn_id: UUID | None = None,
        ip_count: int | None = None,
        expanded: bool = False,
        in_scope: bool = True,
    ) -> CIDRModel:
        """Get or create CIDR"""
        entity = CIDRModel(
            program_id=program_id,
            cidr=cidr,
            asn_id=asn_id,
            ip_count=ip_count,
            expanded=expanded,
            in_scope=in_scope
        )

        return await self.upsert(
            entity,
            conflict_fields=["program_id", "cidr"],
            update_fields=["asn_id", "ip_count", "expanded", "in_scope"]
        )
