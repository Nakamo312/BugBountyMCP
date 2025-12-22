"""Header repository"""

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.repository import AbstractRepository
from api.infrastructure.database.repositories import SQLAlchemyAbstractRepository



class SQLAlchemyHeaderRepository(SQLAlchemyAbstractRepository, AbstractRepository[HeaderModel]):
    """Repository for Header entities"""
    
    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]
