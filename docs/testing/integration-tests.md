# Integration Tests

Integration tests exercise BugBountyMCP against isolated external services. They
must never use the normal development or production database.

## Files

- `docker-compose.integration.yml` - isolated Postgres, RabbitMQ, Neo4j, and
  OpenSearch test stack.
- `.env.integration.example` - example environment for the isolated stack.
- `tests/integration/` - pytest integration tests and safety fixtures.

## Safety Rules

- Integration tests are skipped unless `RUN_INTEGRATION_TESTS=1` is set.
- Tests load `.env.integration` when it exists.
- The Postgres database name must contain `test` or `integration`.
- Tests refuse to use default local Postgres ports such as `5432`.
- Test containers and volumes use `integration`/`test` names.
- Use `down -v` after a run to delete test data.

## First-Time Setup

Create the local env file:

```bash
cp .env.integration.example .env.integration
```

Start the isolated stack:

```bash
docker compose -f docker-compose.integration.yml --env-file .env.integration up -d
```

Run integration tests:

```bash
RUN_INTEGRATION_TESTS=1 python -m pytest -q -m integration
```

Windows PowerShell:

```powershell
$env:RUN_INTEGRATION_TESTS="1"; python -m pytest -q -m integration
```

Stop and delete test data:

```bash
docker compose -f docker-compose.integration.yml --env-file .env.integration down -v
```

## E2E Graph Tests

Graph e2e tests are skipped unless `RUN_E2E_TESTS=1` is set. They use the same
isolated Docker stack as integration tests and verify projection paths from
canonical PostgreSQL state to Neo4j graph relationships.

These tests do not cover Neo4j Graph Data Science. The integration stack uses
plain Neo4j because the current MVP work is only the rebuildable GraphFact read
model. GDS projections remain post-MVP/M8 work and need separate projection
contracts before any `gds.*` procedure is introduced.

Start the required isolated services:

```bash
docker compose -f docker-compose.integration.yml --env-file .env.integration up -d postgres-integration neo4j-integration
```

Run graph e2e tests:

```bash
RUN_E2E_TESTS=1 python -m pytest -q -m e2e
```

Windows PowerShell:

```powershell
$env:RUN_E2E_TESTS="1"; python -m pytest -q -m e2e
```

The current graph e2e coverage seeds deterministic canonical rows, then runs
real graph projector components:

- canonical `httpx` rows through the HTTP observation GraphFact enqueuer;
- canonical `httpx` rows through the shared `GraphProjectionEventWorker`;
- canonical Host/IP/Service inventory through graph `rebuild`;
- real Neo4j applicator/writer.

These tests must not invoke real scanner binaries or perform external probes.

The graph projector also exposes a rebuild command that requeues GraphFact
batches from canonical PostgreSQL data:

```bash
docker compose --profile graph run --rm graph-projector rebuild
```

After `rebuild`, run `apply-loop` or keep the graph profile services running so
the queued batches are applied to Neo4j.

For normal projection-event processing, use the single worker entry point
instead of separate per-source services:

```bash
docker compose --profile graph run --rm graph-projector process-projection-events
```

The loop form can wait on the PostgreSQL `graph_projection_events_changed`
notification channel:

```bash
docker compose --profile graph run --rm graph-projector process-projection-events-loop
```

Before clearing Neo4j, the e2e fixture requires `RUN_E2E_TESTS=1` and a
test-only target: either the integration Bolt port `localhost:57687` /
`127.0.0.1:57687`, or a Neo4j database name containing `test` or `integration`.
Common default targets such as `bolt://localhost:7687` with database `neo4j` are
rejected.

## Current Coverage

The first integration set verifies that Alembic can upgrade an isolated Postgres
database to `head` and that core M1/M4 tables exist:

- action request schema tables;
- policy/scope/approval tables;
- jobs and runs;
- event store and dispatch tables;
- graph fact batch and projection event tables.

Next integration layers should cover:

- M1 action creation atomicity and blocked-action behavior;
- event dispatcher publish failure/retry/no-double-publish behavior;
- OpenSearch indexer projection and sensitive-field sanitization.

Prepared PostgreSQL acceptance also covers the completed M2 artifact schema:

- content encoding, physical size, and retention class;
- bounded raw and sanitized preview safety fields;
- parser, scope, target, tool-run, and parent-artifact lineage;
- rejection of `sanitized_safe_for_llm=true` without sanitizer lineage.
