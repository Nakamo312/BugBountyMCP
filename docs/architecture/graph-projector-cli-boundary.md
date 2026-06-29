# Graph Projector CLI Boundary

`python -m graph_projector` is an operational entrypoint, not the graph
projector application itself.

The entrypoint must stay thin:

```text
__main__.py -> cli_app.main -> cli_parser.build_parser -> GraphProjectorCli
```

Responsibilities:

- `__main__.py` imports the application-level CLI entrypoint and exits with its
  return code.
- `cli_parser.py` owns argparse command registration and CLI option shape.
- `cli_handlers.py` owns command dispatch only.
- `cli_operational_commands.py` owns config/status/diagnostics/health command
  handlers.
- `cli_batch_commands.py` owns GraphFact batch application and canonical enqueue
  command handlers.
- `cli_surface_commands.py` owns action-experience and Surface Map component
  command handlers.
- `cli_maintenance_commands.py` owns retry/rebuild command handlers.
- `cli_services.py` owns runtime service construction from settings. Do not add one bespoke builder for every canonical producer when the construction pattern is shared.
- `cli_enqueuer_factory.py` owns the repeated canonical GraphFact enqueuer composition pattern: Postgres connection, `GraphFactBatchStore`, producer, worker id, lock seconds, and attempt budget.
- `cli_batch_commands.py` owns batch/apply/enqueue command handlers, but repeated once/loop enqueue mechanics must go through shared helper runners rather than copy-pasted command bodies.
- `cli_output.py` owns human-readable CLI rendering helpers.

Do not add Neo4j/Postgres wiring, command branches, loops, or formatter logic to
`__main__.py`. Add new commands by registering argparse shape in `cli_parser.py`,
adding a handler in the narrow command module, and wiring it through
`GraphProjectorCli.COMMAND_HANDLERS`. Parser command choices and
`GraphProjectorCli.COMMAND_HANDLERS.keys()` must stay equal; a command accepted
by argparse must never fail later because dispatch forgot its handler.

The CLI may operate projector queues, rebuilds, diagnostics, and read models. It
must not bypass domain boundaries: graph math remains a structural signal layer,
PostgreSQL remains the source of truth, and action execution still goes through
ActionService rather than arbitrary graph-projector commands.

## Growth guardrails

`cli_services.py` is still a composition root. Keep it narrow. New service builders are allowed only when they wire a distinct runtime service. If a new canonical producer follows the existing GraphFact enqueue shape, add it through `GraphFactEnqueuerFactory` instead of copying a new `_build_*_enqueuer` body.

`cli_batch_commands.py` should keep named command functions for dispatch readability, but the repeated once/loop mechanics belong in shared runners. Do not add a new hand-written enqueue once/loop pair unless the command has different behavior, not just a different producer or setting name.

Simple operational commands should not pay for every graph-projector runtime import long term. Lazy service imports remain a future startup cleanup, not part of the CLI boundary itself.
