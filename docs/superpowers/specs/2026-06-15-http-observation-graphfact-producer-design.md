# HTTP Observation GraphFact Producer Design

## Goal

Add the first production GraphFact producer for `httpx` canonical output so
HTTP observations and endpoints become queryable asset graph facts in Neo4j.

The producer must prove the full path from a controlled tool execution to
canonical PostgreSQL facts and rebuildable Neo4j read models without invoking
real network scanners in tests.

## Scope

This design covers:

- Projection from `http_observations`, `endpoints`, `services`, IPs, and hosts
  into GraphFacts.
- Durable eventing after canonical `httpx` ingestion is complete.
- End-to-end tests that exercise PostgreSQL, GraphFact batches, the applicator,
  and Neo4j with a deterministic fake `httpx` runner.

This design does not cover:

- Running real `httpx`, `subfinder`, `katana`, `ffuf`, or other scanner
  binaries in automated tests.
- LangGraph workflow tests.
- Neo4j GDS, path scoring, similarity, or agent-facing graph query templates.
- Projection of raw HTTP bodies, full response headers, or scanner raw output
  directly into Neo4j.

## Existing Foundation

The project already has:

- `GraphNodeFact`, `GraphEdgeFact`, and `GraphFactBatch` contracts.
- A durable `graph_projection_events` table.
- `graph_fact_batches` storage and claiming.
- `GraphFactBatchApplicator`.
- `GraphFactWriter` with ontology validation and Neo4j idempotent merges.
- A service-level GraphFact producer for raw artifacts.
- Ontology definitions for `Host`, `IP`, `Service`, and `Endpoint`.
- Neo4j relationship definitions for `RESOLVES_TO`, `EXPOSES_SERVICE`, and
  `HAS_ENDPOINT`.
- `HTTPXResultIngestor`, which writes canonical HTTP observations when the unit
  of work exposes an `http_observations` repository.

## Production Flow

The production flow should be:

```text
ToolActionRequest
  -> policy/scope/approval
  -> outbox / dispatch
  -> worker
  -> httpx runner
  -> raw artifact
  -> HTTPXProcessEventParser
  -> HTTPXResultIngestor
  -> hosts / ips / host_ips / services / endpoints / http_observations
  -> http_observations_ready projection event
  -> HttpObservationGraphFactProducer
  -> graph_fact_batches
  -> GraphFactBatchApplicator
  -> Neo4j
```

The new producer should not subscribe directly to `raw_artifact_created`.
`raw_artifact_created` can happen before canonical tables are fully populated.
The asset graph projection must start from an event emitted after the canonical
HTTP observation transaction has completed.

## Durable Event

Add a canonical projection event named:

```text
http_observations_ready
```

The payload should contain enough information to project only the observations
created by one tool run or raw artifact:

```json
{
  "program_id": "uuid",
  "run_id": "uuid",
  "raw_artifact_id": "uuid",
  "source_tool": "httpx"
}
```

The producer should treat `program_id` as mandatory. `run_id` and
`raw_artifact_id` should be used as filters when present, and as lineage on
emitted facts.

## Producer

Add `HttpObservationGraphFactProducer`.

Input:

- `program_id`
- optional `run_id`
- optional `raw_artifact_id`
- canonical rows joined from:
  - `http_observations`
  - `endpoints`
  - `services`
  - `ips`
  - `hosts`

Output:

- `Host` node facts
- `IP` node facts
- `Service` node facts
- `Endpoint` node facts
- `RESOLVES_TO` edge facts from `Host` to `IP`
- `EXPOSES_SERVICE` edge facts from `IP` to `Service`
- `HAS_ENDPOINT` edge facts from `Service` to `Endpoint`

Producer identity:

```text
produced_by = httpx-observation-producer
parser_version = 1.0.0
```

Each fact must include:

- `program_id`
- `producer = "httpx"`
- `source_artifact_id` from `http_observations.raw_artifact_id`
- `tool_run_id` from `http_observations.run_id`
- `confidence`, starting at `1.0` for direct `httpx` observations

## Graph Keys

The producer must use ontology-compatible keys.

`Host`:

```text
key = lower(hostname)
```

`IP`:

```text
key = address
```

`Service`:

```text
key = host_or_ip_key + ":" + port + "/" + protocol
```

The implementation must match the existing `Service` ontology policy
`host_port_protocol` and any local helper already used by tests.

`Endpoint`:

```text
key = service_key + ":" + method + ":" + normalized_path
```

The implementation must match the existing `Endpoint` ontology policy
`service_method_normalized_path`.

## Properties

`Host` properties:

- `hostname`

`IP` properties:

- `address`
- `version` when available

`Service` properties:

- `host_key` or equivalent identity input required by ontology
- `port`
- `protocol`
- `scheme` when available

`Endpoint` properties:

- `service_key`
- `method`
- `normalized_path`
- `status_code` when available
- `content_type` when available

Do not project:

- response bodies
- full response headers
- raw scanner output
- large previews
- secrets or tokens

Those belong in raw artifacts or canonical PostgreSQL tables, not in Neo4j.

## Enqueuer

Add an enqueuer parallel to the existing raw artifact GraphFact enqueuer.

Responsibilities:

- Claim pending `http_observations_ready` projection events.
- Load canonical observation rows for the event.
- Build a `GraphFactBatch`.
- Enqueue the batch.
- Mark the event processed.
- Mark the event failed with a useful error message when projection fails.

Empty result handling:

- If the event has no matching canonical observations, mark it processed with
  no batch. This prevents poison events from being retried forever.

## E2E Test Design

Add e2e tests gated by:

```bash
RUN_E2E_TESTS=1
```

Use marker:

```python
pytest.mark.e2e
```

The e2e environment should use isolated Docker services:

- PostgreSQL test database
- Neo4j test database

The test must not invoke real scanners or make external network probes.

### Happy Path

Use a deterministic fake `httpx` runner that emits JSONL equivalent to:

```json
{
  "url": "https://api.example.com/v1/users/123",
  "host": "api.example.com",
  "path": "/v1/users/123",
  "method": "GET",
  "scheme": "https",
  "port": 443,
  "status_code": 200,
  "content_type": "application/json",
  "a": ["203.0.113.10"]
}
```

The test should execute the real parser and ingestor path, then run the
projection event processor, GraphFact batch applicator, and Neo4j assertions.

Expected PostgreSQL effects:

- one host
- one IP
- one service
- one endpoint
- one HTTP observation
- one `http_observations_ready` projection event
- one GraphFact batch for the observation projection

Expected Neo4j effects:

```cypher
(:Host {hostname: "api.example.com"})
(:IP {address: "203.0.113.10"})
(:Service {port: 443, protocol: "https"})
(:Endpoint {method: "GET", normalized_path: "/v1/users/{id}"})
```

Expected Neo4j relationships:

```cypher
(:Host)-[:RESOLVES_TO]->(:IP)
(:IP)-[:EXPOSES_SERVICE]->(:Service)
(:Service)-[:HAS_ENDPOINT]->(:Endpoint)
```

### Idempotency

Run the observation producer and batch applicator twice for the same canonical
data.

Expected result:

- no duplicate nodes
- no duplicate relationships
- GraphFact batch identities remain stable
- Neo4j relationship `identity_key` values remain stable

### Lineage

Assert that the projected `Endpoint` and `HAS_ENDPOINT` facts preserve:

- `program_id`
- `tool_run_id`
- `source_artifact_id`
- `producer = "httpx"`

### Safety

The e2e tests must fail if the configured runner attempts to execute a real
scanner binary or performs external network probing.

## Acceptance Criteria

- Unit tests cover GraphFact creation for `http_observations`.
- Integration tests cover batch enqueue and event processing against
  PostgreSQL.
- E2E tests cover the full fake-runner-to-Neo4j path.
- `python -m pytest -q` still passes without e2e services.
- `RUN_INTEGRATION_TESTS=1 python -m pytest -q -m integration` still passes.
- `RUN_E2E_TESTS=1 python -m pytest -q -m e2e` passes on the isolated test
  stack.
- No real scanner is invoked by unit, integration, or e2e tests.
- Neo4j can answer endpoint-neighborhood queries using `Host`, `IP`,
  `Service`, `Endpoint`, `RESOLVES_TO`, `EXPOSES_SERVICE`, and `HAS_ENDPOINT`.
