"""Shared primitives for curated Postgres artifact readers."""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, String, cast, column, func, literal, select, table
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.application.research.sanitizer import sanitize_header, sanitize_text
from api.infrastructure.adapters.orm import endpoints, hosts, raw_body

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

LATEST_HTTP_OBSERVATIONS = table(
    "latest_http_observations",
    column("observation_id"),
    column("program_id"),
    column("endpoint_id"),
    column("service_id"),
    column("job_id"),
    column("run_id"),
    column("correlation_id"),
    column("raw_artifact_id"),
    column("method"),
    column("url"),
    column("status_code"),
    column("content_type"),
    column("title"),
    column("body_sha256"),
    column("body_size_bytes"),
    column("body_artifact_id"),
    column("body_preview"),
    column("source_tool"),
    column("observed_at"),
)

LATEST_HTTP_OBSERVATION_HEADERS = table(
    "latest_http_observation_headers",
    column("id"),
    column("endpoint_id"),
    column("observation_id"),
    column("name"),
    column("value"),
    column("ordinal"),
)


class ArtifactReaderError(ValueError):
    """Raised when an MCP artifact query violates the curated contract."""


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_LIMIT))


def clamp_offset(offset: int | None) -> int:
    if offset is None:
        return 0
    return max(0, int(offset))


class ArtifactQueryExecutor:
    """Execute bounded read-only artifact queries."""

    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory

    async def fetch_all(
        self,
        query: Select,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Mapping[str, Any]]:
        query = query.limit(clamp_limit(limit)).offset(clamp_offset(offset))
        async with self.session_factory() as session:
            result = await session.execute(query)
            return list(result.mappings().all())


def sanitize_header_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["value"] = sanitize_header(str(data.get("name") or ""), data.get("value")).safe_excerpt
    return data


def sanitize_body_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["body_preview"] = sanitize_text(data.get("body_preview")).safe_excerpt
    data["body_content"] = None
    return data


def sanitize_leak_row(row: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(row)
    data["content"] = sanitize_text(data.get("content")).safe_excerpt
    return data


def endpoint_status_code_expression():
    return func.coalesce(LATEST_HTTP_OBSERVATIONS.c.status_code, endpoints.c.status_code)


def latest_observation_body_query() -> Select:
    body_ref = func.coalesce(
        LATEST_HTTP_OBSERVATIONS.c.body_artifact_id,
        LATEST_HTTP_OBSERVATIONS.c.observation_id,
    )
    return select(
        body_ref.label("id"),
        LATEST_HTTP_OBSERVATIONS.c.endpoint_id,
        func.coalesce(
            LATEST_HTTP_OBSERVATIONS.c.body_sha256,
            cast(body_ref, String),
        ).label("body_hash"),
        cast(body_ref, String).label("body_ref"),
        func.coalesce(LATEST_HTTP_OBSERVATIONS.c.body_size_bytes, 0).label("body_length"),
        func.coalesce(LATEST_HTTP_OBSERVATIONS.c.body_preview, literal("")).label("body_preview"),
        literal(None).label("body_content"),
    )


def raw_body_query() -> Select:
    return select(
        raw_body.c.id,
        raw_body.c.endpoint_id,
        raw_body.c.body_hash,
        cast(raw_body.c.id, String).label("body_ref"),
        func.length(raw_body.c.body_content).label("body_length"),
        func.substr(raw_body.c.body_content, 1, 500).label("body_preview"),
        literal(None).label("body_content"),
    )


def scope_endpoint_child_query(
    query: Select,
    child_table,
    child_endpoint_column,
    endpoint_id: uuid.UUID | None,
    program_id: uuid.UUID | None,
) -> Select:
    if endpoint_id is None and program_id is None:
        raise ArtifactReaderError("endpoint_id or program_id is required")
    if endpoint_id is not None:
        return query.where(child_endpoint_column == endpoint_id)
    return (
        query
        .select_from(
            child_table
            .join(endpoints, child_endpoint_column == endpoints.c.id)
            .join(hosts, endpoints.c.host_id == hosts.c.id)
        )
        .where(hosts.c.program_id == program_id)
    )
