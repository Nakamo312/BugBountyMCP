"""Header repository"""
from api.infrastructure.database.models import HeaderModel
from api.domain.repositories import IHeaderRepository
from .base_repo import BaseRepository


class HeaderRepository(BaseRepository[HeaderModel], IHeaderRepository):
    """Repository for Header entities"""
    
    model = HeaderModel
    unique_fields = [("endpoint_id", "name")]
