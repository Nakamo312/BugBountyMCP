from __future__ import annotations

import sys
from pathlib import Path


def _parser_command_choices(parser) -> set[str]:
    for action in parser._actions:  # argparse exposes subcommand choices only through the action object.
        if getattr(action, "dest", None) == "command":
            return set(action.choices)
    raise AssertionError("parser does not expose command subparsers")


def test_graph_projector_main_is_thin_entrypoint() -> None:
    source = Path("services/graph-projector/graph_projector/__main__.py").read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 12
    forbidden_tokens = (
        "add_parser",
        "GraphFactBatchApplicator",
        "connect_postgres",
        "GraphProjectorSettings",
        "if args.command",
    )
    for token in forbidden_tokens:
        assert token not in source


def test_graph_projector_cli_responsibilities_have_named_owners() -> None:
    parser_source = Path("services/graph-projector/graph_projector/cli_parser.py").read_text(encoding="utf-8")
    handler_source = Path("services/graph-projector/graph_projector/cli_handlers.py").read_text(encoding="utf-8")
    service_source = Path("services/graph-projector/graph_projector/cli_services.py").read_text(encoding="utf-8")
    factory_source = Path("services/graph-projector/graph_projector/cli_enqueuer_factory.py").read_text(encoding="utf-8")
    output_source = Path("services/graph-projector/graph_projector/cli_output.py").read_text(encoding="utf-8")

    assert "def build_parser" in parser_source
    assert 'subparsers.add_parser("status"' in parser_source
    assert '"process-projection-events": process_projection_events' in handler_source
    assert "class GraphProjectorCli" in handler_source
    assert "def _build_applicator" in service_source
    assert "def _build_projection_event_worker" in service_source
    assert "class GraphFactEnqueuerFactory" in factory_source
    assert "def _print_surface_component_report" in output_source


def test_graph_projector_cli_enqueuer_composition_uses_shared_factory() -> None:
    service_source = Path("services/graph-projector/graph_projector/cli_services.py").read_text(encoding="utf-8")
    factory_source = Path("services/graph-projector/graph_projector/cli_enqueuer_factory.py").read_text(encoding="utf-8")

    assert "class GraphFactEnqueuerFactory" in factory_source
    assert "GraphFactBatchStore(connection)" in factory_source
    assert "lock_seconds=self._settings.batch_lock_seconds" in factory_source
    assert "max_attempts=self._settings.batch_max_attempts" in factory_source

    enqueuer_builder_region = service_source.split("def _build_http_observation_enqueuer", maxsplit=1)[1]
    enqueuer_builder_region = enqueuer_builder_region.split("def _build_rebuild_service", maxsplit=1)[0]
    assert "connect_postgres(settings.postgres_dsn)" not in enqueuer_builder_region
    assert "GraphFactBatchStore(connection)" not in enqueuer_builder_region


def test_graph_projector_batch_commands_use_shared_enqueue_runners() -> None:
    batch_source = Path("services/graph-projector/graph_projector/cli_batch_commands.py").read_text(encoding="utf-8")

    assert "def _run_enqueue_once" in batch_source
    assert "def _run_enqueue_loop" in batch_source
    command_region = batch_source.split("def process_projection_events", maxsplit=1)[0]
    assert command_region.count(".enqueue_pending(") == 1
    assert command_region.count(".run(") == 1


def test_graph_projector_parser_commands_match_handler_registry() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.cli_handlers import GraphProjectorCli
    from graph_projector.cli_parser import build_parser

    parser_commands = _parser_command_choices(build_parser())
    handler_commands = set(GraphProjectorCli.COMMAND_HANDLERS)

    assert parser_commands == handler_commands


def test_graph_projector_parser_preserves_command_shapes() -> None:
    sys.path.insert(0, str(Path("services/graph-projector").resolve()))
    from graph_projector.cli_parser import build_parser

    parser = build_parser()

    assert parser.parse_args(["status", "--program-id", "p1"]).command == "status"
    assert parser.parse_args(["enqueue-http-observations-loop", "--limit", "5", "--program-id", "p1"]).limit == 5
    assert parser.parse_args(["surface-components", "--program-id", "p1", "--snapshot-id", "s1"]).component_limit == 10
    assert parser.parse_args(["rebuild", "--source", "surface_map"]).sources == ["surface_map"]
