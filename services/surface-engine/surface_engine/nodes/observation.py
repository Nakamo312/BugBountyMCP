from __future__ import annotations

from typing import Any, Iterable, Mapping

from surface_engine.canonicalization import (
    EndpointObservationInput,
    RequestShapeInput,
    ResponseShapeInput,
    TransportObservationInput,
    canonicalize_observation,
)

from .dedupe import dedupe_surface_node_drafts
from .drafts import endpoint_draft, response_shape_draft, route_template_draft
from .metadata import (
    header_names,
    metadata_list,
    metadata_mapping,
    metadata_string_mapping,
    metadata_text,
    metadata_value,
    optional_int,
    optional_text,
    required_text,
    url_from_parts,
)
from .models import SurfaceNodeDraft


def build_surface_nodes_from_observation(row: Mapping[str, Any]) -> list[SurfaceNodeDraft]:
    """Build endpoint/route/response-shape nodes from one HTTP observation row."""

    program_id = required_text(row, "program_id")
    observation_id = optional_text(row.get("id"))
    metadata = metadata_mapping(row.get("metadata"))
    canonical = canonicalize_observation(
        EndpointObservationInput(
            program_id=program_id,
            method=optional_text(row.get("method")) or "GET",
            url=optional_text(row.get("url")) or url_from_parts(row),
            host=optional_text(row.get("host")),
            transport=TransportObservationInput(
                scheme=optional_text(row.get("scheme")),
                port=optional_int(row.get("port")),
                http_version=metadata_text(metadata, "http_version", "transport.http_version"),
                alpn=metadata_text(metadata, "alpn", "transport.alpn"),
                transport_protocol=metadata_text(metadata, "transport_protocol", "transport.protocol"),
                connection_features=metadata_list(metadata, "connection_features", "transport.connection_features"),
            ),
            response_shape=ResponseShapeInput(
                status_code=optional_int(row.get("status_code")),
                header_names=header_names(row.get("headers"), row.get("header_names")),
                content_type=optional_text(row.get("content_type")),
                json_keys=metadata_list(metadata, "response_json_keys", "json_keys", "safe_features.json_keys"),
                xml_tags=metadata_list(metadata, "response_xml_tags", "xml_tags", "safe_features.xml_tags"),
                markers=metadata_list(metadata, "response_body_markers", "shape_markers", "safe_features.shape_markers"),
                body_length=optional_int(row.get("body_size_bytes")),
                body_sha256=optional_text(row.get("body_sha256")),
            ),
            request_shape=RequestShapeInput(
                content_type=metadata_text(metadata, "request_content_type", "request.content_type"),
                body_field_value_types=metadata_string_mapping(
                    metadata,
                    "request_body_field_value_types",
                    "request.body_field_value_types",
                ),
                json_keys=metadata_list(metadata, "request_json_keys", "request.json_keys"),
                xml_tags=metadata_list(metadata, "request_xml_tags", "request.xml_tags"),
                markers=metadata_list(metadata, "request_body_markers", "request.shape_markers"),
                body_length=optional_int(metadata_value(metadata, "request_body_length", "request.body_length")),
                body_sha256=optional_text(metadata_value(metadata, "request_body_sha256", "request.body_sha256")),
            ),
        )
    )
    observed_at = row.get("observed_at")
    return [
        endpoint_draft(
            program_id=program_id,
            observation_id=observation_id,
            canonical=canonical,
            status_code=optional_int(row.get("status_code")),
            content_type=optional_text(row.get("content_type")),
            observed_at=observed_at,
            source_tool=optional_text(row.get("source_tool")),
        ),
        route_template_draft(program_id=program_id, canonical=canonical, observed_at=observed_at),
        response_shape_draft(
            program_id=program_id,
            canonical=canonical,
            observed_at=observed_at,
            status_code=optional_int(row.get("status_code")),
            content_type=optional_text(row.get("content_type")),
        ),
    ]


def build_surface_nodes_from_observations(rows: Iterable[Mapping[str, Any]]) -> list[SurfaceNodeDraft]:
    """Build and deduplicate surface node drafts from HTTP observation rows."""

    drafts: list[SurfaceNodeDraft] = []
    for row in rows:
        drafts.extend(build_surface_nodes_from_observation(row))
    return dedupe_surface_node_drafts(drafts)
