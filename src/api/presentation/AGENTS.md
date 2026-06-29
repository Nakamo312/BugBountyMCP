# Presentation Layer Instructions

Presentation code exposes REST and MCP interfaces. It should not become a
shortcut around the control plane.

Read first when changing this layer:

- [Control plane](../../../docs/architecture/control-plane.md)
- [MCP read model](../../../docs/architecture/mcp-read-model.md)

## Rules

- REST/MCP scan requests must go through application services and policy.
- Do not expose arbitrary SQL, shell execution, raw URL proxying, or direct
  runner invocation.
- MCP tools should remain curated and read-oriented unless a tested approval
  flow exists for a specific write action.
- Keep schemas stable and explicit. Do not leak internal ORM rows as public
  contracts by accident.
- Startup should wire services, not create tables or perform migrations.

## Experience and Ranking Boundary

- Do not expose action-experience ranking, GDS probes, graph similarity, or
  internal planner scoring as REST/MCP endpoints.
- Presentation routes may accept explicit human/operator commands such as action
  submission, approval, rejection, and feedback, but must call application
  services instead of infrastructure stores or graph readers directly.
- Dashboard-facing explanations should read persisted proposals or action state;
  they should not trigger Neo4j GDS calculations through request/response APIs.
