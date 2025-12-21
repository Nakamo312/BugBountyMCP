"""Program repository"""
from api.infrastructure.database.models import ProgramModel
from .base_repo import BaseRepository


class ProgramRepository(BaseRepository[ProgramModel]):
    """Repository for Program entities"""
    
    model = ProgramModel
    unique_fields = [("name",)]
