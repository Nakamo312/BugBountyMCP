from __future__ import annotations

from urllib.parse import urlparse

from .inputs import EndpointObservationInput
from .materials import build_query_material, build_request_material, build_response_material
from .models import BodyShape, CanonicalEndpoint, TransportShape
from .route import build_route_material
from .transport import build_transport_shape
from ..fingerprints import build_feature_fingerprint, build_route_fingerprint


def canonicalize_observation(observation: EndpointObservationInput) -> CanonicalEndpoint:
    """Build canonical route/request/response fingerprints for one HTTP endpoint.

    The function is deliberately deterministic and safe-by-construction:
    query and body values are reduced to value types, body content is not used,
    and SHA-256 values are carried only as content-family identifiers.
    """

    parsed = urlparse(observation.url or "")
    route = build_route_material(observation=observation, parsed=parsed)
    transport_shape = build_transport_shape(
        scheme=route.normalized_scheme,
        protocol_family=route.protocol_family,
        port=route.normalized_port,
        http_version=observation.transport.http_version,
        tls=observation.transport.tls,
        alpn=observation.transport.alpn,
        transport_protocol=observation.transport.transport_protocol,
        connection_features=observation.transport.connection_features,
    )
    query = build_query_material(url=observation.url, query_params=observation.query_params)
    request = build_request_material(
        request=observation.request_shape,
        query_param_signature=query.signature,
        query_param_signature_fingerprint=query.signature_fingerprint,
    )
    response = build_response_material(response=observation.response_shape, aliases=observation.aliases)
    route_fingerprint = build_route_fingerprint(
        program_id=observation.program_id,
        host=route.normalized_host,
        method=route.normalized_method,
        route_template=route.route_template,
        scheme=route.normalized_scheme,
        protocol_family=route.protocol_family,
        port=route.normalized_port,
    )
    feature_fingerprint = build_feature_fingerprint(
        route_fingerprint=route_fingerprint,
        request_shape_fingerprint=request.shape_fingerprint,
        response_shape_fingerprint=response.shape_fingerprint,
        request_content_family_fingerprint=(request.body_shape.content_family_fingerprint if request.body_shape else None),
        response_content_family_fingerprint=(response.body_shape.content_family_fingerprint if response.body_shape else None),
        transport_fingerprint=transport_shape.transport_fingerprint,
    )

    return CanonicalEndpoint(
        program_id=observation.program_id,
        url=route.safe_url,
        method=route.normalized_method,
        transport_shape=transport_shape,
        host=route.normalized_host,
        path=route.route_template,
        route_template=route.route_template,
        route_key=route.route_key,
        route_fingerprint=route_fingerprint,
        query_param_names=query.names,
        query_param_value_types=query.value_types,
        query_param_signature=query.signature,
        query_param_signature_fingerprint=query.signature_fingerprint,
        request_body_shape=request.body_shape,
        request_param_signature=request.param_signature,
        request_shape_fingerprint=request.shape_fingerprint,
        status_family=response.status_family,
        header_names=response.header_names,
        response_body_shape=response.body_shape,
        response_shape_fingerprint=response.shape_fingerprint,
        feature_fingerprint=feature_fingerprint,
    )
