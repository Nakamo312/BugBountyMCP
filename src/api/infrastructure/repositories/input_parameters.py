"""Input parameter repository"""
from api.infrastructure.database.models import InputParameterModel
from api.domain.repositories import IInputParameterRepository
from .base_repo import BaseRepository


class InputParameterRepository(BaseRepository[InputParameterModel], IInputParameterRepository):
    """Repository for InputParameter entities"""
    
    model = InputParameterModel
    unique_fields = [("endpoint_id", "location", "name")]
