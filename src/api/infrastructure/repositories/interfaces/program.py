"""Program repository"""

from api.infrastructure.repositories.interfaces.repository import AbstractRepository
from api.domain.models import ProgramModel



class ProgramRepository(AbstractRepository[ProgramModel]):
    """Repository for Program entities"""
    
    model = ProgramModel
    unique_fields = [("name",)]
