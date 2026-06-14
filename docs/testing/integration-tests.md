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
- graph-projector Postgres-to-Neo4j smoke;
- OpenSearch indexer projection and sensitive-field sanitization.
