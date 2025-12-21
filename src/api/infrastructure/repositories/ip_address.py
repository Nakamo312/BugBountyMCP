"""IP Address repository"""
from api.infrastructure.database.models import IPAddressModel
from api.domain.repositories import IIPAddressRepository
from .base_repo import BaseRepository


class IPAddressRepository(BaseRepository[IPAddressModel], IIPAddressRepository):
    """Repository for IPAddress entities"""
    
    model = IPAddressModel
    unique_fields = [("program_id", "address")]
