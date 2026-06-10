from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Mapping
from urllib.parse import urlparse

from .fingerprints import (
    build_body_shape_fingerprint,
    build_feature_fingerprint,
    build_param_signature_fingerprint,
    build_request_shape_fingerprint,
    build_response_shape_fingerprint,
    build_route_fingerprint,
    build_transport_fingerprint,
)

try:
    from api.infrastructure.normalization.path_normalizer import PathNormalizer
except ImportError as exc:  # pragma: no cover - exercised by integration setup
    raise ImportError(
        "surface_engine requires src/ on PYTHONPATH so it can reuse "
        "api.infrastructure.normalization.path_normalizer.PathNormalizer"
    ) from exc


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

    def to_features(self) -> dict[str, Any]:
        return asdict(self)


# Compatibility alias for the original Phase-2 name. In v2 the value includes
# query and request-body shape material, not query params only.
@property
def _param_signature(self: CanonicalEndpoint) -> list[str]:  # pragma: no cover - property alias
    return self.request_param_signature


setattr(CanonicalEndpoint, "param_signature", _param_signature)


def canonicalize_endpoint(
    *,
    url: str,
    method: str = "GET",
    program_id: str | None = None,
    host: str | None = None,
    query_params: Mapping[str, Any] | None = None,
    scheme: str | None = None,
    port: int | None = None,
    http_version: str | None = None,
    tls: bool | None = None,
    alpn: str | None = None,
    transport_protocol: str | None = None,
    connection_features: list[str] | tuple[str, ...] | None = None,
    status_code: int | None = None,
    header_names: list[str] | tuple[str, ...] | None = None,
    response_content_type: str | None = None,
    response_json_keys: list[str] | tuple[str, ...] | None = None,
    response_xml_tags: list[str] | tuple[str, ...] | None = None,
    response_body_fields: Mapping[str, Any] | None = None,
    response_body_field_value_types: Mapping[str, str] | None = None,
    response_body_markers: list[str] | tuple[str, ...] | None = None,
    response_body_length: int | None = None,
    response_body_sha256: str | None = None,
    request_content_type: str | None = None,
    request_body_fields: Mapping[str, Any] | None = None,
    request_body_field_value_types: Mapping[str, str] | None = None,
    request_json_keys: list[str] | tuple[str, ...] | None = None,
    request_xml_tags: list[str] | tuple[str, ...] | None = None,
    request_body_markers: list[str] | tuple[str, ...] | None = None,
    request_body_length: int | None = None,
    request_body_sha256: str | None = None,
    # Backward-compatible aliases from the first Phase-2 patch. Treat these as
    # response-body shape inputs because historic http_observations primarily
    # describe responses.
    content_type: str | None = None,
    json_keys: list[str] | tuple[str, ...] | None = None,
    body_sha256: str | None = None,
) -> CanonicalEndpoint:
    """Build canonical route/request/response fingerprints for a HTTP endpoint.

    The function is deliberately deterministic and safe-by-construction:
    query and body values are reduced to value types, body content is not used,
    and SHA-256 values are carried only as content-family identifiers.
    """

    parsed = urlparse(url or "")
    normalized_method = _normalize_method(method)
    normalized_scheme = _normalize_scheme(scheme or parsed.scheme)
    normalized_host = _normalize_host(host or parsed.hostname)
    normalized_port = _normalize_port(port if port is not None else parsed.port, normalized_scheme)
    protocol_family = _protocol_family(normalized_scheme)
    transport_shape = _build_transport_shape(
        scheme=normalized_scheme,
        protocol_family=protocol_family,
        port=normalized_port,
        http_version=http_version,
        tls=tls,
        alpn=alpn,
        transport_protocol=transport_protocol,
        connection_features=connection_features,
    )
    raw_path = parsed.path or "/"
    route_template = _normalize_route_template(url or raw_path)
    safe_url = _safe_url(
        scheme=normalized_scheme,
        host=normalized_host,
        explicit_port=_explicit_port(port=port, parsed_port=parsed.port, scheme=normalized_scheme),
        route_template=route_template,
    )
    route_key = _route_key(
        normalized_method,
        normalized_scheme,
        normalized_host,
        normalized_port,
        route_template,
    )

    query_value_types = _normalize_query_value_types(url=url, query_params=query_params)
    query_param_names = sorted(query_value_types)
    query_param_signature = [f"query:{name}:{query_value_types[name]}" for name in query_param_names]
    query_param_signature_fingerprint = build_param_signature_fingerprint(query_param_signature)

    request_body_shape = _build_body_shape(
        content_type=request_content_type,
        body_fields=request_body_fields,
        body_field_value_types=request_body_field_value_types,
        json_keys=request_json_keys,
        xml_tags=request_xml_tags,
        markers=request_body_markers,
        body_length=request_body_length,
        body_sha256=request_body_sha256,
    )
    request_param_signature = _build_request_param_signature(
        query_param_signature=query_param_signature,
        request_body_shape=request_body_shape,
    )
    request_shape_fingerprint = build_request_shape_fingerprint(
        query_param_signature_fingerprint=query_param_signature_fingerprint,
        request_body_shape_fingerprint=request_body_shape.body_shape_fingerprint if request_body_shape else None,
    )

    response_body_shape = _build_body_shape(
        content_type=response_content_type or content_type,
        body_fields=response_body_fields,
        body_field_value_types=response_body_field_value_types,
        json_keys=response_json_keys if response_json_keys is not None else json_keys,
        xml_tags=response_xml_tags,
        markers=response_body_markers,
        body_length=response_body_length,
        body_sha256=response_body_sha256 or body_sha256,
    )
    normalized_status_family = _status_family(status_code)
    normalized_header_names = _normalize_names(header_names or [])

    route_fingerprint = build_route_fingerprint(
        program_id=program_id,
        host=normalized_host,
        method=normalized_method,
        route_template=route_template,
        scheme=normalized_scheme,
        protocol_family=protocol_family,
        port=normalized_port,
    )
    response_shape_fingerprint = build_response_shape_fingerprint(
        status_family=normalized_status_family,
        header_names=normalized_header_names,
        response_body_shape_fingerprint=response_body_shape.body_shape_fingerprint if response_body_shape else None,
    )
    feature_fingerprint = build_feature_fingerprint(
        route_fingerprint=route_fingerprint,
        request_shape_fingerprint=request_shape_fingerprint,
        response_shape_fingerprint=response_shape_fingerprint,
        request_content_family_fingerprint=(
            request_body_shape.content_family_fingerprint if request_body_shape else None
        ),
        response_content_family_fingerprint=(
            response_body_shape.content_family_fingerprint if response_body_shape else None
        ),
        transport_fingerprint=transport_shape.transport_fingerprint,
    )

    return CanonicalEndpoint(
        program_id=program_id,
        url=safe_url,
        method=normalized_method,
        transport_shape=transport_shape,
        host=normalized_host,
        path=route_template,
        route_template=route_template,
        route_key=route_key,
        route_fingerprint=route_fingerprint,
        query_param_names=query_param_names,
        query_param_value_types=query_value_types,
        query_param_signature=query_param_signature,
        query_param_signature_fingerprint=query_param_signature_fingerprint,
        request_body_shape=request_body_shape,
        request_param_signature=request_param_signature,
        request_shape_fingerprint=request_shape_fingerprint,
        status_family=normalized_status_family,
        header_names=normalized_header_names,
        response_body_shape=response_body_shape,
        response_shape_fingerprint=response_shape_fingerprint,
        feature_fingerprint=feature_fingerprint,
    )


_STATIC_ASSET_EXTENSIONS = {
    "css",
    "js",
    "mjs",
    "map",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "svg",
    "ico",
    "webp",
    "woff",
    "woff2",
    "ttf",
    "eot",
    "pdf",
    "txt",
    "xml",
    "json",
}
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


def _normalize_route_template(url_or_path: str) -> str:
    """Normalize a URL/path using the shared normalizer plus surface-only wrappers.

    The shared PathNormalizer handles common IDs and hashes. Surface Map adds a
    small wrapper for token-like path segments and static assets because those
    are cache/dedup shapes, not raw route identity.
    """

    normalized = PathNormalizer.normalize_path(url_or_path or "/")
    if normalized == "/":
        return normalized

    segments = [segment for segment in normalized.split("/") if segment]
    rewritten = [_normalize_surface_segment(segment) for segment in segments]
    return "/" + "/".join(rewritten)


def _normalize_surface_segment(segment: str) -> str:
    if not segment:
        return segment
    if segment.startswith("{") and segment.endswith("}"):
        return segment
    lowered = segment.lower()
    if _looks_like_static_asset(lowered):
        return "{static_asset}"
    if _looks_like_token_segment(segment):
        return "{token_like}"
    return segment


def _looks_like_static_asset(segment: str) -> bool:
    if "." not in segment:
        return False
    suffix = segment.rsplit(".", 1)[-1]
    return suffix in _STATIC_ASSET_EXTENSIONS


def _looks_like_token_segment(segment: str) -> bool:
    # JWT/JWS-like path segment: header.payload.signature.
    parts = segment.split(".")
    if len(parts) >= 3 and all(len(part) >= 6 and _BASE64URL_RE.fullmatch(part) for part in parts[:3]):
        return True

    compact = segment.strip("=")
    if len(compact) >= 32 and _BASE64URL_RE.fullmatch(segment):
        return True
    if len(compact) >= 32 and _HEX_RE.fullmatch(segment):
        return True
    return False


def _explicit_port(*, port: int | str | None, parsed_port: int | None, scheme: str | None) -> int | None:
    raw = port if port is not None else parsed_port
    if raw is None:
        return None
    return _normalize_port(raw, scheme)


def _safe_url(*, scheme: str | None, host: str | None, explicit_port: int | None, route_template: str) -> str:
    """Return a queryless, fragmentless, userinfo-free canonical URL."""

    safe_path = route_template or "/"
    if not host:
        return safe_path
    authority = host
    if explicit_port is not None:
        authority = f"{authority}:{explicit_port}"
    if scheme:
        return f"{scheme}://{authority}{safe_path}"
    return f"{authority}{safe_path}"


def _build_body_shape(
    *,
    content_type: str | None,
    body_fields: Mapping[str, Any] | None,
    body_field_value_types: Mapping[str, str] | None,
    json_keys: list[str] | tuple[str, ...] | None,
    xml_tags: list[str] | tuple[str, ...] | None,
    markers: list[str] | tuple[str, ...] | None,
    body_length: int | None,
    body_sha256: str | None,
) -> BodyShape | None:
    normalized_content_type = _normalize_content_type(content_type)
    media_family = _media_family(normalized_content_type)
    field_value_types = _normalize_body_field_value_types(
        body_fields=body_fields,
        body_field_value_types=body_field_value_types,
    )
    field_names = sorted(field_value_types)
    normalized_json_keys = _normalize_names(json_keys or [])
    normalized_xml_tags = _normalize_names(xml_tags or [])
    normalized_markers = _normalize_names(markers or [])
    length_bucket = _length_bucket(body_length)
    content_family_fingerprint = _normalize_sha256(body_sha256)

    has_shape_material = any(
        [
            normalized_content_type,
            field_names,
            normalized_json_keys,
            normalized_xml_tags,
            normalized_markers,
            length_bucket,
            content_family_fingerprint,
        ]
    )
    if not has_shape_material:
        return None

    body_shape_fingerprint = build_body_shape_fingerprint(
        content_type=normalized_content_type,
        media_family=media_family,
        field_names=field_names,
        field_value_types=field_value_types,
        json_keys=normalized_json_keys,
        xml_tags=normalized_xml_tags,
        markers=normalized_markers,
        length_bucket=length_bucket,
    )
    return BodyShape(
        content_type=normalized_content_type,
        media_family=media_family,
        field_names=field_names,
        field_value_types=field_value_types,
        json_keys=normalized_json_keys,
        xml_tags=normalized_xml_tags,
        markers=normalized_markers,
        length_bucket=length_bucket,
        body_shape_fingerprint=body_shape_fingerprint,
        content_family_fingerprint=content_family_fingerprint,
    )


def _build_request_param_signature(
    *,
    query_param_signature: list[str],
    request_body_shape: BodyShape | None,
) -> list[str]:
    signature = list(query_param_signature)
    if request_body_shape is None:
        return sorted(signature)

    if request_body_shape.media_family:
        signature.append(f"body_media:{request_body_shape.media_family}")
    if request_body_shape.length_bucket:
        signature.append(f"body_length:{request_body_shape.length_bucket}")
    for name in request_body_shape.field_names:
        signature.append(f"body_field:{name}:{request_body_shape.field_value_types[name]}")
    for key in request_body_shape.json_keys:
        signature.append(f"body_json_key:{key}")
    for tag in request_body_shape.xml_tags:
        signature.append(f"body_xml_tag:{tag}")
    for marker in request_body_shape.markers:
        signature.append(f"body_marker:{marker}")
    return sorted(signature)


def _normalize_body_field_value_types(
    *,
    body_fields: Mapping[str, Any] | None,
    body_field_value_types: Mapping[str, str] | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if body_field_value_types:
        for raw_name, raw_value_type in body_field_value_types.items():
            name = _normalize_name(raw_name)
            if name:
                normalized[name] = _normalize_name(raw_value_type) or "unknown"

    if body_fields:
        for raw_name, raw_value in body_fields.items():
            name = _normalize_name(raw_name)
            if not name or name in normalized:
                continue
            value = raw_value[0] if isinstance(raw_value, (list, tuple)) and raw_value else raw_value
            normalized[name] = PathNormalizer._classify_value(str(value or ""))
    return normalized


def _build_transport_shape(
    *,
    scheme: str | None,
    protocol_family: str | None,
    port: int | None,
    http_version: str | None,
    tls: bool | None,
    alpn: str | None,
    transport_protocol: str | None,
    connection_features: list[str] | tuple[str, ...] | None,
) -> TransportShape:
    normalized_http_version = _normalize_http_version(http_version)
    normalized_tls = _normalize_tls(tls, scheme)
    normalized_alpn = _normalize_name(alpn) if alpn else None
    normalized_transport_protocol = _normalize_transport_protocol(
        transport_protocol,
        scheme=scheme,
        http_version=normalized_http_version,
        alpn=normalized_alpn,
    )
    normalized_connection_features = _normalize_names(list(connection_features or []))
    transport_fingerprint = build_transport_fingerprint(
        scheme=scheme,
        protocol_family=protocol_family,
        port=port,
        http_version=normalized_http_version,
        tls=normalized_tls,
        alpn=normalized_alpn,
        transport_protocol=normalized_transport_protocol,
        connection_features=normalized_connection_features,
    )
    return TransportShape(
        scheme=scheme,
        protocol_family=protocol_family,
        port=port,
        http_version=normalized_http_version,
        tls=normalized_tls,
        alpn=normalized_alpn,
        transport_protocol=normalized_transport_protocol,
        connection_features=normalized_connection_features,
        transport_fingerprint=transport_fingerprint,
    )


def _normalize_scheme(scheme: str | None) -> str | None:
    if not scheme:
        return None
    normalized = scheme.strip().lower()
    return normalized or None


def _default_port(scheme: str | None) -> int | None:
    if scheme in {"http", "ws"}:
        return 80
    if scheme in {"https", "wss"}:
        return 443
    return None


def _normalize_port(port: int | str | None, scheme: str | None) -> int | None:
    if port is None:
        return _default_port(scheme)
    try:
        value = int(port)
    except (TypeError, ValueError):
        return _default_port(scheme)
    if value <= 0 or value > 65535:
        return _default_port(scheme)
    return value


def _protocol_family(scheme: str | None) -> str | None:
    if scheme in {"http", "https"}:
        return "http"
    if scheme in {"ws", "wss"}:
        return "websocket"
    if scheme:
        return "other"
    return None


def _normalize_http_version(http_version: str | None) -> str | None:
    if not http_version:
        return None
    normalized = http_version.strip().lower().replace(" ", "")
    aliases = {
        "1": "http/1.0",
        "1.0": "http/1.0",
        "http1": "http/1.0",
        "http/1": "http/1.0",
        "h1": "http/1.1",
        "1.1": "http/1.1",
        "http1.1": "http/1.1",
        "http/1.1": "http/1.1",
        "h2": "http/2",
        "2": "http/2",
        "2.0": "http/2",
        "http2": "http/2",
        "http/2": "http/2",
        "h3": "http/3",
        "3": "http/3",
        "3.0": "http/3",
        "http3": "http/3",
        "http/3": "http/3",
    }
    return aliases.get(normalized, normalized or None)


def _normalize_tls(tls: bool | None, scheme: str | None) -> bool | None:
    if tls is not None:
        return bool(tls)
    if scheme in {"https", "wss"}:
        return True
    if scheme in {"http", "ws"}:
        return False
    return None


def _normalize_transport_protocol(
    transport_protocol: str | None,
    *,
    scheme: str | None,
    http_version: str | None,
    alpn: str | None,
) -> str | None:
    if transport_protocol:
        normalized = _normalize_name(transport_protocol)
        return normalized or None
    if scheme in {"http", "https", "ws", "wss"}:
        if http_version == "http/3" or alpn == "h3":
            return "quic"
        return "tcp"
    return None


def _normalize_method(method: str | None) -> str:
    normalized = (method or "GET").strip().upper()
    return normalized or "GET"


def _normalize_host(host: str | None) -> str | None:
    if not host:
        return None
    normalized = host.strip().lower().rstrip(".")
    return normalized or None


def _route_key(
    method: str,
    scheme: str | None,
    host: str | None,
    port: int | None,
    route_template: str,
) -> str:
    if host:
        authority = host
        if port is not None:
            authority = f"{authority}:{port}"
        if scheme:
            return f"{method} {scheme}://{authority}{route_template}"
        return f"{method} {authority}{route_template}"
    return f"{method} {route_template}"


def _normalize_query_value_types(
    *,
    url: str,
    query_params: Mapping[str, Any] | None,
) -> dict[str, str]:
    if query_params is None:
        return {
            _normalize_name(name): str(value_type)
            for name, value_type in PathNormalizer.normalize_query_params(url).items()
            if _normalize_name(name)
        }

    normalized: dict[str, str] = {}
    for raw_name, raw_value in query_params.items():
        name = _normalize_name(raw_name)
        if not name:
            continue
        value = raw_value[0] if isinstance(raw_value, (list, tuple)) and raw_value else raw_value
        normalized[name] = PathNormalizer._classify_value(str(value or ""))
    return normalized


def _normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized or None


def _media_family(content_type: str | None) -> str | None:
    if not content_type:
        return None
    if content_type == "application/x-www-form-urlencoded":
        return "form"
    if content_type == "multipart/form-data":
        return "multipart"
    if content_type in {"application/json", "application/cloudevents+json"} or content_type.endswith("+json"):
        return "json"
    if content_type in {"application/xml", "text/xml"} or content_type.endswith("+xml"):
        return "xml"
    if content_type in {"application/graphql", "application/graphql+json"}:
        return "graphql"
    if content_type in {"application/x-protobuf", "application/protobuf"}:
        return "protobuf"
    if content_type in {"application/x-thrift", "application/vnd.apache.thrift.binary"}:
        return "thrift"
    if content_type in {"application/x-amf", "application/x-amf3"}:
        return "amf"
    if content_type == "application/octet-stream":
        return "binary"
    if content_type == "application/pdf":
        return "pdf"
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    if content_type.startswith("video/"):
        return "video"
    if content_type in {"text/plain", "text/html", "text/css", "text/javascript"}:
        return "text"
    return "other"


def _status_family(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return None
    if code < 100 or code > 599:
        return None
    return f"{code // 100}xx"


def _length_bucket(length: int | None) -> str | None:
    if length is None:
        return None
    try:
        value = int(length)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    if value == 0:
        return "empty"
    if value <= 128:
        return "1-128b"
    if value <= 1024:
        return "129b-1kb"
    if value <= 10 * 1024:
        return "1kb-10kb"
    if value <= 100 * 1024:
        return "10kb-100kb"
    if value <= 1024 * 1024:
        return "100kb-1mb"
    return "gt-1mb"


def _normalize_names(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({name for value in values if (name := _normalize_name(value))})


def _normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_sha256(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized):
        return normalized
    return None
