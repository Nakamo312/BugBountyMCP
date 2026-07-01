from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .body import build_body_shape, build_request_param_signature, normalize_name, normalize_names
from .inputs import CanonicalizationAliases, RequestShapeInput, ResponseShapeInput
from .models import BodyShape
from ..fingerprints import (
    build_param_signature_fingerprint,
    build_request_shape_fingerprint,
    build_response_shape_fingerprint,
)

try:
    from api.infrastructure.normalization.path_normalizer import PathNormalizer
except ImportError as exc:  # pragma: no cover - exercised by integration setup
    raise ImportError(
        "surface_engine requires src/ on PYTHONPATH so it can reuse "
        "api.infrastructure.normalization.path_normalizer.PathNormalizer"
    ) from exc


@dataclass(frozen=True)
class QueryMaterial:
    names: list[str]
    value_types: dict[str, str]
    signature: list[str]
    signature_fingerprint: str


@dataclass(frozen=True)
class RequestMaterial:
    body_shape: BodyShape | None
    param_signature: list[str]
    shape_fingerprint: str


@dataclass(frozen=True)
class ResponseMaterial:
    body_shape: BodyShape | None
    status_family: str | None
    header_names: list[str]
    shape_fingerprint: str


def build_query_material(*, url: str, query_params: Mapping[str, Any] | None) -> QueryMaterial:
    value_types = normalize_query_value_types(url=url, query_params=query_params)
    names = sorted(value_types)
    signature = [f"query:{name}:{value_types[name]}" for name in names]
    signature_fingerprint = build_param_signature_fingerprint(signature)
    return QueryMaterial(
        names=names,
        value_types=value_types,
        signature=signature,
        signature_fingerprint=signature_fingerprint,
    )


def build_request_material(
    *,
    request: RequestShapeInput,
    query_param_signature: list[str],
    query_param_signature_fingerprint: str,
) -> RequestMaterial:
    body_shape = build_body_shape(
        content_type=request.content_type,
        body_fields=request.body_fields,
        body_field_value_types=request.body_field_value_types,
        json_keys=request.json_keys,
        xml_tags=request.xml_tags,
        markers=request.markers,
        body_length=request.body_length,
        body_sha256=request.body_sha256,
    )
    param_signature = build_request_param_signature(
        query_param_signature=query_param_signature,
        request_body_shape=body_shape,
    )
    shape_fingerprint = build_request_shape_fingerprint(
        query_param_signature_fingerprint=query_param_signature_fingerprint,
        request_body_shape_fingerprint=body_shape.body_shape_fingerprint if body_shape else None,
    )
    return RequestMaterial(
        body_shape=body_shape,
        param_signature=param_signature,
        shape_fingerprint=shape_fingerprint,
    )


def build_response_material(
    *,
    response: ResponseShapeInput,
    aliases: CanonicalizationAliases,
) -> ResponseMaterial:
    body_shape = build_body_shape(
        content_type=response.content_type or aliases.content_type,
        body_fields=response.body_fields,
        body_field_value_types=response.body_field_value_types,
        json_keys=response.json_keys if response.json_keys is not None else aliases.json_keys,
        xml_tags=response.xml_tags,
        markers=response.markers,
        body_length=response.body_length,
        body_sha256=response.body_sha256 or aliases.body_sha256,
    )
    status_family = status_family_for_code(response.status_code)
    header_names = normalize_names(response.header_names or [])
    shape_fingerprint = build_response_shape_fingerprint(
        status_family=status_family,
        header_names=header_names,
        response_body_shape_fingerprint=body_shape.body_shape_fingerprint if body_shape else None,
    )
    return ResponseMaterial(
        body_shape=body_shape,
        status_family=status_family,
        header_names=header_names,
        shape_fingerprint=shape_fingerprint,
    )


def normalize_query_value_types(
    *,
    url: str,
    query_params: Mapping[str, Any] | None,
) -> dict[str, str]:
    if query_params is None:
        return {
            normalize_name(name): str(value_type)
            for name, value_type in PathNormalizer.normalize_query_params(url).items()
            if normalize_name(name)
        }

    normalized: dict[str, str] = {}
    for raw_name, raw_value in query_params.items():
        name = normalize_name(raw_name)
        if not name:
            continue
        value = raw_value[0] if isinstance(raw_value, (list, tuple)) and raw_value else raw_value
        normalized[name] = PathNormalizer._classify_value(str(value or ""))
    return normalized


def status_family_for_code(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        return None
    if code < 100 or code > 599:
        return None
    return f"{code // 100}xx"
