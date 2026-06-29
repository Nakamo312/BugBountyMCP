from __future__ import annotations

from typing import Any, Mapping

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .raw_artifact_projection import RawArtifactProjectionRow, parse_raw_artifact_row

PRODUCER = "raw-artifact-metadata"


def build_raw_artifact_batch(row: Mapping[str, Any], *, parser_version: str) -> GraphFactBatch | None:
    projection = parse_raw_artifact_row(row)
    if projection is None:
        return None
    return GraphFactBatch(
        program_id=projection.program_id,
        produced_by=PRODUCER,
        parser_version=parser_version,
        facts=raw_artifact_facts(projection),
    )


def raw_artifact_facts(row: RawArtifactProjectionRow) -> list[GraphNodeFact | GraphEdgeFact]:
    lineage = {
        "program_id": row.program_id,
        "producer": PRODUCER,
        "source_artifact_id": row.artifact_id,
        "tool_run_id": row.run_id,
        "confidence": 1.0,
    }
    return [
        GraphNodeFact(
            **lineage,
            kind="Program",
            key=str(row.program_id),
            properties={"program_id": str(row.program_id)},
        ),
        GraphNodeFact(
            **lineage,
            kind="Tool",
            key=row.node_id,
            properties={"tool_id": row.node_id, "event_name": row.event_name},
        ),
        GraphNodeFact(
            **lineage,
            kind="ToolRun",
            key=str(row.run_id),
            properties={
                "tool_run_id": str(row.run_id),
                "job_id": str(row.job_id) if row.job_id else None,
                "node_id": row.node_id,
                "event_name": row.event_name,
            },
        ),
        GraphNodeFact(
            **lineage,
            kind="Artifact",
            key=str(row.artifact_id),
            properties={
                "artifact_id": str(row.artifact_id),
                "artifact_type": row.artifact_type,
                "storage_uri": row.storage_uri,
                "sha256": row.sha256,
                "size_bytes": row.size_bytes,
                "node_id": row.node_id,
                "event_name": row.event_name,
                "created_at": row.created_at,
            },
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="Program",
            src_key=str(row.program_id),
            edge_kind="HAS_TOOL_RUN",
            dst_kind="ToolRun",
            dst_key=str(row.run_id),
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="ToolRun",
            src_key=str(row.run_id),
            edge_kind="USED_TOOL",
            dst_kind="Tool",
            dst_key=row.node_id,
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="ToolRun",
            src_key=str(row.run_id),
            edge_kind="PRODUCED_ARTIFACT",
            dst_kind="Artifact",
            dst_key=str(row.artifact_id),
        ),
    ]
