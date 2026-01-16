"""Raw body repository"""

from api.domain.models import RawBodyModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class RawBodyRepository(AbstractRepository[RawBodyModel]):
    """Repository for raw HTTP request bodies"""

    model = RawBodyModel
    unique_fields = []
