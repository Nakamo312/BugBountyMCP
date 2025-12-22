"""Service repository"""
from typing import Dict
from uuid import UUID

from api.domain.models import ServiceModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.service import ServiceRepository


class SQLAlchemyServiceRepository(SQLAlchemyAbstractRepository, ServiceRepository):
    """Repository for Service entities"""
    
    model = ServiceModel
    unique_fields = [("ip_id", "scheme", "port")]
    
    async def get_or_create_with_tech(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Dict[str, bool]
    ) -> ServiceModel:
        """
        Get or create service and merge technologies.
        
        Args:
            ip_id: IP address ID
            scheme: http or https
            port: Port number (1-65535)
            technologies: Dict of technology names and their presence
            
        Returns:
            Service entity with merged technologies
        """
        port = max(1, min(int(port), 65535))
        
        existing = await self.get_by_fields(ip_id=ip_id, scheme=scheme, port=port)
        
        if existing:
            merged_tech = {**(existing.technologies or {}), **technologies}
            return await self.update(existing.id, {"technologies": merged_tech})

        return await self.create({
            "ip_id": ip_id,
            "scheme": scheme,
            "port": port,
            "technologies": technologies
        })
