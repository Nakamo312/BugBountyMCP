# Infrastructure Instructions

Infrastructure code talks to external systems: CLI tools, Postgres, RabbitMQ,
filesystem artifacts, MCP transport, and concrete repositories.

Read first when changing this layer:

- [Pipeline boundaries](../../../docs/architecture/pipeline-boundaries.md)
- [MCP read model](../../../docs/architecture/mcp-read-model.md)

## Rules

- Infrastructure may implement concrete adapters, but should not decide
  high-level scan policy.
- Keep command execution, parsing, persistence, and ingestion separated.
- Avoid introducing new direct execution surfaces. Tool execution should stay
  behind capabilities, profiles, policy, and pipeline nodes.
- Do not expose free-form SQL or shell command execution through MCP/API helpers.
- Any storage schema change needs an Alembic migration and tests.
