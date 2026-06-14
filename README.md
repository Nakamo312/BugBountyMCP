# BugBountyMCP

BugBountyMCP is a controlled bug bounty automation platform. The project is
moving from scan-specific routes toward a durable action execution core with
policy, artifacts, projections, graph facts, and future agent-human workflows.

## Documentation

Start with:

- [Root agent index](AGENTS.md)
- [Documentation index](docs/README.md)
- [Target architecture](docs/architecture/target-platform.md)
- [Patch plan to MVP](docs/architecture/patch-plan-to-mvp.md)
- [Control plane](docs/architecture/control-plane.md)
- [Refactor roadmap](docs/architecture/refactor-roadmap.md)

## Architecture Summary

```text
ToolActionRequest
  -> policy/scope/approval
  -> PostgreSQL state + transactional outbox
  -> RabbitMQ
  -> worker / runner
  -> raw artifact metadata
  -> parser / processor / ingestor
  -> PostgreSQL canonical facts
  -> OpenSearch projection
  -> Neo4j GraphFacts
  -> LangGraph wait/resume
  -> hypothesis/evidence/report draft
```

PostgreSQL owns canonical operational state. RabbitMQ is transport. OpenSearch
and Neo4j are rebuildable read models. LangGraph owns future agent-human
workflow and must use the Tool Execution API instead of bypassing policy or
runners.

## Repository Map

- `src/api/application/` - application contracts, action services, policy,
  scheduler, pipeline configuration, and runtime-facing use cases.
- `src/api/infrastructure/` - database mappings, event infrastructure, runners,
  parsers, ingestors, artifact support, runtime manifest, and tool catalog
  adapters.
- `src/api/presentation/` - FastAPI REST surface.
- `services/graph-projector/` - GraphFact batch application, Neo4j projection,
  ontology, and raw artifact GraphFact enqueue support.
- `services/search-indexer/` - OpenSearch projection service.
- `services/surface-engine/` - deterministic surface canonicalization and
  snapshot support.
- `BugBountyDashBoard/` - React dashboard.
- `alembic/versions/` - PostgreSQL migrations.
- `tests/` - contract, application, infrastructure, and service tests.

## Local Setup

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the API locally:

```bash
python main.py
```

Or run FastAPI directly:

```bash
PYTHONPATH=src uvicorn api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="src"; uvicorn api.presentation.rest.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Docker Compose

Run the base stack:

```bash
docker compose up -d
```

Optional profiles include graph and search services:

```bash
docker compose --profile graph up -d
docker compose --profile search up -d
```

The graph profile includes Neo4j, `graph-projector`, and the raw artifact
GraphFact enqueuer.

## Verification

Run the Python test suite:

```bash
python -m pytest -q
```

Run graph/raw-artifact focused tests:

```bash
python -m pytest tests/infrastructure/test_graphfact_batch_store.py tests/infrastructure/test_raw_artifact_enqueue_command.py tests/infrastructure/test_graphfact_batch_apply_service.py tests/infrastructure/test_raw_artifact_graphfact_producer.py tests/infrastructure/test_graph_projection_events.py tests/infrastructure/test_neo4j_projector_upsert.py -q
```

Frontend dependencies and build are managed inside `BugBountyDashBoard/`.

## Safety Boundary

This platform is intended for authorized bug bounty and security research
automation. It must not run destructive, exploitative, or state-changing actions
outside explicit scope, policy, and approval workflows.
