"""Input parameter repository"""
from api.domain.models import InputParameterModel
from api.infrastructure.repositories.adapters.host import SQLAlchemyHostRepository
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.input_parameters import InputParameterRepository



class SQLAlchemyInputParameterRepository(SQLAlchemyAbstractRepository, InputParameterRepository):
    """Repository for InputParameter entities"""
    
    model = InputParameterModel
    unique_fields = [("endpoint_id", "location", "name")]
