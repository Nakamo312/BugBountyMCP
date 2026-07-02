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
    program_key = str(row.program_id)
    facts: list[GraphNodeFact | GraphEdgeFact] = [
        GraphNodeFact(
            **lineage,
            kind="Program",
            key=program_key,
            properties={"program_id": program_key},
        )
    ]

    if row.asn_number is not None:
        facts.extend(_asn_facts(row, lineage, program_key))
    if row.cidr:
        facts.extend(_cidr_facts(row, lineage, program_key))
    if row.ip_address:
        facts.extend(_ip_facts(row, lineage, program_key))
    if row.hostname:
        facts.extend(_host_facts(row, lineage, program_key))
    if row.hostname and row.ip_address:
        facts.append(
            GraphEdgeFact(
                **lineage,
                src_kind="Host",
                src_key=row.hostname,
                edge_kind="RESOLVES_TO",
                dst_kind="IP",
                dst_key=row.ip_address,
                properties={"source": row.host_ip_source},
            )
        )
    if row.ip_address and row.cidr:
        facts.append(GraphEdgeFact(**lineage, src_kind="IP", src_key=row.ip_address, edge_kind="IN_CIDR", dst_kind="CIDR", dst_key=row.cidr))
    if row.cidr and row.asn_number is not None:
        facts.append(GraphEdgeFact(**lineage, src_kind="CIDR", src_key=row.cidr, edge_kind="ANNOUNCED_BY", dst_kind="ASN", dst_key=_asn_key(row.asn_number)))
    if row.service is not None:
        facts.extend(_service_facts(row, lineage, program_key))
    return facts


def _asn_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
    program_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    key = _asn_key(row.asn_number)
    return [
        GraphNodeFact(
            **lineage,
            kind="ASN",
            key=key,
            properties={
                "asn": key,
                "asn_number": row.asn_number,
                "name": row.asn_name,
                "country": row.asn_country,
                "asn_id": row.asn_id,
                "display_label": key if not row.asn_name else f"{key} · {row.asn_name}",
            },
        ),
        _program_asset_edge(lineage, program_key, "ASN", key),
    ]


def _cidr_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
    program_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    assert row.cidr is not None
    return [
        GraphNodeFact(
            **lineage,
            kind="CIDR",
            key=row.cidr,
            properties={
                "cidr": row.cidr,
                "cidr_id": row.cidr_id,
                "ip_count": row.cidr_ip_count,
                "in_scope": row.cidr_in_scope,
                "source": "canonical_inventory",
                "display_label": row.cidr,
            },
        ),
        _program_asset_edge(lineage, program_key, "CIDR", row.cidr),
    ]


def _ip_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
    program_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    return [
        GraphNodeFact(
            **lineage,
            kind="IP",
            key=row.ip_address,
            properties={"address": row.ip_address, "ip_id": row.ip_id, "display_label": row.ip_address},
        ),
        _program_asset_edge(lineage, program_key, "IP", row.ip_address),
    ]


def _host_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
    program_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    return [
        GraphNodeFact(
            **lineage,
            kind="Host",
            key=row.hostname,
            properties={"hostname": row.hostname, "host_id": row.host_id, "display_label": row.hostname},
        ),
        _program_asset_edge(lineage, program_key, "Host", row.hostname),
    ]


def _service_facts(
    row: CanonicalInventoryRow,
    lineage: dict[str, object],
    program_key: str,
) -> list[GraphNodeFact | GraphEdgeFact]:
    service_key, scheme, port = row.service or ("", "", 0)
    facts: list[GraphNodeFact | GraphEdgeFact] = [
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
                "address": row.ip_address,
                "display_label": f"{scheme}:{port} @ {row.ip_address}",
            },
        ),
        _program_asset_edge(lineage, program_key, "Service", service_key),
    ]
    if row.ip_address:
        facts.append(
            GraphEdgeFact(
                **lineage,
                src_kind="IP",
                src_key=row.ip_address,
                edge_kind="EXPOSES_SERVICE",
                dst_kind="Service",
                dst_key=service_key,
                properties={"port": port, "scheme": scheme},
            )
        )
    if row.hostname:
        facts.append(
            GraphEdgeFact(
                **lineage,
                src_kind="Host",
                src_key=row.hostname,
                edge_kind="EXPOSES_SERVICE",
                dst_kind="Service",
                dst_key=service_key,
                properties={"port": port, "scheme": scheme},
            )
        )
    return facts


def _program_asset_edge(
    lineage: dict[str, object],
    program_key: str,
    dst_kind: str,
    dst_key: str,
) -> GraphEdgeFact:
    return GraphEdgeFact(
        **lineage,
        src_kind="Program",
        src_key=program_key,
        edge_kind="HAS_ASSET",
        dst_kind=dst_kind,
        dst_key=dst_key,
    )


def _asn_key(asn_number: int | None) -> str:
    return f"AS{int(asn_number)}"


def _batch_program_id(current: UUID | None, candidate: UUID) -> UUID:
    if current is None:
        return candidate
    if current != candidate:
        raise ValueError("canonical inventory batch cannot mix program_id values")
    return current
