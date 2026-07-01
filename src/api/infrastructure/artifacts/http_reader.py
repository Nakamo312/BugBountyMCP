"""HTTP observation child artifact queries."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import or_, select

from api.application.artifact_contracts import BodyArtifact, HeaderArtifact
from api.infrastructure.adapters.orm import headers, input_parameters, raw_body
from api.infrastructure.artifacts.common import (
    LATEST_HTTP_OBSERVATION_HEADERS,
    LATEST_HTTP_OBSERVATIONS,
    ArtifactQueryExecutor,
    latest_observation_body_query,
    raw_body_query,
    sanitize_body_row,
    sanitize_header_row,
    scope_endpoint_child_query,
)


class HttpObservationArtifactReader:
    """Read latest HTTP observation headers and body previews."""

    def __init__(self, executor: ArtifactQueryExecutor):
        self.executor = executor

    async def list_headers(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        name: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[HeaderArtifact]:
        rows = await self._latest_header_rows(
            endpoint_id=endpoint_id,
            program_id=program_id,
            name=name,
            limit=limit,
            offset=offset,
        )
        if rows:
            return [HeaderArtifact.model_validate(sanitize_header_row(row)) for row in rows]

        rows = await self._legacy_header_rows(
            endpoint_id=endpoint_id,
            program_id=program_id,
            name=name,
            limit=limit,
            offset=offset,
        )
        return [HeaderArtifact.model_validate(sanitize_header_row(row)) for row in rows]

    async def list_bodies(
        self,
        endpoint_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        body_hash: str | None = None,
        include_content: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[BodyArtifact]:
        rows = await self._latest_body_rows(
            endpoint_id=endpoint_id,
            program_id=program_id,
            body_hash=body_hash,
            limit=limit,
            offset=offset,
        )
        if rows:
            return [BodyArtifact.model_validate(sanitize_body_row(row)) for row in rows]

        rows = await self._legacy_body_rows(
            endpoint_id=endpoint_id,
            program_id=program_id,
            body_hash=body_hash,
            limit=limit,
            offset=offset,
        )
        return [BodyArtifact.model_validate(sanitize_body_row(row)) for row in rows]

    async def _latest_header_rows(
        self,
        *,
        endpoint_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        name: str | None,
        limit: int | None,
        offset: int | None,
    ) -> list:
        query = select(
            LATEST_HTTP_OBSERVATION_HEADERS.c.id,
            LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
            LATEST_HTTP_OBSERVATION_HEADERS.c.name,
            LATEST_HTTP_OBSERVATION_HEADERS.c.value,
        )
        query = scope_endpoint_child_query(
            query,
            LATEST_HTTP_OBSERVATION_HEADERS,
            LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
            endpoint_id,
            program_id,
        )
        if name:
            query = query.where(LATEST_HTTP_OBSERVATION_HEADERS.c.name.ilike(f"%{name}%"))
        return await self.executor.fetch_all(
            query.order_by(LATEST_HTTP_OBSERVATION_HEADERS.c.name),
            limit,
            offset,
        )

    async def _legacy_header_rows(
        self,
        *,
        endpoint_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        name: str | None,
        limit: int | None,
        offset: int | None,
    ) -> list:
        query = select(headers)
        query = scope_endpoint_child_query(query, headers, headers.c.endpoint_id, endpoint_id, program_id)
        if name:
            query = query.where(headers.c.name.ilike(f"%{name}%"))
        return await self.executor.fetch_all(query.order_by(headers.c.name), limit, offset)

    async def _latest_body_rows(
        self,
        *,
        endpoint_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        body_hash: str | None,
        limit: int | None,
        offset: int | None,
    ) -> list:
        query = latest_observation_body_query()
        query = scope_endpoint_child_query(
            query,
            LATEST_HTTP_OBSERVATIONS,
            LATEST_HTTP_OBSERVATIONS.c.endpoint_id,
            endpoint_id,
            program_id,
        )
        query = query.where(latest_observation_has_body())
        if body_hash:
            query = query.where(LATEST_HTTP_OBSERVATIONS.c.body_sha256 == body_hash)
        return await self.executor.fetch_all(
            query.order_by(LATEST_HTTP_OBSERVATIONS.c.observed_at.desc()),
            limit,
            offset,
        )

    async def _legacy_body_rows(
        self,
        *,
        endpoint_id: uuid.UUID | None,
        program_id: uuid.UUID | None,
        body_hash: str | None,
        limit: int | None,
        offset: int | None,
    ) -> list:
        query = raw_body_query()
        query = scope_endpoint_child_query(query, raw_body, raw_body.c.endpoint_id, endpoint_id, program_id)
        if body_hash:
            query = query.where(raw_body.c.body_hash == body_hash)
        return await self.executor.fetch_all(query.order_by(raw_body.c.id), limit, offset)

    @staticmethod
    async def endpoint_headers(session, endpoint_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await session.execute(
            select(
                LATEST_HTTP_OBSERVATION_HEADERS.c.id,
                LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id,
                LATEST_HTTP_OBSERVATION_HEADERS.c.name,
                LATEST_HTTP_OBSERVATION_HEADERS.c.value,
            )
            .where(LATEST_HTTP_OBSERVATION_HEADERS.c.endpoint_id == endpoint_id)
            .order_by(LATEST_HTTP_OBSERVATION_HEADERS.c.ordinal, LATEST_HTTP_OBSERVATION_HEADERS.c.name)
        )
        rows = [dict(row) for row in result.mappings().all()]
        if rows:
            return [sanitize_header_row(row) for row in rows]

        result = await session.execute(select(headers).where(headers.c.endpoint_id == endpoint_id))
        return [sanitize_header_row(row) for row in result.mappings().all()]

    @staticmethod
    async def endpoint_bodies(
        session,
        endpoint_id: uuid.UUID,
        include_content: bool,
    ) -> list[dict[str, Any]]:
        result = await session.execute(
            latest_observation_body_query()
            .where(LATEST_HTTP_OBSERVATIONS.c.endpoint_id == endpoint_id)
            .where(latest_observation_has_body())
            .order_by(LATEST_HTTP_OBSERVATIONS.c.observed_at.desc())
        )
        rows = [dict(row) for row in result.mappings().all()]
        if rows:
            return [sanitize_body_row(row) for row in rows]

        result = await session.execute(raw_body_query().where(raw_body.c.endpoint_id == endpoint_id))
        return [sanitize_body_row(row) for row in result.mappings().all()]


def latest_observation_has_body():
    return or_(
        LATEST_HTTP_OBSERVATIONS.c.body_sha256.is_not(None),
        LATEST_HTTP_OBSERVATIONS.c.body_artifact_id.is_not(None),
        LATEST_HTTP_OBSERVATIONS.c.body_preview.is_not(None),
    )
