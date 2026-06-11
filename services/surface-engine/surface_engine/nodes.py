from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Any, Iterable, Mapping

from .canonicalize import CanonicalEndpoint, canonicalize_endpoint
from .fingerprints import build_node_fingerprint, build_snapshot_fingerprint

SURFACE_NODE_FEATURE_VERSION = "surface-node-v1"
SURFACE_SNAPSHOT_ALGORITHM = "surface-map"
SURFACE_SNAPSHOT_ALGORITHM_VERSION = "surface-map-v1"


@dataclass(frozen=True)
class SurfaceNodeDraft:
    """Shape-only node ready to be persisted into surface_nodes.

    Drafts never contain raw request/response bodies, raw header values, query
    values, cookies, authorization material, or legacy body previews. The
    observation row is used only to derive canonical route/request/response
    shape material.
    """

    program_id: str
    node_type: str
    node_fingerprint: str
    feature_fingerprint: str
    feature_version: str
    features_json: dict[str, Any]
    safe_for_search: bool
    ref_type: str | None = None
    ref_id: str | None = None
    host: str | None = None
    path: str | None = None
    route_template: str | None = None
    method: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    first_seen: datetime | str | None = None
    last_seen: datetime | str | None = None


@dataclass(frozen=True)
class SurfaceSnapshotDraft:
    """Snapshot metadata produced before writing surface_nodes."""

    program_id: str
    snapshot_fingerprint: str
    algorithm: str
    algorithm_version: str
    input_watermark: str | None
    source_window_start: datetime | str | None
    source_window_end: datetime | str | None
    stats_json: dict[str, Any]


def build_surface_nodes_from_observation(row: Mapping[str, Any]) -> list[SurfaceNodeDraft]:
    """Build endpoint/route/response-shape nodes from one HTTP observation row."""

    program_id = _required_text(row, "program_id")
    observation_id = _optional_text(row.get("id"))
    metadata = _metadata(row.get("metadata"))
    canonical = canonicalize_endpoint(
        program_id=program_id,
        method=_optional_text(row.get("method")) or "GET",
        url=_optional_text(row.get("url")) or _url_from_parts(row),
        host=_optional_text(row.get("host")),
        scheme=_optional_text(row.get("scheme")),
        port=_optional_int(row.get("port")),
        http_version=_metadata_text(metadata, "http_version", "transport.http_version"),
        alpn=_metadata_text(metadata, "alpn", "transport.alpn"),
        transport_protocol=_metadata_text(metadata, "transport_protocol", "transport.protocol"),
        connection_features=_metadata_list(metadata, "connection_features", "transport.connection_features"),
        status_code=_optional_int(row.get("status_code")),
        header_names=_header_names(row.get("headers"), row.get("header_names")),
        response_content_type=_optional_text(row.get("content_type")),
        response_json_keys=_metadata_list(metadata, "response_json_keys", "json_keys", "safe_features.json_keys"),
        response_xml_tags=_metadata_list(metadata, "response_xml_tags", "xml_tags", "safe_features.xml_tags"),
        response_body_markers=_metadata_list(metadata, "response_body_markers", "shape_markers", "safe_features.shape_markers"),
        response_body_length=_optional_int(row.get("body_size_bytes")),
        response_body_sha256=_optional_text(row.get("body_sha256")),
        request_content_type=_metadata_text(metadata, "request_content_type", "request.content_type"),
        request_body_field_value_types=_metadata_mapping(metadata, "request_body_field_value_types", "request.body_field_value_types"),
        request_json_keys=_metadata_list(metadata, "request_json_keys", "request.json_keys"),
        request_xml_tags=_metadata_list(metadata, "request_xml_tags", "request.xml_tags"),
        request_body_markers=_metadata_list(metadata, "request_body_markers", "request.shape_markers"),
        request_body_length=_optional_int(_metadata_value(metadata, "request_body_length", "request.body_length")),
        request_body_sha256=_optional_text(_metadata_value(metadata, "request_body_sha256", "request.body_sha256")),
    )
    observed_at = row.get("observed_at")
    return [
        _endpoint_node(
            program_id=program_id,
            observation_id=observation_id,
            canonical=canonical,
            status_code=_optional_int(row.get("status_code")),
            content_type=_optional_text(row.get("content_type")),
            observed_at=observed_at,
            source_tool=_optional_text(row.get("source_tool")),
        ),
        _route_template_node(program_id=program_id, canonical=canonical, observed_at=observed_at),
        _response_shape_node(
            program_id=program_id,
            canonical=canonical,
            observed_at=observed_at,
            status_code=_optional_int(row.get("status_code")),
            content_type=_optional_text(row.get("content_type")),
        ),
    ]


def build_surface_nodes_from_observations(rows: Iterable[Mapping[str, Any]]) -> list[SurfaceNodeDraft]:
    """Build and deduplicate surface node drafts from HTTP observation rows."""

    drafts: list[SurfaceNodeDraft] = []
    for row in rows:
        drafts.extend(build_surface_nodes_from_observation(row))
    return dedupe_surface_node_drafts(drafts)


def dedupe_surface_node_drafts(drafts: Iterable[SurfaceNodeDraft]) -> list[SurfaceNodeDraft]:
    """Deduplicate drafts by node_fingerprint while preserving aggregate counts."""

    grouped: dict[str, SurfaceNodeDraft] = {}
    counts: Counter[str] = Counter()
    exemplar_refs: dict[str, list[str]] = {}
    for draft in drafts:
        key = draft.node_fingerprint
        counts[key] += 1
        if draft.ref_id:
            refs = exemplar_refs.setdefault(key, [])
            if draft.ref_id not in refs and len(refs) < 10:
                refs.append(draft.ref_id)
        if key not in grouped:
            grouped[key] = _with_count(draft, observation_count=1, exemplar_refs=exemplar_refs.get(key, []))
            continue
        existing = grouped[key]
        grouped[key] = _merge_node_drafts(existing, draft, observation_count=counts[key], exemplar_refs=exemplar_refs.get(key, []))
    return sorted(grouped.values(), key=lambda node: (node.node_type, node.node_fingerprint))


def build_snapshot_draft(
    *,
    program_id: str,
    nodes: Iterable[SurfaceNodeDraft],
    source_rows: Iterable[Mapping[str, Any]],
    algorithm_version: str = SURFACE_SNAPSHOT_ALGORITHM_VERSION,
) -> SurfaceSnapshotDraft:
    """Build deterministic snapshot metadata from input rows and deduped nodes."""

    node_list = list(nodes)
    rows = list(source_rows)
    observed_values = [row.get("observed_at") for row in rows if row.get("observed_at") is not None]
    source_window_start = min(observed_values) if observed_values else None
    source_window_end = max(observed_values) if observed_values else None
    input_ids = sorted(str(row.get("id")) for row in rows if row.get("id") is not None)
    input_watermark = input_ids[-1] if input_ids else None
    snapshot_fingerprint = build_snapshot_fingerprint(
        program_id=program_id,
        algorithm_version=algorithm_version,
        node_fingerprints=[node.node_fingerprint for node in node_list],
        input_ids=input_ids,
    )
    node_type_counts = Counter(node.node_type for node in node_list)
    stats_json = {
        "source": "http_observations",
        "observations_read": len(rows),
        "nodes_deduped": len(node_list),
        "node_types": dict(sorted(node_type_counts.items())),
    }
    return SurfaceSnapshotDraft(
        program_id=program_id,
        snapshot_fingerprint=snapshot_fingerprint,
        algorithm=SURFACE_SNAPSHOT_ALGORITHM,
        algorithm_version=algorithm_version,
        input_watermark=input_watermark,
        source_window_start=source_window_start,
        source_window_end=source_window_end,
        stats_json=stats_json,
    )


def _endpoint_node(
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


def _route_template_node(*, program_id: str, canonical: CanonicalEndpoint, observed_at: Any) -> SurfaceNodeDraft:
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


def _response_shape_node(
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


def _merge_node_drafts(
    left: SurfaceNodeDraft,
    right: SurfaceNodeDraft,
    *,
    observation_count: int,
    exemplar_refs: list[str],
) -> SurfaceNodeDraft:
    first_seen = _min_seen(left.first_seen, right.first_seen)
    last_seen = _max_seen(left.last_seen, right.last_seen)
    return _with_count(
        replace(
            left,
            first_seen=first_seen,
            last_seen=last_seen,
            ref_id=left.ref_id or right.ref_id,
            ref_type=left.ref_type or right.ref_type,
        ),
        observation_count=observation_count,
        exemplar_refs=exemplar_refs,
    )


def _with_count(
    draft: SurfaceNodeDraft,
    *,
    observation_count: int,
    exemplar_refs: list[str],
) -> SurfaceNodeDraft:
    features = dict(draft.features_json)
    features["surface_node"] = {
        "observation_count": observation_count,
        "exemplar_ref_ids": list(exemplar_refs),
    }
    return replace(draft, features_json=features)


def _metadata(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metadata_value(metadata: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = metadata
        found = True
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
                continue
            found = False
            break
        if found:
            return current
    return None


def _metadata_text(metadata: Mapping[str, Any], *paths: str) -> str | None:
    return _optional_text(_metadata_value(metadata, *paths))


def _metadata_list(metadata: Mapping[str, Any], *paths: str) -> list[str]:
    value = _metadata_value(metadata, *paths)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _metadata_mapping(metadata: Mapping[str, Any], *paths: str) -> dict[str, str] | None:
    value = _metadata_value(metadata, *paths)
    if isinstance(value, Mapping):
        return {str(key): str(val) for key, val in value.items()}
    return None


def _header_names(headers: Any, fallback: Any = None) -> list[str]:
    if fallback:
        return [str(item) for item in fallback if str(item).strip()]
    if not headers:
        return []
    names: list[str] = []
    for header in headers:
        if isinstance(header, Mapping):
            name = header.get("name")
        else:
            name = header
        if name:
            names.append(str(name))
    return names


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(row: Mapping[str, Any], key: str) -> str:
    value = _optional_text(row.get(key))
    if not value:
        raise ValueError(f"missing required observation field: {key}")
    return value


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _url_from_parts(row: Mapping[str, Any]) -> str:
    scheme = _optional_text(row.get("scheme")) or "http"
    host = _optional_text(row.get("host")) or ""
    path = _optional_text(row.get("path")) or "/"
    return f"{scheme}://{host}{path}" if host else path


def _min_seen(left: Any, right: Any) -> Any:
    values = [value for value in (left, right) if value is not None]
    return min(values) if values else None


def _max_seen(left: Any, right: Any) -> Any:
    values = [value for value in (left, right) if value is not None]
    return max(values) if values else None
