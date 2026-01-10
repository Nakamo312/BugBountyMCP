"""CIDR repository interface"""

from abc import ABC
from uuid import UUID

from api.domain.models import CIDRModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class CIDRRepository(AbstractRepository[CIDRModel], ABC):
    """Repository for CIDR entities"""

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
        raise NotImplementedError
