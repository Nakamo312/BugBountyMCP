# Refactor Roadmap

This roadmap summarizes how to move the repository toward the MVP described in
[Patch plan to MVP](patch-plan-to-mvp.md). The patch plan remains the source of
truth for detailed acceptance criteria.

## Current Integration State

The active integration branch has moved the project toward:

- action-oriented frontend and API surfaces;
- action schema v2 and typed execution contracts;
- capability catalog and runtime manifest foundations;
- policy split tests and scheduler/runtime tests;
- event dispatcher and event-store dispatch contracts;
- graph-projector service, GraphFact contracts, ontology, Neo4j writer, batch
  store, apply loop, raw artifact enqueue loop, dedupe keys, and notification
  wait support.

Python verification for the current integration state:

```bash
python -m pytest -q
```

## Next Order Of Work

1. Stabilize M1 execution-core gaps.
   Confirm jobs/runs/leases/attempts, transactional outbox, publisher retries,
   runner option propagation, work keys, and campaign lifecycle.

2. Resolve M2 artifact-storage scope.
   Follow the current patch plan. Do not introduce a new artifact storage
   architecture unless the plan explicitly brings it back into MVP.

3. Remove or freeze `research-engine` according to M3.
   The core should not become a pseudo-intelligence service. Hypotheses,
   verifier, critic, and report workflows belong later in LangGraph.

4. Complete M4 graph projection.
   Add remaining producers, graph rebuild command, and safe graph query
   templates before introducing graph analytics.

5. Complete M5 OpenSearch expansion.
   Add versioned indexes, missing target indexes, sanitized producers, and
   projection lag state.

6. Implement M6 async agent protocol.
   Add agent workflows, inbox, wait conditions, result sets, and protocol API.

7. Implement M7 LangGraph workflows.
   Add workflow runtime, read-only context tools, ToolActionRequest tool, human
   approval node, hypothesis builder, critic/verifier, and report draft builder.

## Do Not Skip

- Do not implement LangGraph before projections and result/wait readiness exist.
- Do not implement Neo4j GDS before graph rebuild and query templates exist.
- Do not allow LLMs to bypass policy, RabbitMQ/outbox, or workers.
- Do not promote hypotheses to findings without evidence.
- Do not treat raw artifacts as graph nodes, agent state, or raw search
  documents.
