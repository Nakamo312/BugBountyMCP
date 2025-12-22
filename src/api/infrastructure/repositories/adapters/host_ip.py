"""Host-IP mapping repository"""
from uuid import UUID

from api.domain.models import HostIPModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.host_ip import HostIPRepository



class SQLAlchemyHostIPRepository(SQLAlchemyAbstractRepository, HostIPRepository):
    """Repository for HostIP mapping entities"""
    
    model = HostIPModel
    unique_fields = [("host_id", "ip_id")]
    
    async def link(self, host_id: UUID, ip_id: UUID, source: str) -> HostIPModel:
        """
        Create or update host-IP link.
        
        Args:
            host_id: Host entity ID
            ip_id: IP address entity ID
            source: Tool/source that discovered this link
            
        Returns:
            HostIP mapping entity
        """
        return await self.upsert(
            data={
                "host_id": host_id,
                "ip_id": ip_id,
                "source": source
            },
            conflict_fields=["host_id", "ip_id"],
            update_fields=["source"]
        )
