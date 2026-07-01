"""Canonical endpoint observation pipeline."""

from .endpoint import canonicalize_observation
from .inputs import (
    CanonicalizationAliases,
    EndpointObservationInput,
    RequestShapeInput,
    ResponseShapeInput,
    TransportObservationInput,
)
from .legacy import canonicalize_endpoint
from .models import BodyShape, CanonicalEndpoint, TransportShape

__all__ = [
    "BodyShape",
    "CanonicalEndpoint",
    "CanonicalizationAliases",
    "EndpointObservationInput",
    "RequestShapeInput",
    "ResponseShapeInput",
    "TransportObservationInput",
    "TransportShape",
    "canonicalize_endpoint",
    "canonicalize_observation",
]
