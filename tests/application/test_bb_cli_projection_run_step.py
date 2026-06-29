from __future__ import annotations

import json
from uuid import uuid4



def test_cli_parser_supports_projection_run_step_preview() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(
        ["--program-id", str(uuid4()), "projection", "run-step", "process-search-projection-events", "--command-index", "1"]
    )

    assert args.command == "projection"
    assert args.projection_command == "run-step"
    assert args.step_id == "process-search-projection-events"
    assert args.command_index == [1]
    assert args.execute is False


def test_projection_run_step_previews_allowlisted_plan_command() -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    program_id = uuid4()
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "process-search-projection-events",
                "priority": 70,
                "severity": "warning",
                "area": "search_projection",
                "title": "Process pending search projection events",
                "reason": "pending",
                "commands": [f"python -m search_indexer process-events --program-id {program_id}"],
            }
        ],
    }

    result = run_operator_plan_step(plan, step_id="process-search-projection-events")

    assert result["execute"] is False
    assert result["results"][0]["status"] == "preview"
    assert result["results"][0]["allowed"] is True
    assert result["results"][0]["argv"][:4] == ["python", "-m", "search_indexer", "process-events"]


def test_projection_run_step_keeps_legacy_console_script_commands_allowlisted() -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    program_id = uuid4()
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "legacy",
                "commands": [f"search_indexer process-events --program-id {program_id}"],
            }
        ],
    }

    result = run_operator_plan_step(plan, step_id="legacy")

    assert result["results"][0]["status"] == "preview"
    assert result["results"][0]["allowed"] is True


def test_projection_run_step_blocks_non_allowlisted_command_in_preview() -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    plan = {
        "program_id": str(uuid4()),
        "steps": [
            {
                "step_id": "bad",
                "priority": 1,
                "severity": "critical",
                "area": "test",
                "title": "bad",
                "reason": "bad",
                "commands": ["rm -rf /"],
            }
        ],
    }

    result = run_operator_plan_step(plan, step_id="bad")

    assert result["results"][0]["status"] == "blocked"
    assert result["results"][0]["allowed"] is False




def test_projection_run_step_allows_only_read_only_bb_commands() -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    program_id = uuid4()
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "review",
                "commands": [
                    f"python -m bb_cli --program-id {program_id} proposal list",
                    f"python -m bb_cli --program-id {program_id} projection overview",
                    f"python -m bb_cli --program-id {program_id} proposal accept 00000000-0000-0000-0000-000000000000",
                    f"python -m bb_cli --program-id {program_id} projection run-step process-search-projection-events --execute --yes",
                ],
            }
        ],
    }

    result = run_operator_plan_step(plan, step_id="review")

    assert [item["allowed"] for item in result["results"]] == [True, True, False, False]
    assert result["results"][2]["status"] == "blocked"
    assert result["results"][3]["status"] == "blocked"


def test_projection_run_step_rejects_extra_positionals_and_unknown_options() -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    program_id = uuid4()
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "strict-command-shape",
                "commands": [
                    f"python -m search_indexer process-events --program-id {program_id}",
                    f"python -m search_indexer process-events unexpected --program-id {program_id}",
                    f"python -m search_indexer process-events --unknown-option {program_id}",
                    "python -m search_indexer process-events --program-id",
                    f"python -m bb_cli --program-id {program_id} proposal list extra",
                ],
            }
        ],
    }

    result = run_operator_plan_step(plan, step_id="strict-command-shape")

    assert [item["allowed"] for item in result["results"]] == [True, False, False, False, False]
    assert [item["status"] for item in result["results"]] == ["preview", "blocked", "blocked", "blocked", "blocked"]


def test_projection_run_step_boundary_reports_strict_command_shape() -> None:
    from bb_cli.operator_plan import projection_run_step_boundary

    boundary = projection_run_step_boundary()

    assert boundary["extra_positional_args"] == "forbidden"
    assert boundary["unknown_options"] == "forbidden"
    assert "--program-id" in boundary["allowed_options_with_values"]


def test_projection_run_step_execute_requires_yes() -> None:
    import pytest
    from bb_cli.operator_plan import run_operator_plan_step

    plan = {
        "program_id": str(uuid4()),
        "steps": [
            {
                "step_id": "s",
                "commands": ["search_indexer process-events --program-id 00000000-0000-0000-0000-000000000000"],
            }
        ],
    }

    with pytest.raises(ValueError, match="--yes"):
        run_operator_plan_step(plan, step_id="s", execute=True, confirmed=False)


def test_projection_run_step_executes_allowlisted_command(monkeypatch) -> None:
    from types import SimpleNamespace

    from bb_cli.operator_plan import run_operator_plan_step

    calls: list[list[str]] = []

    def fake_runner(argv, *, text, capture_output, check):
        calls.append(list(argv))
        return SimpleNamespace(returncode=0, stdout="processed=1\n", stderr="")

    program_id = uuid4()
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "process-search-projection-events",
                "priority": 70,
                "severity": "warning",
                "area": "search_projection",
                "title": "Process pending search projection events",
                "reason": "pending",
                "commands": [f"search_indexer process-events --program-id {program_id}"],
            }
        ],
    }

    result = run_operator_plan_step(
        plan,
        step_id="process-search-projection-events",
        execute=True,
        confirmed=True,
        runner=fake_runner,
    )

    assert calls == [["search_indexer", "process-events", "--program-id", str(program_id)]]
    assert result["results"][0]["status"] == "ok"
    assert result["results"][0]["stdout"] == "processed=1\n"


def test_render_program_projection_run_step_shows_preview_boundary() -> None:
    from bb_cli.render import render_program_projection_run_step

    text = render_program_projection_run_step(
        {
            "program_id": str(uuid4()),
            "step": {
                "step_id": "process-search-projection-events",
                "severity": "warning",
                "title": "Process pending search projection events",
                "reason": "pending",
            },
            "execute": False,
            "results": [
                {
                    "command": "search_indexer process-events --program-id 00000000-0000-0000-0000-000000000000",
                    "status": "preview",
                    "allowed": True,
                }
            ],
            "boundary": {"shell_execution": "forbidden"},
        },
        show_boundary=True,
    )

    assert "Program projection operator step" in text
    assert "Preview only" in text
    assert "shell_execution: forbidden" in text

def test_projection_run_step_writes_jsonl_audit_event(tmp_path) -> None:
    from bb_cli.operator_plan import run_operator_plan_step

    program_id = uuid4()
    audit_log = tmp_path / "projection-run-step.jsonl"
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "process-search-projection-events",
                "priority": 70,
                "severity": "warning",
                "area": "search_projection",
                "title": "Process pending search projection events",
                "reason": "pending",
                "commands": [f"search_indexer process-events --program-id {program_id}"],
            }
        ],
    }

    result = run_operator_plan_step(
        plan,
        step_id="process-search-projection-events",
        audit_log_path=audit_log,
    )

    assert result["audit"]["enabled"] is True
    assert result["audit"]["path"] == str(audit_log)
    lines = audit_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["surface"] == "bb_cli.projection.run_step"
    assert event["program_id"] == str(program_id)
    assert event["step_id"] == "process-search-projection-events"
    assert event["execute"] is False
    assert event["results"][0]["status"] == "preview"
    assert event["results"][0]["argv"][:2] == ["search_indexer", "process-events"]


def test_projection_run_step_audit_bounds_stdout_stderr(tmp_path) -> None:
    from types import SimpleNamespace

    from bb_cli.operator_plan import run_operator_plan_step

    def fake_runner(argv, *, text, capture_output, check):
        return SimpleNamespace(returncode=0, stdout="x" * 5000, stderr="y" * 5000)

    program_id = uuid4()
    audit_log = tmp_path / "audit.jsonl"
    plan = {
        "program_id": str(program_id),
        "steps": [
            {
                "step_id": "process-search-projection-events",
                "commands": [f"search_indexer process-events --program-id {program_id}"],
            }
        ],
    }

    run_operator_plan_step(
        plan,
        step_id="process-search-projection-events",
        execute=True,
        confirmed=True,
        runner=fake_runner,
        audit_log_path=audit_log,
    )

    event = json.loads(audit_log.read_text(encoding="utf-8"))
    assert len(event["results"][0]["stdout_excerpt"]) == 4001
    assert event["results"][0]["stdout_excerpt"].endswith("…")
    assert len(event["results"][0]["stderr_excerpt"]) == 4001


def test_cli_parser_supports_projection_run_step_audit_flags() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(
        [
            "--program-id",
            str(uuid4()),
            "projection",
            "run-step",
            "process-search-projection-events",
            "--audit-log",
            "audit.jsonl",
            "--no-audit",
        ]
    )

    assert args.audit_log == "audit.jsonl"
    assert args.no_audit is True


def test_render_program_projection_run_step_shows_audit_path() -> None:
    from bb_cli.render import render_program_projection_run_step

    text = render_program_projection_run_step(
        {
            "program_id": str(uuid4()),
            "step": {"step_id": "s", "severity": "warning", "title": "Step", "reason": "pending"},
            "execute": False,
            "results": [],
            "audit": {"enabled": True, "path": ".bb/audit/projection-run-step.jsonl", "audit_id": "audit-1"},
        }
    )

    assert "Audit" in text
    assert "audit_id=audit-1" in text
    assert ".bb/audit/projection-run-step.jsonl" in text
