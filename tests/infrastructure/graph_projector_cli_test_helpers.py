from __future__ import annotations

from pathlib import Path

GRAPH_PROJECTOR_CLI_SOURCE_PATHS = (
    "services/graph-projector/graph_projector/cli_parser.py",
    "services/graph-projector/graph_projector/cli_handlers.py",
    "services/graph-projector/graph_projector/cli_operational_commands.py",
    "services/graph-projector/graph_projector/cli_batch_commands.py",
    "services/graph-projector/graph_projector/cli_surface_commands.py",
    "services/graph-projector/graph_projector/cli_maintenance_commands.py",
    "services/graph-projector/graph_projector/cli_services.py",
    "services/graph-projector/graph_projector/cli_enqueuer_factory.py",
    "services/graph-projector/graph_projector/cli_output.py",
)


def graph_projector_cli_source() -> str:
    return "\n".join(Path(path).read_text(encoding="utf-8") for path in GRAPH_PROJECTOR_CLI_SOURCE_PATHS)
