from __future__ import annotations

import json
from uuid import uuid4



def test_cli_parser_supports_projection_audit() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(
        [
            "--program-id",
            str(uuid4()),
            "projection",
            "audit",
            "--audit-log",
            "audit.jsonl",
            "--step-id",
            "process-search-projection-events",
            "--limit",
            "5",
            "--show-boundary",
        ]
    )

    assert args.command == "projection"
    assert args.projection_command == "audit"
    assert args.audit_log == "audit.jsonl"
    assert args.step_id == "process-search-projection-events"
    assert args.limit == 5
    assert args.show_boundary is True


def test_projection_audit_reader_filters_events(tmp_path) -> None:
    from bb_cli.operator_plan import read_projection_run_step_audit

    program_id = str(uuid4())
    other_program_id = str(uuid4())
    audit_log = tmp_path / "projection-run-step.jsonl"
    events = [
        {
            "audit_id": "a1",
            "created_at": "2026-06-27T00:00:00+00:00",
            "surface": "bb_cli.projection.run_step",
            "program_id": program_id,
            "step_id": "process-search-projection-events",
            "step_title": "Process search events",
            "execute": False,
            "command_count": 1,
            "results": [{"command": "search_indexer process-events", "status": "preview", "allowed": True}],
        },
        {
            "audit_id": "a2",
            "created_at": "2026-06-27T00:01:00+00:00",
            "surface": "bb_cli.projection.run_step",
            "program_id": other_program_id,
            "step_id": "process-search-projection-events",
            "execute": True,
            "command_count": 1,
            "results": [{"command": "search_indexer process-events", "status": "ok", "allowed": True}],
        },
        {"surface": "other"},
    ]
    audit_log.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    data = read_projection_run_step_audit(
        audit_log,
        program_id=program_id,
        step_id="process-search-projection-events",
        limit=10,
    )

    assert data["exists"] is True
    assert data["total_lines"] == 3
    assert data["matched_lines"] == 1
    assert data["events"][0]["audit_id"] == "a1"
    assert data["events"][0]["statuses"] == {"preview": 1}
    assert data["events"][0]["commands"] == ["search_indexer process-events"]


def test_projection_audit_reader_returns_latest_events_first(tmp_path) -> None:
    from bb_cli.operator_plan import read_projection_run_step_audit

    program_id = str(uuid4())
    audit_log = tmp_path / "audit.jsonl"
    lines = []
    for index in range(3):
        lines.append(
            json.dumps(
                {
                    "audit_id": f"a{index}",
                    "created_at": f"2026-06-27T00:0{index}:00+00:00",
                    "surface": "bb_cli.projection.run_step",
                    "program_id": program_id,
                    "step_id": "s",
                    "results": [],
                }
            )
        )
    audit_log.write_text("\n".join(lines), encoding="utf-8")

    data = read_projection_run_step_audit(audit_log, program_id=program_id, limit=2)

    assert [event["audit_id"] for event in data["events"]] == ["a2", "a1"]


def test_render_program_projection_audit_shows_events() -> None:
    from bb_cli.render import render_program_projection_audit

    text = render_program_projection_audit(
        {
            "path": ".bb/audit/projection-run-step.jsonl",
            "exists": True,
            "program_id": str(uuid4()),
            "step_id": "process-search-projection-events",
            "total_lines": 1,
            "matched_lines": 1,
            "skipped_lines": 0,
            "events": [
                {
                    "audit_id": "audit-1",
                    "created_at": "2026-06-27T00:00:00+00:00",
                    "step_id": "process-search-projection-events",
                    "step_title": "Process pending search projection events",
                    "execute": True,
                    "command_count": 1,
                    "statuses": {"ok": 1},
                    "commands": ["search_indexer process-events"],
                }
            ],
            "boundary": {"command_execution": "forbidden"},
        },
        show_boundary=True,
    )

    assert "Program projection run-step audit" in text
    assert "audit-1" in text
    assert "[execute]" in text
    assert "$ search_indexer process-events" in text
    assert "command_execution: forbidden" in text


def test_cli_parser_supports_projection_audit_summary() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(
        [
            "--program-id",
            str(uuid4()),
            "projection",
            "audit-summary",
            "--audit-log",
            "audit.jsonl",
            "--step-id",
            "process-search-projection-events",
            "--limit",
            "7",
            "--show-boundary",
        ]
    )

    assert args.command == "projection"
    assert args.projection_command == "audit-summary"
    assert args.audit_log == "audit.jsonl"
    assert args.step_id == "process-search-projection-events"
    assert args.limit == 7
    assert args.show_boundary is True


def test_projection_audit_summary_aggregates_by_step(tmp_path) -> None:
    from bb_cli.operator_plan import summarize_projection_run_step_audit

    program_id = str(uuid4())
    audit_log = tmp_path / "projection-run-step.jsonl"
    events = [
        {
            "audit_id": "a1",
            "created_at": "2026-06-27T00:00:00+00:00",
            "surface": "bb_cli.projection.run_step",
            "program_id": program_id,
            "step_id": "process-search-projection-events",
            "step_title": "Process search events",
            "execute": False,
            "command_count": 1,
            "results": [{"command": "search_indexer process-events", "status": "preview", "allowed": True}],
        },
        {
            "audit_id": "a2",
            "created_at": "2026-06-27T00:01:00+00:00",
            "surface": "bb_cli.projection.run_step",
            "program_id": program_id,
            "step_id": "process-search-projection-events",
            "step_title": "Process search events",
            "execute": True,
            "command_count": 1,
            "results": [{"command": "search_indexer process-events", "status": "ok", "allowed": True}],
        },
        {
            "audit_id": "a3",
            "created_at": "2026-06-27T00:02:00+00:00",
            "surface": "bb_cli.projection.run_step",
            "program_id": program_id,
            "step_id": "repair-search-projection-events",
            "step_title": "Repair search events",
            "execute": True,
            "command_count": 1,
            "results": [{"command": "search_indexer retry", "status": "failed", "allowed": True}],
        },
    ]
    audit_log.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")

    data = summarize_projection_run_step_audit(audit_log, program_id=program_id, limit=10)

    assert data["exists"] is True
    assert data["matched_lines"] == 3
    assert data["summary"]["total_events"] == 3
    assert data["summary"]["preview_events"] == 1
    assert data["summary"]["execute_events"] == 2
    assert data["summary"]["failed_events"] == 1
    assert data["summary"]["status_counts"] == {"failed": 1, "ok": 1, "preview": 1}
    by_step = {step["step_id"]: step for step in data["steps"]}
    assert by_step["process-search-projection-events"]["total_events"] == 2
    assert by_step["process-search-projection-events"]["status_counts"] == {"ok": 1, "preview": 1}
    assert by_step["repair-search-projection-events"]["failed_events"] == 1


def test_projection_audit_summary_filters_by_step(tmp_path) -> None:
    from bb_cli.operator_plan import summarize_projection_run_step_audit

    program_id = str(uuid4())
    audit_log = tmp_path / "audit.jsonl"
    audit_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "audit_id": "a1",
                        "created_at": "2026-06-27T00:00:00+00:00",
                        "surface": "bb_cli.projection.run_step",
                        "program_id": program_id,
                        "step_id": "s1",
                        "results": [{"status": "preview"}],
                    }
                ),
                json.dumps(
                    {
                        "audit_id": "a2",
                        "created_at": "2026-06-27T00:01:00+00:00",
                        "surface": "bb_cli.projection.run_step",
                        "program_id": program_id,
                        "step_id": "s2",
                        "results": [{"status": "ok"}],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    data = summarize_projection_run_step_audit(audit_log, program_id=program_id, step_id="s2")

    assert data["matched_lines"] == 1
    assert data["steps"][0]["step_id"] == "s2"
    assert data["summary"]["status_counts"] == {"ok": 1}


def test_render_program_projection_audit_summary_shows_totals() -> None:
    from bb_cli.render import render_program_projection_audit_summary

    text = render_program_projection_audit_summary(
        {
            "path": ".bb/audit/projection-run-step.jsonl",
            "exists": True,
            "program_id": str(uuid4()),
            "step_id": None,
            "total_lines": 2,
            "matched_lines": 2,
            "skipped_lines": 0,
            "summary": {
                "total_events": 2,
                "preview_events": 1,
                "execute_events": 1,
                "ok_events": 1,
                "failed_events": 0,
                "blocked_events": 0,
                "command_count": 2,
                "status_counts": {"ok": 1, "preview": 1},
                "last_event_at": "2026-06-27T00:01:00+00:00",
                "last_audit_id": "a2",
                "last_step_id": "s1",
            },
            "steps": [
                {
                    "step_id": "s1",
                    "step_title": "Process search events",
                    "total_events": 2,
                    "preview_events": 1,
                    "execute_events": 1,
                    "failed_events": 0,
                    "command_count": 2,
                    "status_counts": {"ok": 1, "preview": 1},
                    "last_event_at": "2026-06-27T00:01:00+00:00",
                    "last_audit_id": "a2",
                }
            ],
            "boundary": {"command_execution": "forbidden"},
        },
        show_boundary=True,
    )

    assert "Program projection run-step audit summary" in text
    assert "events=2" in text
    assert "s1" in text
    assert "Process search events" in text
    assert "command_execution: forbidden" in text
