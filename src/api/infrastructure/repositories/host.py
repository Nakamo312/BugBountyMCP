"""Host repository"""
from api.infrastructure.database.models import HostModel
from api.domain.repositories import IHostRepository
from .base_repo import BaseRepository


class HostRepository(BaseRepository[HostModel], IHostRepository):
    """Repository for Host entities"""
    
    model = HostModel
    unique_fields = [("program_id", "host")]
