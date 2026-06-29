# Surface Engine

Surface Engine builds deterministic Surface Map inputs from normalized
observations. It produces shape-based surface state for later graph math,
proposal ranking, search projections, and optional cluster labeling.

It does not create findings, does not call an LLM, and does not classify raw
endpoints through handwritten business labels. Canonicalization is mechanical:
route shape, request/response shape, transport shape, bounded content-family
material, and stable fingerprints.

The package reuses the existing `PathNormalizer` from
`src/api/infrastructure/normalization/path_normalizer.py` instead of defining a
second route-normalization implementation.

## What It Writes

`build-snapshot` now writes the working runtime subset of the Surface Map schema:

```text
surface_snapshots
surface_nodes
surface_edges
surface_deltas
```

`surface_nodes` are snapshot-local canonicalized surface vertices.

`surface_edges` link nodes by deterministic structural forms such as route shape
and response shape. They do not encode labels such as `admin`, `api`, `auth`, or
`docs`.

`surface_deltas` compare the current snapshot with the previous snapshot for the
same program and record structural changes such as introduced nodes and edges.
Deltas feed graph aggregation in Neo4j/GDS; raw counts are not the quality
function.

The following schema areas remain later layers:

```text
surface_clusters
surface_cluster_members
surface_cluster_labels
OpenSearch projections
LLM cluster labels
```

## Safety And Canonicalization Boundaries

Query values, request-body values, response-body values, raw headers, raw request
bodies, and raw response bodies are excluded from fingerprints.

Request and response bodies are represented only by bounded shape material:
media family, field names, value type classes, JSON keys, XML tags, markers,
size buckets, and optional content-family hashes.

Transport/protocol shape is tracked separately from request/response content.
The canonical representation may include scheme, protocol family, port, HTTP
version, TLS, ALPN, transport protocol, and bounded connection features such as
multiplexed, keep_alive, server_sent_events, websocket_upgrade, or long_polling.

Nested JSON, GraphQL, XML, protobuf/thrift schemas, and inferred business-entity
relationships are not expanded into full body graphs in this layer. They remain
follow-up graph layers.

## Example Dry Run

```bash
PYTHONPATH="$PWD/src:$PWD/services/surface-engine" \
python -m surface_engine build-snapshot \
  --program-id 00000000-0000-0000-0000-000000000001 \
  --dry-run-input ./observations.json
```

## Example PostgreSQL Run

```bash
PYTHONPATH="$PWD/src:$PWD/services/surface-engine" \
python -m surface_engine build-snapshot \
  --dsn "$DATABASE_URL" \
  --program-id 00000000-0000-0000-0000-000000000001 \
  --limit 10000
```

After a snapshot is built and projected, graph-projector surface math can run on
Neo4j/GDS through `SurfaceGraphMathReader`.
