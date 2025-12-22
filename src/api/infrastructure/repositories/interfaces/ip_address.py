"""IP Address repository"""
from api.domain.models import IPAddressModel
from api.infrastructure.repositories.interfaces.repository import \
    AbstractRepository


class IPAddressRepository(AbstractRepository[IPAddressModel]):
    """Repository for IPAddress entities"""
    
    model = IPAddressModel
    unique_fields = [("program_id", "address")]
