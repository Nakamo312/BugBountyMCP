from __future__ import annotations

from dataclasses import asdict
from typing import Any

from surface_engine.canonicalization import CanonicalEndpoint
from surface_engine.fingerprints import build_node_fingerprint

from .models import SURFACE_NODE_FEATURE_VERSION, SurfaceNodeDraft


def endpoint_draft(
    *,
    program_id: str,
    observation_id: str | None,
    canonical: CanonicalEndpoint,
    status_code: int | None,
    content_type: str | None,
    observed_at: Any,
    source_tool: str | None,
) -> SurfaceNodeDraft:
    features = canonical.to_features()
    features["source"] = {
        "source_tool": source_tool,
        "ref_type": "http_observation" if observation_id else None,
        "ref_id": observation_id,
    }
    node_fingerprint = build_node_fingerprint(
        program_id=program_id,
        node_type="endpoint",
        primary_fingerprint=canonical.feature_fingerprint,
    )
    return SurfaceNodeDraft(
        program_id=program_id,
        node_type="endpoint",
        ref_type="http_observation" if observation_id else None,
        ref_id=observation_id,
        node_fingerprint=node_fingerprint,
        feature_fingerprint=canonical.feature_fingerprint,
        feature_version=SURFACE_NODE_FEATURE_VERSION,
        host=canonical.host,
        path=canonical.path,
        route_template=canonical.route_template,
        method=canonical.method,
        status_code=status_code,
        content_type=content_type,
        features_json=features,
        safe_for_search=True,
        first_seen=observed_at,
        last_seen=observed_at,
    )


def route_template_draft(*, program_id: str, canonical: CanonicalEndpoint, observed_at: Any) -> SurfaceNodeDraft:
    features = {
        "route_key": canonical.route_key,
        "route_template": canonical.route_template,
        "route_fingerprint": canonical.route_fingerprint,
        "method": canonical.method,
        "host": canonical.host,
        "transport_shape": asdict(canonical.transport_shape),
    }
    node_fingerprint = build_node_fingerprint(
        program_id=program_id,
        node_type="route_template",
        primary_fingerprint=canonical.route_fingerprint,
    )
    return SurfaceNodeDraft(
        program_id=program_id,
        node_type="route_template",
        ref_type="route_template",
        ref_id=canonical.route_fingerprint,
        node_fingerprint=node_fingerprint,
        feature_fingerprint=canonical.route_fingerprint,
        feature_version=SURFACE_NODE_FEATURE_VERSION,
        host=canonical.host,
        path=canonical.path,
        route_template=canonical.route_template,
        method=canonical.method,
        features_json=features,
        safe_for_search=True,
        first_seen=observed_at,
        last_seen=observed_at,
    )


def response_shape_draft(
    *,
    program_id: str,
    canonical: CanonicalEndpoint,
    observed_at: Any,
    status_code: int | None,
    content_type: str | None,
) -> SurfaceNodeDraft:
    features = {
        "status_family": canonical.status_family,
        "header_names": canonical.header_names,
        "response_shape_fingerprint": canonical.response_shape_fingerprint,
        "response_body_shape": asdict(canonical.response_body_shape) if canonical.response_body_shape else None,
    }
    node_fingerprint = build_node_fingerprint(
        program_id=program_id,
        node_type="response_shape",
        primary_fingerprint=canonical.response_shape_fingerprint,
    )
    return SurfaceNodeDraft(
        program_id=program_id,
        node_type="response_shape",
        ref_type="response_shape",
        ref_id=canonical.response_shape_fingerprint,
        node_fingerprint=node_fingerprint,
        feature_fingerprint=canonical.response_shape_fingerprint,
        feature_version=SURFACE_NODE_FEATURE_VERSION,
        status_code=status_code,
        content_type=content_type,
        features_json=features,
        safe_for_search=True,
        first_seen=observed_at,
        last_seen=observed_at,
    )
