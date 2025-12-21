"""IP Address repository"""
from api.infrastructure.database.models import IPAddressModel
from .base_repo import BaseRepository


class IPAddressRepository(BaseRepository[IPAddressModel]):
    """Repository for IPAddress entities"""
    
    model = IPAddressModel
    unique_fields = [("program_id", "address")]
