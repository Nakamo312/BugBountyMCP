from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TransportShape:
    """Canonical transport/protocol shape for one observation.

    TransportShape is not request content. It captures protocol-level material
    that matters for later analysis of HTTP versions, TLS, WebSocket upgrades,
    HTTP/2 multiplexing, HTTP/3/QUIC, long-lived connections, and similar
    protocol surfaces.
    """

    scheme: str | None
    protocol_family: str | None
    port: int | None
    http_version: str | None
    tls: bool | None
    alpn: str | None
    transport_protocol: str | None
    connection_features: list[str]
    transport_fingerprint: str


@dataclass(frozen=True)
class BodyShape:
    """Canonical request/response body shape.

    BodyShape is shape-only. It may contain names, media families, type classes,
    size buckets, and hashes, but never raw body bytes or raw field values.
    """

    content_type: str | None
    media_family: str | None
    field_names: list[str]
    field_value_types: dict[str, str]
    json_keys: list[str]
    xml_tags: list[str]
    markers: list[str]
    length_bucket: str | None
    body_shape_fingerprint: str
    content_family_fingerprint: str | None


@dataclass(frozen=True)
class CanonicalEndpoint:
    """Canonical shape for one HTTP endpoint observation.

    This object is the cache key substrate for the surface map. It contains
    deterministic route/query/body/response-shape fingerprints and excludes raw
    query values, raw headers, raw request bodies, raw response bodies, and raw
    request/response field values.
    """

    program_id: str | None
    url: str
    method: str
    transport_shape: TransportShape
    host: str | None
    path: str
    route_template: str
    route_key: str
    route_fingerprint: str
    query_param_names: list[str]
    query_param_value_types: dict[str, str]
    query_param_signature: list[str]
    query_param_signature_fingerprint: str
    request_body_shape: BodyShape | None
    request_param_signature: list[str]
    request_shape_fingerprint: str
    status_family: str | None
    header_names: list[str]
    response_body_shape: BodyShape | None
    response_shape_fingerprint: str
    feature_fingerprint: str

    @property
    def param_signature(self) -> list[str]:
        return self.request_param_signature

    def to_features(self) -> dict[str, Any]:
        return asdict(self)
