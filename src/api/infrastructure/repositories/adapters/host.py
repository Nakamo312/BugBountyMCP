"""Host repository"""

from api.domain.models import HostModel
from api.infrastructure.repositories.adapters.sqlalchemy_repository import SQLAlchemyBaseRepository


class SQLAlchemyHostRepository(SQLAlchemyBaseRepository[HostModel]):
    """Repository for Host entities"""
    
    model = HostModel
    unique_fields = [("program_id", "host")]
