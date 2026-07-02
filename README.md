# BugBountyMCP

BugBountyMCP is an experience-first security research system. The project is
moving from scan-specific routes toward a durable research substrate where
actions, observations, deltas, evidence, projections, feedback, and agent
proposals become replayable memory.

## Documentation

Start with:

- [Root agent index](AGENTS.md)
- [Documentation index](docs/README.md)
- [Research operating model](docs/architecture/research-operating-model.md)
- [Graph math role](docs/architecture/graph-math-role.md)
- [Graph algorithm backlog](docs/architecture/graph-algorithm-backlog.md)
- [Typed graph projections](docs/architecture/typed-graph-projections.md)
- [`docs/architecture/g-http-projection-contract.md`](docs/architecture/g-http-projection-contract.md) — minimal `G_http` projection event/shape contract.
- [`docs/architecture/bipartite-endpoint-param-contract.md`](docs/architecture/bipartite-endpoint-param-contract.md) — minimal `G_bipartite_endpoint_param` endpoint ↔ param contract.
- [Orchestration store split plan](docs/architecture/orchestration-store-split-plan.md)
- [Target architecture](docs/architecture/target-platform.md)
- [Patch plan to MVP](docs/architecture/patch-plan-to-mvp.md)
- [Control plane](docs/architecture/control-plane.md)
- [Refactor roadmap](docs/architecture/refactor-roadmap.md)

## Architecture Summary

```text
state / structural signal / retrieved evidence
  -> hypothesis proposal
  -> ToolActionRequest
  -> policy/scope/approval/budget
  -> PostgreSQL state + transactional outbox
  -> RabbitMQ
  -> worker / runner
  -> raw artifact metadata
  -> parser / processor / ingestor
  -> PostgreSQL canonical facts and outcomes
  -> OpenSearch retrieval projection
  -> Neo4j/GDS structural signal projection
  -> RAG/RLM analysis tasks
  -> LangGraph proposal/evidence/report workflow
```

PostgreSQL owns canonical operational state and research memory. RabbitMQ is
transport. OpenSearch and Neo4j are rebuildable projections. Neo4j/GDS produces
structural signals, not findings. RAG retrieves evidence quickly. RLM performs
deep analysis over selected context. LangGraph coordinates role workflows and
must use the Tool Execution API instead of bypassing policy or runners.

Typed graph projection work must reference a versioned `ProjectionContract`
(`projection name + contract_version`) before adding GDS/Cypher logic.

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

The graph profile includes Neo4j plus two durable projection workers: `graph-projector-events` claims `graph_projection_events` and enqueues GraphFact batches, while `graph-projector` applies pending GraphFact batches into Neo4j. Without both workers, Neo4j remains empty even if scans write PostgreSQL artifacts.

For an existing database that already has artifacts but an empty Neo4j store, rebuild the durable graph batches and let the apply worker drain them:

```bash
docker compose --profile graph run --rm graph-projector rebuild --program-id <program-id>
docker compose --profile graph up -d graph-projector-events graph-projector
```

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

- `docs/architecture/structural-signal-event-model.md` defines the contract-only StructuralSignal event/read-model boundary: signals are not findings or actions.
- [`docs/architecture/hypothesis-from-structural-signal-contract.md`](docs/architecture/hypothesis-from-structural-signal-contract.md) — contract-only `StructuralSignal -> HypothesisProposal` boundary.
