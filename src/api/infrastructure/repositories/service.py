from typing import Optional
from uuid import UUID

from sqlalchemy import select
from api.infrastructure.database.models import ServiceModel
from api.infrastructure.repositories.base_repo import BaseRepository


class ServiceRepository(BaseRepository[ServiceModel]):
    """PostgreSQL implementation of Service repository"""

    model = ServiceModel
    unique_fields = [('ip_id', 'port')]

    async def get_or_create_with_tech(
        self,
        ip_id: UUID,
        scheme: str,
        port: int,
        technologies: Optional[dict] = None,
    ) -> ServiceModel:
        """
        Get existing service or create new one.
        If exists and has new technologies, merge them.
        """
        existing = await self.get_by_unique_fields(ip_id=ip_id, port=port)
        
        if existing:
            # Merge technologies if provided
            if technologies:
                current_tech = existing.technologies or {}
                # Merge dictionaries
                merged = {**current_tech, **technologies}
                if merged != current_tech:
                    existing.technologies = merged
                    await self.session.flush()
            return existing
        
        # Create new service
        service, _ = await self.get_or_create(
            ip_id=ip_id,
            port=port,
            defaults={
                'scheme': scheme,
                'technologies': technologies or {}
            }
        )
        return service

    async def add_technology(
        self, service_id: UUID, tech_name: str, tech_value: any
    ) -> ServiceModel:
        """Add a single technology to existing service"""
        service = await self.get_by_id(service_id)
        if not service:
            raise ValueError(f"Service {service_id} not found")
        
        technologies = service.technologies or {}
        technologies[tech_name] = tech_value
        service.technologies = technologies
        await self.session.flush()
        return service