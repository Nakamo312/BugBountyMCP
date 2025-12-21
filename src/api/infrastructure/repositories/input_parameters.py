"""Input parameter repository"""
from api.infrastructure.database.models import InputParameterModel
from .base_repo import BaseRepository


class InputParameterRepository(BaseRepository[InputParameterModel]):
    """Repository for InputParameter entities"""
    
    model = InputParameterModel
    unique_fields = [("endpoint_id", "location", "name")]
