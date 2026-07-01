from __future__ import annotations

import argparse
import json

from .canonicalization import (
    CanonicalizationAliases,
    EndpointObservationInput,
    RequestShapeInput,
    ResponseShapeInput,
    TransportObservationInput,
    canonicalize_observation,
)
from .deltas import build_surface_deltas
from .edges import build_surface_edges_from_nodes
from .nodes import build_snapshot_draft, build_surface_nodes_from_observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="surface-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    canonicalize = subparsers.add_parser(
        "canonicalize-url",
        help="Print deterministic surface fingerprints for one URL.",
    )
    canonicalize.add_argument("url")
    canonicalize.add_argument("--method", default="GET")
    canonicalize.add_argument("--program-id")
    canonicalize.add_argument("--scheme", help="Optional scheme override, e.g. http, https, ws, wss.")
    canonicalize.add_argument("--port", type=int)
    canonicalize.add_argument("--http-version", help="Observed HTTP version, e.g. HTTP/1.1, h2, HTTP/3.")
    canonicalize.add_argument("--tls", choices=["true", "false"], help="Optional TLS override when scheme alone is not enough.")
    canonicalize.add_argument("--alpn", help="Observed ALPN token, e.g. http/1.1, h2, h3.")
    canonicalize.add_argument("--transport-protocol", help="Observed transport, e.g. tcp or quic.")
    canonicalize.add_argument("--connection-feature", action="append", default=[], help="Protocol/connection feature such as keep_alive, multiplexed, sse, websocket_upgrade, long_polling.")
    canonicalize.add_argument("--status-code", type=int)
    canonicalize.add_argument("--content-type", help="Backward-compatible response Content-Type alias.")
    canonicalize.add_argument("--request-content-type")
    canonicalize.add_argument("--request-body-field", action="append", default=[], help="Request body field as name=value; value is reduced to a type class.")
    canonicalize.add_argument("--request-json-key", action="append", default=[])
    canonicalize.add_argument("--request-xml-tag", action="append", default=[])
    canonicalize.add_argument("--response-content-type")
    canonicalize.add_argument("--json-key", action="append", default=[], help="Backward-compatible response JSON key alias.")
    canonicalize.add_argument("--response-json-key", action="append", default=[])
    canonicalize.add_argument("--response-xml-tag", action="append", default=[])
    canonicalize.add_argument("--header-name", action="append", default=[])
    canonicalize.set_defaults(func=_canonicalize_url)

    build_snapshot = subparsers.add_parser(
        "build-snapshot",
        help="Build Surface Map V1 snapshot nodes from http_observations.",
    )
    build_snapshot.add_argument("--dsn", help="PostgreSQL DSN. Required unless --dry-run-input is used.")
    build_snapshot.add_argument("--program-id", required=True)
    build_snapshot.add_argument("--limit", type=int, default=1000)
    build_snapshot.add_argument("--offset", type=int, default=0)
    build_snapshot.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print snapshot stats without writing surface_* tables.",
    )
    build_snapshot.add_argument(
        "--dry-run-input",
        help="Optional JSON file with observation rows for local contract testing.",
    )
    build_snapshot.set_defaults(func=_build_snapshot)
    return parser


def _canonicalize_url(args: argparse.Namespace) -> int:
    endpoint = canonicalize_observation(
        EndpointObservationInput(
            url=args.url,
            method=args.method,
            program_id=args.program_id,
            transport=TransportObservationInput(
                scheme=args.scheme,
                port=args.port,
                http_version=args.http_version,
                tls=_parse_bool(args.tls),
                alpn=args.alpn,
                transport_protocol=args.transport_protocol,
                connection_features=args.connection_feature,
            ),
            request_shape=RequestShapeInput(
                content_type=args.request_content_type,
                body_fields=_parse_kv_args(args.request_body_field),
                json_keys=args.request_json_key,
                xml_tags=args.request_xml_tag,
            ),
            response_shape=ResponseShapeInput(
                status_code=args.status_code,
                header_names=args.header_name,
                content_type=args.response_content_type,
                json_keys=args.response_json_key,
                xml_tags=args.response_xml_tag,
            ),
            aliases=CanonicalizationAliases(
                content_type=args.content_type,
                json_keys=args.json_key,
            ),
        )
    )
    print(json.dumps(endpoint.to_features(), indent=2, sort_keys=True))
    return 0



def _build_snapshot(args: argparse.Namespace) -> int:
    rows = _load_observation_rows(args)
    nodes = build_surface_nodes_from_observations(rows)
    edges = build_surface_edges_from_nodes(nodes)
    snapshot = build_snapshot_draft(program_id=args.program_id, nodes=nodes, source_rows=rows)
    result = {
        "snapshot": {
            "program_id": snapshot.program_id,
            "snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "algorithm": snapshot.algorithm,
            "algorithm_version": snapshot.algorithm_version,
            "input_watermark": snapshot.input_watermark,
            "source_window_start": str(snapshot.source_window_start) if snapshot.source_window_start else None,
            "source_window_end": str(snapshot.source_window_end) if snapshot.source_window_end else None,
            "stats_json": snapshot.stats_json,
        },
        "nodes": {
            "count": len(nodes),
            "types": snapshot.stats_json.get("node_types", {}),
        },
        "edges": {
            "count": len(edges),
            "types": _count_by(edges, "edge_type"),
        },
        "deltas": {
            "count": None,
        },
        "dry_run": bool(args.dry_run or args.dry_run_input),
    }
    if args.dry_run or args.dry_run_input:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if not args.dsn:
        raise SystemExit("--dsn is required unless --dry-run or --dry-run-input is used")
    from .postgres import PostgresSurfaceStore

    store = PostgresSurfaceStore(args.dsn)
    snapshot_id = store.upsert_snapshot(snapshot)
    previous_snapshot_id = store.fetch_previous_snapshot_id(
        program_id=args.program_id,
        current_snapshot_id=snapshot_id,
    )
    previous_nodes = store.fetch_snapshot_nodes(program_id=args.program_id, snapshot_id=previous_snapshot_id)
    previous_edges = store.fetch_snapshot_edges(program_id=args.program_id, snapshot_id=previous_snapshot_id)
    deltas = build_surface_deltas(
        program_id=args.program_id,
        from_snapshot_id=previous_snapshot_id,
        to_snapshot_id=snapshot_id,
        previous_nodes=previous_nodes,
        previous_edges=previous_edges,
        current_nodes=nodes,
        current_edges=edges,
    )
    nodes_written = store.upsert_nodes(snapshot_id=snapshot_id, nodes=nodes)
    edges_written = store.upsert_edges(snapshot_id=snapshot_id, edges=edges)
    deltas_written = store.upsert_deltas(deltas)
    result["snapshot"]["id"] = snapshot_id
    result["snapshot"]["previous_snapshot_id"] = previous_snapshot_id
    result["nodes"]["written"] = nodes_written
    result["edges"]["written"] = edges_written
    result["deltas"]["count"] = len(deltas)
    result["deltas"]["written"] = deltas_written
    result["deltas"]["types"] = _count_by(deltas, "delta_type")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _load_observation_rows(args: argparse.Namespace) -> list[dict]:
    if args.dry_run_input:
        with open(args.dry_run_input, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise SystemExit("--dry-run-input must point to a JSON array of observation rows")
        return [dict(row) for row in data]

    if not args.dsn:
        raise SystemExit("--dsn is required unless --dry-run-input is used")
    from .postgres import PostgresSurfaceStore

    store = PostgresSurfaceStore(args.dsn)
    return store.fetch_http_observations(program_id=args.program_id, limit=args.limit, offset=args.offset)


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() == "true"


def _parse_kv_args(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" in item:
            key, value = item.split("=", 1)
        else:
            key, value = item, ""
        key = key.strip()
        if key:
            parsed[key] = value
    return parsed


def _count_by(items: list[object], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(getattr(item, attribute))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
