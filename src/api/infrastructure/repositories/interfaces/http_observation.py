"""HTTP observation repository contracts."""

from abc import ABC
from typing import Any
from uuid import UUID

from api.domain.models import HTTPObservationHeaderModel, HTTPObservationModel
from api.infrastructure.repositories.interfaces.base import AbstractRepository


class HTTPObservationRepository(AbstractRepository[HTTPObservationModel], ABC):
    """Repository for HTTP response observations."""

    async def create_with_headers(
        self,
        observation: HTTPObservationModel,
        headers: list[dict[str, Any]] | None = None,
    ) -> HTTPObservationModel:
        """Create one observation and its observed headers."""
        raise NotImplementedError

    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HTTPObservationModel]:
        """Find observations for an endpoint."""
        raise NotImplementedError


class HTTPObservationHeaderRepository(AbstractRepository[HTTPObservationHeaderModel], ABC):
    """Repository for headers attached to HTTP observations."""

    async def find_by_observation(
        self,
        observation_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HTTPObservationHeaderModel]:
        """Find headers for an observation."""
        raise NotImplementedError
