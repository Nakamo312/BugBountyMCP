from typing import Optional
from uuid import UUID

from api.domain.models import EndpointModel
from api.infrastructure.repositories.interfaces.repository import \
    AbstractRepository


class EndpointRepository(AbstractRepository[EndpointModel]):
    """Repository for Endpoint entities"""
    
    model = EndpointModel
    unique_fields = [("host_id", "service_id", "normalized_path")]
    
    async def upsert_with_method(
            self,
            host_id: UUID,
            service_id: UUID,
            path: str,
            method: str,
            normalized_path: str,
            status_code: Optional[int] = None,
            **kwargs
        ) -> EndpointModel:
        raise NotImplementedError
