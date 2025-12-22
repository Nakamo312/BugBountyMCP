"""Host repository"""

from api.domain.models import HostModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.host import HostRepository



class SQLAlchemyHostRepository(SQLAlchemyAbstractRepository, HostRepository):
    """Repository for Host entities"""
    
    model = HostModel
    unique_fields = [("program_id", "host")]
