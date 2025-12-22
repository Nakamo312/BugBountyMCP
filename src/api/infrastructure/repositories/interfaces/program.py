"""Program repository"""

from api.domain.models import ProgramModel
from api.infrastructure.repositories.interfaces.repository import \
    AbstractRepository


class ProgramRepository(AbstractRepository[ProgramModel]):
    """Repository for Program entities"""
    
    model = ProgramModel
    unique_fields = [("name",)]
