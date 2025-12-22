"""Input parameter repository"""
from api.domain.models import InputParameterModel
from api.infrastructure.repositories.adapters.sqlalchemy_repository import \
    SQLAlchemyBaseRepository


class SQLAlchemyInputParameterRepository(SQLAlchemyBaseRepository[InputParameterModel]):
    """Repository for InputParameter entities"""
    
    model = InputParameterModel
    unique_fields = [("endpoint_id", "location", "name")]
