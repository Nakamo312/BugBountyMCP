from __future__ import annotations

from typing import Any, Mapping

from .inputs import (
    CanonicalizationAliases,
    EndpointObservationInput,
    RequestShapeInput,
    ResponseShapeInput,
    TransportObservationInput,
)
from .endpoint import canonicalize_observation
from .models import CanonicalEndpoint


def canonicalize_endpoint(**kwargs: Any) -> CanonicalEndpoint:
    """Compatibility wrapper for legacy callers with flat observation kwargs."""

    return canonicalize_observation(_legacy_observation_input(kwargs))


def _legacy_observation_input(raw: Mapping[str, Any]) -> EndpointObservationInput:
    if "url" not in raw:
        raise TypeError("canonicalize_endpoint() missing required keyword-only argument: 'url'")
    return EndpointObservationInput(
        url=raw["url"],
        method=raw.get("method", "GET"),
        program_id=raw.get("program_id"),
        host=raw.get("host"),
        query_params=raw.get("query_params"),
        transport=_legacy_transport_input(raw),
        request_shape=_legacy_request_shape_input(raw),
        response_shape=_legacy_response_shape_input(raw),
        aliases=CanonicalizationAliases(
            content_type=raw.get("content_type"),
            json_keys=raw.get("json_keys"),
            body_sha256=raw.get("body_sha256"),
        ),
    )


def _legacy_transport_input(raw: Mapping[str, Any]) -> TransportObservationInput:
    return TransportObservationInput(
        scheme=raw.get("scheme"),
        port=raw.get("port"),
        http_version=raw.get("http_version"),
        tls=raw.get("tls"),
        alpn=raw.get("alpn"),
        transport_protocol=raw.get("transport_protocol"),
        connection_features=raw.get("connection_features"),
    )


def _legacy_request_shape_input(raw: Mapping[str, Any]) -> RequestShapeInput:
    return RequestShapeInput(
        content_type=raw.get("request_content_type"),
        body_fields=raw.get("request_body_fields"),
        body_field_value_types=raw.get("request_body_field_value_types"),
        json_keys=raw.get("request_json_keys"),
        xml_tags=raw.get("request_xml_tags"),
        markers=raw.get("request_body_markers"),
        body_length=raw.get("request_body_length"),
        body_sha256=raw.get("request_body_sha256"),
    )


def _legacy_response_shape_input(raw: Mapping[str, Any]) -> ResponseShapeInput:
    return ResponseShapeInput(
        status_code=raw.get("status_code"),
        header_names=raw.get("header_names"),
        content_type=raw.get("response_content_type"),
        body_fields=raw.get("response_body_fields"),
        body_field_value_types=raw.get("response_body_field_value_types"),
        json_keys=raw.get("response_json_keys"),
        xml_tags=raw.get("response_xml_tags"),
        markers=raw.get("response_body_markers"),
        body_length=raw.get("response_body_length"),
        body_sha256=raw.get("response_body_sha256"),
    )
