from __future__ import annotations

from uuid import uuid4

from bb_cli.client import BbApiClient
from bb_cli.settings import CliSettings

from tests.application.bb_cli_support import RecordingTransport


def test_client_reads_program_projection_overview() -> None:
    transport = RecordingTransport()
    program_id = uuid4()
    client = BbApiClient(CliSettings(api_url="http://testserver", program_id=program_id), transport=transport)

    overview = client.program_projection_overview(program_id=program_id)

    assert overview["program_id"] == str(program_id)
    assert overview["surface_analysis_fresh"] is True
    assert transport.requests[-1].url.path == "/api/v1/program-projection-overview"
    assert transport.requests[-1].url.params["program_id"] == str(program_id)


def test_cli_parser_supports_projection_overview() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(["--program-id", str(uuid4()), "projection", "overview", "--show-boundary"])

    assert args.command == "projection"
    assert args.projection_command == "overview"
    assert args.show_boundary is True


def test_render_program_projection_overview_shows_pipeline_state() -> None:
    from bb_cli.render import render_program_projection_overview

    text = render_program_projection_overview(
        {
            "program_id": str(uuid4()),
            "latest_surface_snapshot": {
                "snapshot_id": str(uuid4()),
                "node_count": 10,
                "edge_count": 12,
                "delta_count": 2,
            },
            "latest_surface_analysis": {
                "analysis_run_id": str(uuid4()),
                "snapshot_id": str(uuid4()),
                "item_count": 3,
            },
            "surface_analysis_fresh": True,
            "search_index_fresh": False,
            "ui_data_fresh": False,
            "graph_projection_events": {"pending": 0, "locked": 0, "processed": 8, "failed": 0, "dead": 0},
            "graph_fact_batches": {"pending": 0, "locked": 0, "processed": 0, "applied": 8, "failed": 0, "dead": 0},
            "surface_analysis_events": {"pending": 0, "locked": 0, "processed": 1, "failed": 0, "dead": 0},
            "search_projection_events": {"pending": 2, "locked": 0, "processed": 0, "failed": 0, "dead": 0},
            "search_index": {
                "surface_components_indexed": False,
                "surface_deltas_indexed": False,
                "latest_surface_components_event_status": "pending",
                "latest_surface_deltas_event_status": "pending",
            },
            "experience_proposals": {"pending": 4, "accepted": 1, "rejected": 2, "suppressed": 1},
            "suggested_commands": ["search_indexer process-events"],
            "boundary": {"gds_execution": "forbidden"},
        },
        show_boundary=True,
    )

    assert "Program projection overview" in text
    assert "surface_analysis=ok" in text
    assert "search_index=stale" in text
    assert "Search projection events" in text
    assert "pending=4" in text
    assert "search_indexer process-events" in text
    assert "gds_execution: forbidden" in text


def test_client_reads_program_projection_plan() -> None:
    transport = RecordingTransport()
    program_id = uuid4()
    client = BbApiClient(CliSettings(api_url="http://testserver", program_id=program_id), transport=transport)

    plan = client.program_projection_plan(program_id=program_id)

    assert plan["program_id"] == str(program_id)
    assert plan["step_count"] == 1
    assert plan["steps"][0]["step_id"] == "process-search-projection-events"
    assert transport.requests[-1].url.path == "/api/v1/program-projection-overview/plan"


def test_cli_parser_supports_projection_plan() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(["--program-id", str(uuid4()), "projection", "plan", "--show-boundary"])

    assert args.command == "projection"
    assert args.projection_command == "plan"
    assert args.show_boundary is True


def test_render_program_projection_plan_shows_ordered_steps() -> None:
    from bb_cli.render import render_program_projection_plan

    text = render_program_projection_plan(
        {
            "program_id": str(uuid4()),
            "ui_data_fresh": False,
            "step_count": 1,
            "steps": [
                {
                    "step_id": "process-search-projection-events",
                    "priority": 70,
                    "severity": "warning",
                    "area": "search_projection",
                    "title": "Process pending search projection events",
                    "reason": "Incremental OpenSearch projection events are pending.",
                    "commands": ["search_indexer process-events"],
                    "blocks_ui_freshness": True,
                }
            ],
            "boundary": {"gds_execution": "forbidden"},
        },
        show_boundary=True,
    )

    assert "Program projection operator plan" in text
    assert "Process pending search projection events" in text
    assert "$ search_indexer process-events" in text
    assert "gds_execution: forbidden" in text
