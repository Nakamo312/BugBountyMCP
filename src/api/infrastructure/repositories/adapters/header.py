"""Header repository"""

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository



class SQLAlchemyHeaderRepository(SQLAlchemyAbstractRepository, AbstractRepository[HeaderModel]):
    """Repository for Header entities"""
    
    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]
