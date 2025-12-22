"""Host repository"""

from uuid import UUID

from api.domain.models import HostModel
from api.infrastructure.repositories.interfaces.repository import \
    AbstractRepository


class HostRepository(AbstractRepository[HostModel]):
    """Repository for Host entities"""
    
    model = HostModel
    unique_fields = [("program_id", "host")]