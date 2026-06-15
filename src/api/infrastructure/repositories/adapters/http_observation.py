"""HTTP observation repository adapters."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from api.domain.models import HTTPObservationHeaderModel, HTTPObservationModel
from api.infrastructure.adapters.orm import graph_projection_events
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
        await self._enqueue_graph_projection_event(created)
        await self.session.flush()
        return created

    async def _enqueue_graph_projection_event(
        self,
        observation: HTTPObservationModel,
    ) -> None:
        if observation.raw_artifact_id is None:
            return
        if observation.run_id is None:
            return

        dedupe_key = f"http-observations-ready:{observation.raw_artifact_id}"
        statement = (
            insert(graph_projection_events)
            .values(
                program_id=observation.program_id,
                source_type="raw_artifact",
                source_id=observation.raw_artifact_id,
                event_type="http_observations_ready",
                dedupe_key=dedupe_key,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
        )
        await self.session.execute(statement)

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
