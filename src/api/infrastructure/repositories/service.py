"""Service repository"""
from typing import Dict
from uuid import UUID
from api.infrastructure.database.models import ServiceModel
from api.domain.repositories import IServiceRepository
from .base_repo import BaseRepository


class ServiceRepository(BaseRepository[ServiceModel], IServiceRepository):
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
        # Validate port
        port = max(1, min(int(port), 65535))
        
        # Try to find existing service
        existing = await self.get_by_fields(ip_id=ip_id, scheme=scheme, port=port)
        
        if existing:
            # Merge technologies
            merged_tech = {**(existing.technologies or {}), **technologies}
            return await self.update(existing.id, {"technologies": merged_tech})
        
        # Create new service
        return await self.create({
            "ip_id": ip_id,
            "scheme": scheme,
            "port": port,
            "technologies": technologies
        })
