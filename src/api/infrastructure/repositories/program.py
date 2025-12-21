"""Program repository"""
from api.infrastructure.database.models import ProgramModel
from api.domain.repositories import IProgramRepository
from .base_repo import BaseRepository


class ProgramRepository(BaseRepository[ProgramModel], IProgramRepository):
    """Repository for Program entities"""
    
    model = ProgramModel
    unique_fields = [("name",)]
