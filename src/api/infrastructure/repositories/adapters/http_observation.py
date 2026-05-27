"""HTTP observation repository adapters."""

from typing import Any
from uuid import UUID

from sqlalchemy import select

from api.domain.models import HTTPObservationHeaderModel, HTTPObservationModel
from api.infrastructure.repositories.adapters.base import SQLAlchemyAbstractRepository
from api.infrastructure.repositories.interfaces.http_observation import (
    HTTPObservationHeaderRepository,
    HTTPObservationRepository,
)


class SQLAlchemyHTTPObservationRepository(
    SQLAlchemyAbstractRepository,
    HTTPObservationRepository,
):
    """SQLAlchemy implementation for append-only HTTP observations."""

    model = HTTPObservationModel

    async def create_with_headers(
        self,
        observation: HTTPObservationModel,
        headers: list[dict[str, Any]] | None = None,
    ) -> HTTPObservationModel:
        created = await self.create(observation)
        for ordinal, header in enumerate(headers or []):
            name = str(header.get("name") or "").strip().lower()
            if not name:
                continue
            value = "" if header.get("value") is None else str(header.get("value"))
            self.session.add(
                HTTPObservationHeaderModel(
                    observation_id=created.id,
                    name=name,
                    value=value,
                    ordinal=ordinal,
                )
            )
        await self.session.flush()
        return created

    async def find_by_endpoint(
        self,
        endpoint_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HTTPObservationModel]:
        query = (
            select(HTTPObservationModel)
            .where(HTTPObservationModel.endpoint_id == endpoint_id)
            .order_by(HTTPObservationModel.observed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class SQLAlchemyHTTPObservationHeaderRepository(
    SQLAlchemyAbstractRepository,
    HTTPObservationHeaderRepository,
):
    """SQLAlchemy implementation for observation headers."""

    model = HTTPObservationHeaderModel

    async def find_by_observation(
        self,
        observation_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HTTPObservationHeaderModel]:
        query = (
            select(HTTPObservationHeaderModel)
            .where(HTTPObservationHeaderModel.observation_id == observation_id)
            .order_by(HTTPObservationHeaderModel.ordinal)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
