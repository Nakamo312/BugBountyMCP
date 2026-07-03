from __future__ import annotations

from typing import Any, Mapping, Protocol
from uuid import UUID

from .row_codec import optional_uuid_text as _optional_uuid_text


class RebuildCursor(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...


class RebuildConnection(Protocol):
    def cursor(self) -> RebuildCursor: ...


def _fetch_all(
    connection: RebuildConnection,
    query: str,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    cursor = connection.cursor()
    cursor.execute(
        query.strip(),
        {"limit": limit, "program_id": _optional_uuid_text(program_id)},
    )
    return list(cursor.fetchall())


RAW_ARTIFACTS_REBUILD_SQL = """
SELECT
    raw_artifacts.id,
    raw_artifacts.program_id,
    raw_artifacts.job_id,
    raw_artifacts.run_id,
    raw_artifacts.node_id,
    raw_artifacts.event_name,
    raw_artifacts.artifact_type,
    raw_artifacts.storage_uri,
    raw_artifacts.sha256,
    raw_artifacts.size_bytes,
    raw_artifacts.artifact_metadata,
    raw_artifacts.created_at
FROM raw_artifacts
WHERE raw_artifacts.run_id IS NOT NULL
  AND (%(program_id)s IS NULL OR raw_artifacts.program_id = %(program_id)s)
ORDER BY raw_artifacts.created_at ASC, raw_artifacts.id ASC
LIMIT %(limit)s;
"""


CANONICAL_INVENTORY_REBUILD_SQL = """
WITH host_ip_service AS (
    SELECT
        h.program_id,
        h.id AS host_id,
        h.host AS hostname,
        ip.id AS ip_id,
        ip.address AS ip_address,
        hi.source AS host_ip_source,
        s.id AS service_id,
        s.scheme AS service_scheme,
        s.port AS service_port,
        s.technologies,
        cidr.id AS cidr_id,
        cidr.cidr,
        cidr.ip_count AS cidr_ip_count,
        cidr.in_scope AS cidr_in_scope,
        asn.id AS asn_id,
        asn.asn_number,
        asn.organization_name AS asn_name,
        asn.country_code AS asn_country
    FROM host_ips hi
    JOIN hosts h ON h.id = hi.host_id
    JOIN ip_addresses ip ON ip.id = hi.ip_id
    LEFT JOIN services s ON s.ip_id = ip.id
    LEFT JOIN LATERAL (
        SELECT c.*
        FROM cidrs c
        WHERE c.program_id = h.program_id
          AND ip.address ~ '^[0-9A-Fa-f:.]+$'
          AND c.cidr ~ '^[0-9A-Fa-f:.]+/[0-9]+$'
          AND ip.address::inet << c.cidr::cidr
        ORDER BY masklen(c.cidr::cidr) DESC, c.cidr ASC
        LIMIT 1
    ) cidr ON TRUE
    LEFT JOIN asns asn ON asn.id = cidr.asn_id
    WHERE (%(program_id)s IS NULL OR h.program_id = %(program_id)s)
), network_inventory AS (
    SELECT
        coalesce(c.program_id, a.program_id) AS program_id,
        NULL::uuid AS host_id,
        NULL::text AS hostname,
        NULL::uuid AS ip_id,
        NULL::text AS ip_address,
        NULL::text AS host_ip_source,
        NULL::uuid AS service_id,
        NULL::text AS service_scheme,
        NULL::integer AS service_port,
        NULL::jsonb AS technologies,
        c.id AS cidr_id,
        c.cidr,
        c.ip_count AS cidr_ip_count,
        c.in_scope AS cidr_in_scope,
        a.id AS asn_id,
        a.asn_number,
        a.organization_name AS asn_name,
        a.country_code AS asn_country
    FROM cidrs c
    FULL OUTER JOIN asns a ON a.id = c.asn_id
    WHERE (%(program_id)s IS NULL OR coalesce(c.program_id, a.program_id) = %(program_id)s)
)
SELECT * FROM host_ip_service
UNION ALL
SELECT * FROM network_inventory
ORDER BY program_id ASC, hostname ASC NULLS LAST, ip_address ASC NULLS LAST, cidr ASC NULLS LAST, asn_number ASC NULLS LAST, service_port ASC NULLS LAST
LIMIT %(limit)s;
"""


HTTP_OBSERVATIONS_REBUILD_SQL = """
SELECT
    ho.id AS observation_id,
    ho.program_id,
    ho.run_id,
    ho.raw_artifact_id,
    ho.source_tool,
    ho.method,
    ho.url,
    ho.status_code,
    ho.content_type,
    ho.body_sha256,
    ho.body_size_bytes,
    ho.body_artifact_id,
    coalesce(inp.input_parameters, '[]'::jsonb) AS input_parameters,
    coalesce(hdr.response_header_names, '[]'::jsonb) AS response_header_names,
    ho.observed_at,
    e.id AS endpoint_id,
    e.path,
    e.normalized_path,
    h.id AS host_id,
    h.host AS hostname,
    s.id AS service_id,
    s.scheme,
    s.port,
    ip.id AS ip_id,
    ip.address AS ip_address
FROM http_observations ho
JOIN endpoints e ON e.id = ho.endpoint_id
JOIN hosts h ON h.id = e.host_id
JOIN services s ON s.id = ho.service_id
JOIN ip_addresses ip ON ip.id = s.ip_id
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object(
            'name', p.name,
            'location', p.location,
            'param_type', p.param_type,
            'reflected', coalesce(p.reflected, false),
            'is_array', coalesce(p.is_array, false)
        )
        ORDER BY p.location, p.name
    ) AS input_parameters
    FROM input_parameters p
    WHERE p.endpoint_id = e.id
) inp ON true
LEFT JOIN LATERAL (
    SELECT jsonb_agg(DISTINCT lower(hh.name)) AS response_header_names
    FROM http_observation_headers hh
    WHERE hh.observation_id = ho.id
) hdr ON true
WHERE ho.run_id IS NOT NULL
  AND ho.raw_artifact_id IS NOT NULL
  AND ho.source_tool IS NOT NULL
  AND ho.source_tool != ''
  AND (%(program_id)s IS NULL OR ho.program_id = %(program_id)s)
ORDER BY ho.raw_artifact_id ASC, ho.observed_at ASC, ho.id ASC
LIMIT %(limit)s;
"""


ACTION_OUTCOMES_REBUILD_SQL = """
SELECT *
FROM action_outcomes
WHERE (%(program_id)s IS NULL OR program_id = %(program_id)s)
ORDER BY updated_at ASC, id ASC
LIMIT %(limit)s;
"""


JAVASCRIPT_REFERENCES_REBUILD_SQL = """
SELECT
    jr.id AS javascript_reference_id,
    jr.program_id,
    jr.run_id,
    jr.raw_artifact_id,
    jr.source_tool,
    jr.source_url,
    jr.referenced_url,
    jr.reference_type,
    jr.observed_at,
    e.id AS endpoint_id,
    e.path,
    e.normalized_path,
    h.id AS host_id,
    h.host AS hostname,
    s.id AS service_id,
    s.scheme,
    s.port,
    ip.id AS ip_id,
    ip.address AS ip_address
FROM javascript_references jr
JOIN endpoints e ON e.id = jr.endpoint_id
JOIN hosts h ON h.id = e.host_id
JOIN services s ON s.id = jr.service_id
JOIN ip_addresses ip ON ip.id = s.ip_id
WHERE jr.run_id IS NOT NULL
  AND jr.raw_artifact_id IS NOT NULL
  AND jr.source_tool IS NOT NULL
  AND jr.source_tool != ''
  AND (%(program_id)s IS NULL OR jr.program_id = %(program_id)s)
ORDER BY jr.raw_artifact_id ASC, jr.observed_at ASC, jr.id ASC
LIMIT %(limit)s;
"""


SURFACE_MAP_REBUILD_SQL = """
SELECT
    ss.program_id,
    ss.id AS snapshot_id,
    ss.snapshot_fingerprint,
    ss.algorithm_version AS snapshot_algorithm_version,
    ss.input_watermark,
    sn.id AS node_id,
    sn.node_type,
    sn.ref_type,
    sn.ref_id,
    sn.node_fingerprint,
    sn.feature_fingerprint,
    sn.host,
    sn.path,
    sn.route_template,
    sn.method,
    sn.status_code,
    sn.content_type,
    se.id AS edge_id,
    se.edge_type,
    se.edge_fingerprint,
    se.weight,
    se.algorithm_version AS edge_algorithm_version,
    src.node_fingerprint AS src_node_fingerprint,
    dst.node_fingerprint AS dst_node_fingerprint,
    sd.id AS delta_id,
    sd.from_snapshot_id,
    sd.delta_type,
    sd.subject_type AS delta_subject_type,
    sd.subject_fingerprint AS delta_subject_fingerprint,
    sd.novelty_score
FROM surface_snapshots ss
LEFT JOIN surface_nodes sn ON sn.snapshot_id = ss.id
LEFT JOIN surface_edges se ON se.snapshot_id = ss.id
LEFT JOIN surface_nodes src ON src.id = se.src_node_id
LEFT JOIN surface_nodes dst ON dst.id = se.dst_node_id
LEFT JOIN surface_deltas sd ON sd.to_snapshot_id = ss.id
WHERE (%(program_id)s IS NULL OR ss.program_id = %(program_id)s)
ORDER BY ss.created_at ASC, ss.id ASC, sn.node_fingerprint ASC, se.edge_fingerprint ASC, sd.delta_type ASC
LIMIT %(limit)s;
"""


def fetch_raw_artifacts(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, RAW_ARTIFACTS_REBUILD_SQL, limit=limit, program_id=program_id)


def fetch_canonical_inventory(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, CANONICAL_INVENTORY_REBUILD_SQL, limit=limit, program_id=program_id)


def fetch_http_observations(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, HTTP_OBSERVATIONS_REBUILD_SQL, limit=limit, program_id=program_id)


def fetch_action_outcomes(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, ACTION_OUTCOMES_REBUILD_SQL, limit=limit, program_id=program_id)


def fetch_javascript_references(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, JAVASCRIPT_REFERENCES_REBUILD_SQL, limit=limit, program_id=program_id)


def fetch_surface_map(
    connection: RebuildConnection,
    *,
    limit: int,
    program_id: UUID | str | None,
) -> list[Mapping[str, Any]]:
    return _fetch_all(connection, SURFACE_MAP_REBUILD_SQL, limit=limit, program_id=program_id)
