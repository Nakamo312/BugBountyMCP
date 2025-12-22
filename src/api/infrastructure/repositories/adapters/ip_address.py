"""IP Address repository"""
from api.domain.models import IPAddressModel, ProgramModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.ip_address import IPAddressRepository


class SQLAlchemyIPAddressRepository(SQLAlchemyAbstractRepository, IPAddressRepository):
    """Repository for IPAddress entities"""
    
    model = IPAddressModel
    unique_fields = [("program_id", "address")]
