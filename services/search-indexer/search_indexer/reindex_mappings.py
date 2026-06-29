"""OpenSearch index names, mappings, retention policies, and target registry."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from search_indexer.documents import (
    build_artifact_preview_document,
    build_detection_signal_document,
    build_endpoint_document,
    build_finding_document,
    build_http_observation_document,
    build_hypothesis_document,
    build_surface_component_document,
    build_surface_delta_document,
    build_technology_document,
)
from search_indexer.postgres_reader import PostgresSearchReader

HTTP_OBSERVATIONS_INDEX = "bb-http-observations"
ARTIFACTS_PREVIEW_INDEX = "bb-artifacts-preview"
FINDINGS_INDEX = "bb-findings"
DETECTION_SIGNALS_INDEX = "bb-detection-signals"
HYPOTHESES_INDEX = "bb-research-hypotheses"
ENDPOINTS_INDEX = "bb-endpoints"
TECHNOLOGIES_INDEX = "bb-technologies"
SURFACE_COMPONENTS_INDEX = "bb-surface-components"
SURFACE_DELTAS_INDEX = "bb-surface-deltas"


def single_node_settings() -> dict[str, Any]:
    return {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    }


def searchable_text(*, keyword_ignore_above: int = 1024) -> dict[str, Any]:
    return {
        "type": "text",
        "fields": {
            "keyword": {
                "type": "keyword",
                "ignore_above": keyword_ignore_above,
            }
        },
    }


def delete_after_policy(*, description: str, delete_after: str) -> dict[str, Any]:
    return {
        "policy": {
            "description": description,
            "default_state": "open",
            "states": [
                {
                    "name": "open",
                    "actions": [],
                    "transitions": [
                        {
                            "state_name": "delete",
                            "conditions": {"min_index_age": delete_after},
                        }
                    ],
                },
                {
                    "name": "delete",
                    "actions": [{"delete": {}}],
                    "transitions": [],
                },
            ],
        }
    }


INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    HTTP_OBSERVATIONS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "observed_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "correlation_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "service_id": {"type": "keyword"},
                "raw_artifact_id": {"type": "keyword"},
                "artifact_id": {"type": "keyword"},
                "tool_run_id": {"type": "keyword"},
                "body_artifact_id": {"type": "keyword"},
                "method": {"type": "keyword"},
                "scheme": {"type": "keyword"},
                "host": {"type": "keyword"},
                "url": searchable_text(keyword_ignore_above=4096),
                "port": {"type": "integer"},
                "path": searchable_text(keyword_ignore_above=2048),
                "status_code": {"type": "integer"},
                "content_type": {"type": "keyword"},
                "title": searchable_text(),
                "headers": {"type": "flat_object"},
                "body_sha256": {"type": "keyword"},
                "body_size_bytes": {"type": "long"},
                "source_tool": {"type": "keyword"},
                "metadata": {"type": "flat_object"},
            },
        },
    },
    ARTIFACTS_PREVIEW_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "artifact_id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "tool_run_id": {"type": "keyword"},
                "node_id": {"type": "keyword"},
                "event_name": {"type": "keyword"},
                "artifact_type": {"type": "keyword"},
                "sha256": {"type": "keyword"},
                "size_bytes": {"type": "long"},
                "metadata": {"type": "flat_object"},
                "preview": {"type": "text"},
            },
        },
    },
    ENDPOINTS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "host_id": {"type": "keyword"},
                "service_id": {"type": "keyword"},
                "host": {"type": "keyword"},
                "scheme": {"type": "keyword"},
                "port": {"type": "integer"},
                "path": searchable_text(keyword_ignore_above=2048),
                "normalized_path": searchable_text(keyword_ignore_above=2048),
                "methods": {"type": "keyword"},
                "status_code": {"type": "integer"},
                "technology_names": {"type": "keyword"},
            },
        },
    },
    TECHNOLOGIES_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "service_id": {"type": "keyword"},
                "address": {"type": "ip"},
                "scheme": {"type": "keyword"},
                "port": {"type": "integer"},
                "technology_names": {"type": "keyword"},
            },
        },
    },
    FINDINGS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "vuln_type_id": {"type": "keyword"},
                "host_id": {"type": "keyword"},
                "endpoint_id": {"type": "keyword"},
                "parameter_id": {"type": "keyword"},
                "payload_id": {"type": "keyword"},
                "execution_id": {"type": "keyword"},
                "vuln_code": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "category": {"type": "keyword"},
                "description": searchable_text(),
                "evidence": {"type": "flat_object"},
                "verified": {"type": "boolean"},
                "false_positive": {"type": "boolean"},
            },
        },
    },
    DETECTION_SIGNALS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "event_store_id": {"type": "keyword"},
                "event_id": {"type": "keyword"},
                "event_type": {"type": "keyword"},
                "program_id": {"type": "keyword"},
                "job_id": {"type": "keyword"},
                "run_id": {"type": "keyword"},
                "tool_run_id": {"type": "keyword"},
                "correlation_id": {"type": "keyword"},
                "causation_id": {"type": "keyword"},
                "source": {"type": "keyword"},
                "profile": {"type": "keyword"},
                "confidence": {"type": "float"},
            },
        },
    },
    HYPOTHESES_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "hypothesis_id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "first_seen": {"type": "date"},
                "last_seen": {"type": "date"},
                "updated_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "hypothesis_type": {"type": "keyword"},
                "hypothesis_fingerprint": {"type": "keyword"},
                "status": {"type": "keyword"},
                "state_version": {"type": "integer"},
                "priority_score": {"type": "integer"},
                "confidence": {"type": "float"},
                "severity_guess": {"type": "keyword"},
                "safety_level": {"type": "keyword"},
                "score_version": {"type": "keyword"},
                "inputs_hash": {"type": "keyword"},
                "source_signal_fingerprints": {"type": "keyword"},
                "duplicate_of_hypothesis_id": {"type": "keyword"},
                "evidence_count": {"type": "integer"},
                "evidence_ref_types": {"type": "keyword"},
                "evidence_roles": {"type": "keyword"},
                "evidence_claim_types": {"type": "keyword"},
                "evidence_ref_ids": {"type": "keyword"},
                "safe_evidence_text": {"type": "text"},
            },
        },
    },

    SURFACE_COMPONENTS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "analysis_run_id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "snapshot_id": {"type": "keyword"},
                "previous_snapshot_id": {"type": "keyword"},
                "algorithm": {"type": "keyword"},
                "algorithm_version": {"type": "keyword"},
                "report_fingerprint": {"type": "keyword"},
                "component_id": {"type": "integer"},
                "node_count": {"type": "integer"},
                "changed_node_count": {"type": "integer"},
                "structural_pressure_score": {"type": "integer"},
                "drift_score": {"type": "integer"},
                "bridge_pressure_score": {"type": "integer"},
                "outlier_score": {"type": "integer"},
                "coverage_score": {"type": "integer"},
                "exploration_priority_score": {"type": "integer"},
                "action_candidate_count": {"type": "integer"},
                "metrics": {"type": "flat_object"},
                "action_candidates": {"type": "object", "enabled": False},
            },
        },
    },
    SURFACE_DELTAS_INDEX: {
        "settings": single_node_settings(),
        "mappings": {
            "dynamic": False,
            "properties": {
                "schema_version": {"type": "keyword"},
                "sanitizer_version": {"type": "keyword"},
                "id": {"type": "keyword"},
                "@timestamp": {"type": "date"},
                "created_at": {"type": "date"},
                "program_id": {"type": "keyword"},
                "from_snapshot_id": {"type": "keyword"},
                "to_snapshot_id": {"type": "keyword"},
                "delta_type": {"type": "keyword"},
                "subject_type": {"type": "keyword"},
                "subject_fingerprint": {"type": "keyword"},
                "novelty_score": {"type": "integer"},
                "details": {"type": "flat_object"},
            },
        },
    },
}

INDEX_RETENTION_POLICIES: dict[str, dict[str, Any]] = {
    ARTIFACTS_PREVIEW_INDEX: {
        "policy_id": "bb-artifacts-preview-dev-retention",
        "delete_after": "7d",
        "policy": delete_after_policy(
            description="Delete rebuildable artifact preview indexes after 7 days in dev.",
            delete_after="7d",
        ),
    },
    HTTP_OBSERVATIONS_INDEX: {
        "policy_id": "bb-http-observations-dev-retention",
        "delete_after": "30d",
        "policy": delete_after_policy(
            description="Delete rebuildable HTTP observation indexes after 30 days in dev.",
            delete_after="30d",
        ),
    },
    HYPOTHESES_INDEX: {
        "policy_id": "bb-research-hypotheses-dev-retention",
        "delete_after": "90d",
        "policy": delete_after_policy(
            description="Delete rebuildable research hypothesis indexes after 90 days in dev.",
            delete_after="90d",
        ),
    },
    DETECTION_SIGNALS_INDEX: {
        "policy_id": "bb-detection-signals-dev-retention",
        "delete_after": "90d",
        "policy": delete_after_policy(
            description="Delete rebuildable detection signal indexes after 90 days in dev.",
            delete_after="90d",
        ),
    },
}


ReindexFilters = Mapping[str, str]
TargetFetcher = Callable[[PostgresSearchReader, int, int, str | None, ReindexFilters], list[dict[str, Any]]]
DocumentBuilder = Callable[[Mapping[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TargetSpec:
    index_name: str
    fetch_rows: TargetFetcher
    build_document: DocumentBuilder


def _fetch_http_observations(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_http_observations(limit=limit, offset=offset, program_id=program_id)


def _fetch_artifacts(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_artifacts(limit=limit, offset=offset, program_id=program_id)


def _fetch_endpoints(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_endpoints(limit=limit, offset=offset, program_id=program_id)


def _fetch_technologies(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_technologies(limit=limit, offset=offset, program_id=program_id)


def _fetch_findings(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_findings(limit=limit, offset=offset, program_id=program_id)


def _fetch_detection_signals(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_detection_signals(limit=limit, offset=offset, program_id=program_id)


def _fetch_hypotheses(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_hypotheses(limit=limit, offset=offset, program_id=program_id)


def _fetch_surface_components(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_surface_components(
        limit=limit,
        offset=offset,
        program_id=program_id,
        analysis_run_id=filters.get("analysis_run_id"),
        snapshot_id=filters.get("snapshot_id"),
    )


def _fetch_surface_deltas(reader: PostgresSearchReader, limit: int, offset: int, program_id: str | None, filters: ReindexFilters) -> list[dict[str, Any]]:
    return reader.fetch_surface_deltas(
        limit=limit,
        offset=offset,
        program_id=program_id,
        snapshot_id=filters.get("snapshot_id"),
    )


TARGETS: dict[str, TargetSpec] = {
    "http-observations": TargetSpec(HTTP_OBSERVATIONS_INDEX, _fetch_http_observations, build_http_observation_document),
    "artifacts": TargetSpec(ARTIFACTS_PREVIEW_INDEX, _fetch_artifacts, build_artifact_preview_document),
    "endpoints": TargetSpec(ENDPOINTS_INDEX, _fetch_endpoints, build_endpoint_document),
    "technologies": TargetSpec(TECHNOLOGIES_INDEX, _fetch_technologies, build_technology_document),
    "findings": TargetSpec(FINDINGS_INDEX, _fetch_findings, build_finding_document),
    "detection-signals": TargetSpec(DETECTION_SIGNALS_INDEX, _fetch_detection_signals, build_detection_signal_document),
    "hypotheses": TargetSpec(HYPOTHESES_INDEX, _fetch_hypotheses, build_hypothesis_document),
    "surface-components": TargetSpec(SURFACE_COMPONENTS_INDEX, _fetch_surface_components, build_surface_component_document),
    "surface-deltas": TargetSpec(SURFACE_DELTAS_INDEX, _fetch_surface_deltas, build_surface_delta_document),
}
