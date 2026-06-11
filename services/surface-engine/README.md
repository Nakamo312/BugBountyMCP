# Surface Engine

Surface Engine builds the canonical surface-map inputs used by the research layer.

Phase 2 only adds deterministic canonicalization and fingerprint helpers. It does
not build the graph, call OpenSearch, call an LLM, or create findings.

The package intentionally reuses the existing `PathNormalizer` from
`src/api/infrastructure/normalization/path_normalizer.py` instead of defining a
second route-normalization implementation.

Canonicalization is shape-based. Query values, request-body values, response-body
values, raw headers, raw request bodies, and raw response bodies are excluded.
Request and response bodies are represented by bounded shape material: media
family, field names, value type classes, JSON keys, XML tags, markers, size
buckets, and optional content-family hashes.

Transport/protocol shape is tracked separately from request/response content.
The canonical representation may include scheme, protocol family, port, HTTP
version, TLS, ALPN, transport protocol, and bounded connection features such as
multiplexed, keep_alive, server_sent_events, websocket_upgrade, or long_polling.

Nested JSON, GraphQL, XML, protobuf/thrift schemas, and inferred business-entity
relationships are intentionally not expanded into full graphs in Phase 2. They
are recorded as follow-up layers so canonicalization stays small and stable.

Phase 3 adds snapshot/node construction from `http_observations`. It writes only
`surface_snapshots` and `surface_nodes`; edges, clusters, OpenSearch projections,
and LLM labels remain later phases.

Example dry run against a JSON file of observation rows:

```bash
PYTHONPATH="$PWD/src:$PWD/services/surface-engine" \
python -m surface_engine build-snapshot \
  --program-id 00000000-0000-0000-0000-000000000001 \
  --dry-run-input ./observations.json
```

Example PostgreSQL run:

```bash
PYTHONPATH="$PWD/src:$PWD/services/surface-engine" \
python -m surface_engine build-snapshot \
  --dsn "$DATABASE_URL" \
  --program-id 00000000-0000-0000-0000-000000000001 \
  --limit 10000
```
