from __future__ import annotations

from typing import Any, Mapping

from .models import BodyShape
from ..fingerprints import build_body_shape_fingerprint

try:
    from api.infrastructure.normalization.path_normalizer import PathNormalizer
except ImportError as exc:  # pragma: no cover - exercised by integration setup
    raise ImportError(
        "surface_engine requires src/ on PYTHONPATH so it can reuse "
        "api.infrastructure.normalization.path_normalizer.PathNormalizer"
    ) from exc


def build_body_shape(
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
    normalized_content_type = normalize_content_type(content_type)
    media_family = media_family_for_content_type(normalized_content_type)
    field_value_types = normalize_body_field_value_types(
        body_fields=body_fields,
        body_field_value_types=body_field_value_types,
    )
    field_names = sorted(field_value_types)
    normalized_json_keys = normalize_names(json_keys or [])
    normalized_xml_tags = normalize_names(xml_tags or [])
    normalized_markers = normalize_names(markers or [])
    length_bucket = length_bucket_for_body(body_length)
    content_family_fingerprint = normalize_sha256(body_sha256)

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


def build_request_param_signature(
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


def normalize_body_field_value_types(
    *,
    body_fields: Mapping[str, Any] | None,
    body_field_value_types: Mapping[str, str] | None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    if body_field_value_types:
        for raw_name, raw_value_type in body_field_value_types.items():
            name = normalize_name(raw_name)
            if name:
                normalized[name] = normalize_name(raw_value_type) or "unknown"

    if body_fields:
        for raw_name, raw_value in body_fields.items():
            name = normalize_name(raw_name)
            if not name or name in normalized:
                continue
            value = raw_value[0] if isinstance(raw_value, (list, tuple)) and raw_value else raw_value
            normalized[name] = PathNormalizer._classify_value(str(value or ""))
    return normalized


def normalize_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    normalized = content_type.split(";", 1)[0].strip().lower()
    return normalized or None


def media_family_for_content_type(content_type: str | None) -> str | None:
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


def length_bucket_for_body(length: int | None) -> str | None:
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


def normalize_names(values: list[str] | tuple[str, ...]) -> list[str]:
    return sorted({name for value in values if (name := normalize_name(value))})


def normalize_name(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_sha256(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if len(normalized) == 64 and all(char in "0123456789abcdef" for char in normalized):
        return normalized
    return None
