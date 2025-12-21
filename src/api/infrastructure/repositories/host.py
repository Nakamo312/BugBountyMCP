"""Host repository"""
from api.infrastructure.database.models import HostModel
from .base_repo import BaseRepository


class HostRepository(BaseRepository[HostModel]):
    """Repository for Host entities"""
    
    model = HostModel
    unique_fields = [("program_id", "host")]
