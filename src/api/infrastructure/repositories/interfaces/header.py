"""Header repository"""

from api.domain.models import HeaderModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository



class HeaderRepository(AbstractRepository[HeaderModel]):
    """Repository for Header entities"""
    
    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]
