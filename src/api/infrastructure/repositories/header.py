"""Header repository"""
from api.infrastructure.database.models import HeaderModel
from .base_repo import BaseRepository


class HeaderRepository(BaseRepository[HeaderModel]):
    """Repository for Header entities"""
    
    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]
