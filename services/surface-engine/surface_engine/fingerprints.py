from __future__ import annotations

import hashlib
import json
from typing import Any

ROUTE_FINGERPRINT_VERSION = "route-fingerprint-v2"
TRANSPORT_FINGERPRINT_VERSION = "transport-fingerprint-v1"
PARAM_SIGNATURE_VERSION = "param-signature-v1"
BODY_SHAPE_VERSION = "body-shape-v1"
REQUEST_SHAPE_VERSION = "request-shape-v1"
RESPONSE_SHAPE_VERSION = "response-shape-v2"
FEATURE_FINGERPRINT_VERSION = "surface-feature-v2"


def stable_hash(payload: Any) -> str:
    """Return a deterministic SHA-256 hash for JSON-like payloads.

    Fingerprints are intentionally based on canonical shape material, not raw
    request/response bodies. Callers should only pass bounded safe metadata and
    deterministic shape summaries.
    """

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_transport_fingerprint(
    *,
    scheme: str | None,
    protocol_family: str | None,
    port: int | None,
    http_version: str | None,
    tls: bool | None,
    alpn: str | None,
    transport_protocol: str | None,
    connection_features: list[str],
) -> str:
    return stable_hash(
        {
            "version": TRANSPORT_FINGERPRINT_VERSION,
            "scheme": scheme or "",
            "protocol_family": protocol_family or "",
            "port": port,
            "http_version": http_version or "",
            "tls": tls,
            "alpn": alpn or "",
            "transport_protocol": transport_protocol or "",
            "connection_features": sorted(connection_features),
        }
    )


def build_route_fingerprint(
    *,
    program_id: str | None,
    host: str | None,
    method: str,
    route_template: str,
    scheme: str | None,
    protocol_family: str | None,
    port: int | None,
) -> str:
    return stable_hash(
        {
            "version": ROUTE_FINGERPRINT_VERSION,
            "program_id": program_id or "",
            "host": host or "",
            "method": method,
            "route_template": route_template,
            "scheme": scheme or "",
            "protocol_family": protocol_family or "",
            "port": port,
        }
    )


def build_param_signature_fingerprint(param_signature: list[str]) -> str:
    return stable_hash(
        {
            "version": PARAM_SIGNATURE_VERSION,
            "param_signature": sorted(param_signature),
        }
    )


def build_body_shape_fingerprint(
    *,
    content_type: str | None,
    media_family: str | None,
    field_names: list[str],
    field_value_types: dict[str, str],
    json_keys: list[str],
    xml_tags: list[str],
    markers: list[str],
    length_bucket: str | None,
) -> str:
    return stable_hash(
        {
            "version": BODY_SHAPE_VERSION,
            "content_type": content_type,
            "media_family": media_family,
            "field_names": sorted(field_names),
            "field_value_types": {key: field_value_types[key] for key in sorted(field_value_types)},
            "json_keys": sorted(json_keys),
            "xml_tags": sorted(xml_tags),
            "markers": sorted(markers),
            "length_bucket": length_bucket,
        }
    )


def build_request_shape_fingerprint(
    *,
    query_param_signature_fingerprint: str,
    request_body_shape_fingerprint: str | None,
) -> str:
    return stable_hash(
        {
            "version": REQUEST_SHAPE_VERSION,
            "query_param_signature_fingerprint": query_param_signature_fingerprint,
            "request_body_shape_fingerprint": request_body_shape_fingerprint,
        }
    )


def build_response_shape_fingerprint(
    *,
    status_family: str | None,
    header_names: list[str],
    response_body_shape_fingerprint: str | None,
) -> str:
    return stable_hash(
        {
            "version": RESPONSE_SHAPE_VERSION,
            "status_family": status_family,
            "header_names": sorted(header_names),
            "response_body_shape_fingerprint": response_body_shape_fingerprint,
        }
    )


def build_feature_fingerprint(
    *,
    route_fingerprint: str,
    request_shape_fingerprint: str,
    response_shape_fingerprint: str,
    request_content_family_fingerprint: str | None,
    response_content_family_fingerprint: str | None,
    transport_fingerprint: str,
) -> str:
    return stable_hash(
        {
            "version": FEATURE_FINGERPRINT_VERSION,
            "route_fingerprint": route_fingerprint,
            "request_shape_fingerprint": request_shape_fingerprint,
            "response_shape_fingerprint": response_shape_fingerprint,
            "request_content_family_fingerprint": request_content_family_fingerprint,
            "response_content_family_fingerprint": response_content_family_fingerprint,
            "transport_fingerprint": transport_fingerprint,
        }
    )
