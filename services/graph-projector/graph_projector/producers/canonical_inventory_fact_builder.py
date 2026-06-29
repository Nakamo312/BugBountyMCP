from __future__ import annotations

from typing import Any, Mapping
from uuid import UUID

from ..contracts import GraphEdgeFact, GraphFactBatch, GraphNodeFact
from .canonical_inventory_projection import CanonicalInventoryRow, parse_canonical_inventory_row

PRODUCER = "canonical-inventory"


def build_canonical_inventory_batch(
    rows: list[Mapping[str, Any]],
    *,
    parser_version: str,
) -> GraphFactBatch | None:
    facts: list[GraphNodeFact | GraphEdgeFact] = []
    seen_fact_keys: set[tuple[str, UUID | None, UUID | None]] = set()
    batch_program_id: UUID | None = None

    for raw_row in rows:
        row = parse_canonical_inventory_row(raw_row)
        if row is None:
            continue
        batch_program_id = _batch_program_id(batch_program_id, row.program_id)
        for fact in canonical_inventory_facts(row):
            dedupe_key = (fact.identity_key, fact.source_artifact_id, fact.tool_run_id)
            if dedupe_key in seen_fact_keys:
                continue
            seen_fact_keys.add(dedupe_key)
            facts.append(fact)

    if batch_program_id is None or not facts:
        return None
    return GraphFactBatch(
        program_id=batch_program_id,
        facts=facts,
        produced_by=PRODUCER,
        parser_version=parser_version,
    )


def canonical_inventory_facts(row: CanonicalInventoryRow) -> list[GraphNodeFact | GraphEdgeFact]:
    lineage = {"program_id": row.program_id, "producer": PRODUCER, "confidence": 1.0}
    facts: list[GraphNodeFact | GraphEdgeFact] = [
        GraphNodeFact(
            **lineage,
            kind="Host",
            key=row.hostname,
            properties={"hostname": row.hostname, "host_id": row.host_id},
        ),
        GraphNodeFact(
            **lineage,
            kind="IP",
            key=row.ip_address,
            properties={"address": row.ip_address, "ip_id": row.ip_id},
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="Host",
            src_key=row.hostname,
            edge_kind="RESOLVES_TO",
            dst_kind="IP",
            dst_key=row.ip_address,
            properties={"source": row.host_ip_source},
        ),
    ]
    if row.service is not None:
        facts.extend(_service_facts(row, lineage))
    return facts


def _service_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
) -> list[GraphNodeFact | GraphEdgeFact]:
    service_key, scheme, port = row.service or ("", "", 0)
    return [
        GraphNodeFact(
            **lineage,
            kind="Service",
            key=service_key,
            properties={
                "service_key": service_key,
                "scheme": scheme,
                "port": port,
                "service_id": row.service_id,
                "technologies": row.technologies,
            },
        ),
        GraphEdgeFact(
            **lineage,
            src_kind="IP",
            src_key=row.ip_address,
            edge_kind="EXPOSES_SERVICE",
            dst_kind="Service",
            dst_key=service_key,
        ),
    ]


def _batch_program_id(current: UUID | None, candidate: UUID) -> UUID:
    if current is None:
        return candidate
    if current != candidate:
        raise ValueError("canonical inventory batch cannot mix program_id values")
    return current
