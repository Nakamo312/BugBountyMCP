"""Finding repository implementation"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, select

from api.domain.models import FindingModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.finding import FindingRepository


class SQLAlchemyFindingRepository(SQLAlchemyAbstractRepository, FindingRepository):
    """SQLAlchemy implementation of FindingRepository"""
    
    model = FindingModel
    
    async def find_by_program(
        self,
        program_id: UUID,
        limit: int = 100,
        offset: int = 0,
        verified: Optional[bool] = None,
        false_positive: Optional[bool] = None
    ) -> List[FindingModel]:
        """Find findings by program with optional filters"""
        conditions = [FindingModel.program_id == program_id]
        
        if verified is not None:
            conditions.append(FindingModel.verified == verified)
        
        if false_positive is not None:
            conditions.append(FindingModel.false_positive == false_positive)
        
        query = select(FindingModel).where(and_(*conditions))
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_host(
        self,
        host_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by host"""
        query = select(FindingModel).where(
            FindingModel.host_id == host_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by endpoint"""
        query = select(FindingModel).where(
            FindingModel.endpoint_id == endpoint_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def find_by_vuln_type(
        self,
        vuln_type_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[FindingModel]:
        """Find findings by vulnerability type"""
        query = select(FindingModel).where(
            FindingModel.vuln_type_id == vuln_type_id
        ).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
