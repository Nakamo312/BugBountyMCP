"""Finding repository interface"""

from abc import ABC
from typing import List, Optional
from uuid import UUID

from api.domain.models import FindingModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class FindingRepository(AbstractRepository[FindingModel], ABC):
    """Repository interface for FindingModel"""
    
    async def find_by_program(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        verified: Optional[bool] = None,
        false_positive: Optional[bool] = None
    ) -> List[FindingModel]:
        """Find findings by program with optional filters"""
        raise NotImplementedError
    
    async def find_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by host"""
        raise NotImplementedError
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by endpoint"""
        raise NotImplementedError
    
    async def find_by_vuln_type(
        self,
        vuln_type_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by vulnerability type"""
        raise NotImplementedError
