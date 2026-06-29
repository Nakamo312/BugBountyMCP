"""JavaScript reference repository contracts."""

from abc import ABC

from api.domain.models import JavaScriptReferenceModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class JavaScriptReferenceRepository(AbstractRepository[JavaScriptReferenceModel], ABC):
    """Repository for endpoint references extracted from JavaScript."""
