from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

NameList = list[str] | tuple[str, ...]


@dataclass(frozen=True)
class TransportObservationInput:
    """Protocol-level material observed for one endpoint sample."""

    scheme: str | None = None
    port: int | None = None
    http_version: str | None = None
    tls: bool | None = None
    alpn: str | None = None
    transport_protocol: str | None = None
    connection_features: NameList | None = None


@dataclass(frozen=True)
class BodyShapeInput:
    """Shape-only request/response body material.

    Raw body bytes and raw field values do not belong here. Field values are
    accepted only when a caller still needs the normalizer to reduce them to
    value classes.
    """

    content_type: str | None = None
    body_fields: Mapping[str, Any] | None = None
    body_field_value_types: Mapping[str, str] | None = None
    json_keys: NameList | None = None
    xml_tags: NameList | None = None
    markers: NameList | None = None
    body_length: int | None = None
    body_sha256: str | None = None


@dataclass(frozen=True)
class RequestShapeInput(BodyShapeInput):
    """Request body shape material."""


@dataclass(frozen=True)
class ResponseShapeInput(BodyShapeInput):
    """Response shape material plus status/header shape."""

    status_code: int | None = None
    header_names: NameList | None = None


@dataclass(frozen=True)
class CanonicalizationAliases:
    """Legacy response-body aliases retained only at the compatibility boundary."""

    content_type: str | None = None
    json_keys: NameList | None = None
    body_sha256: str | None = None


@dataclass(frozen=True)
class EndpointObservationInput:
    """Structured input for endpoint canonicalization.

    This replaces the old habit of passing every surface observation field as a
    top-level optional argument. Keep compatibility aliases outside the normal
    request/response structures so new callers cannot accidentally create two
    sources of truth for the same shape.
    """

    url: str
    method: str = "GET"
    program_id: str | None = None
    host: str | None = None
    query_params: Mapping[str, Any] | None = None
    transport: TransportObservationInput = field(default_factory=TransportObservationInput)
    request_shape: RequestShapeInput = field(default_factory=RequestShapeInput)
    response_shape: ResponseShapeInput = field(default_factory=ResponseShapeInput)
    aliases: CanonicalizationAliases = field(default_factory=CanonicalizationAliases)
