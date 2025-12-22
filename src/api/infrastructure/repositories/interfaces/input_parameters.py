"""Input parameter repository"""
from api.domain.models import InputParameterModel
from api.infrastructure.repositories.interfaces.repository import AbstractRepository



class InputParameterRepository(AbstractRepository[InputParameterModel]):
    """Repository for InputParameter entities"""
    
    model = InputParameterModel
    unique_fields = [("endpoint_id", "location", "name")]
