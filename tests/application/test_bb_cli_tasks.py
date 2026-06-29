from __future__ import annotations

from uuid import uuid4

from bb_cli.client import BbApiClient, runtime_metadata
from bb_cli.render import render_task_detail, render_task_run_agent, render_workspace
from bb_cli.settings import CliSettings

from tests.application.bb_cli_support import RecordingTransport, json_request


def test_runtime_metadata_matches_ui_boundary() -> None:
    metadata = runtime_metadata(mode="deep", deep_confirmed=True, surface="cli.test")

    assert metadata["tool_execution"] == "forbidden_from_prompt"
    assert metadata["agent_runtime_mode"] == "deep"
    assert metadata["deep_mode_confirmed"] is True
    assert metadata["ui_surface"] == "cli.test"


def test_client_creates_agent_task_with_runtime_metadata() -> None:
    transport = RecordingTransport()
    settings = CliSettings(api_url="http://testserver", program_id=uuid4())
    client = BbApiClient(settings, transport=transport)

    created = client.create_agent_task(
        program_id=settings.program_id,
        prompt="разбери новые JS",
        target_agent="artifacts",
        runtime_mode="cheap",
        created_by="cli-test",
    )

    assert created["task"]["target_agent"] == "artifacts"
    request_payload = json_request(transport.requests[-1])
    assert request_payload["metadata"]["agent_runtime_mode"] == "cheap"
    assert request_payload["metadata"]["tool_execution"] == "forbidden_from_prompt"
    assert request_payload["created_by"] == "cli-test"


def test_client_workspace_uses_public_read_model() -> None:
    transport = RecordingTransport()
    program_id = uuid4()
    client = BbApiClient(CliSettings(api_url="http://testserver", program_id=program_id), transport=transport)

    workspace = client.workspace(program_id=program_id)

    assert workspace["counts"]["tasks"] == 0
    assert transport.requests[-1].url.path.endswith("/api/v1/campaign-workspace")
    assert transport.requests[-1].url.params["program_id"] == str(program_id)


def test_renderers_do_not_require_raw_artifacts() -> None:
    workspace_text = render_workspace(
        {
            "program_id": str(uuid4()),
            "campaign_id": None,
            "counts": {"tasks": 1, "pending_agent_proposals": 0, "action_queue": 0, "recent_decisions": 0},
            "agent_runtime_usage": {"selected_modes": {"none": 1, "cheap": 0, "normal": 0, "deep": 0}},
            "tasks": [],
            "pending_agent_proposals": [],
            "action_queue": [],
        }
    )
    detail_text = render_task_detail(
        {
            "task": {"task_id": str(uuid4()), "title": "t", "status": "queued", "target_agent": "coordinator"},
            "messages": [],
            "proposals": [],
            "accepted_actions": [],
            "related_outcomes": [],
            "counts": {},
            "compact_context": {},
        }
    )

    assert "Campaign workspace" in workspace_text
    assert "Agent task" in detail_text
    assert "raw" not in workspace_text.lower()


def test_dev_worker_once_sets_control_plane_environment(monkeypatch) -> None:
    from bb_cli.devloop import run_agent_worker_once

    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "claimed=1 processed=1 failed=0\n"
        stderr = ""

    def fake_run(command, *, env, text, capture_output, timeout, check):
        captured["command"] = command
        captured["env"] = env
        captured["timeout"] = timeout
        return Completed()

    monkeypatch.setattr("subprocess.run", fake_run)
    program_id = uuid4()
    campaign_id = uuid4()
    settings = CliSettings(
        api_url="http://api.local",
        program_id=program_id,
        campaign_id=campaign_id,
        agent_internal_token="secret",
    )

    result = run_agent_worker_once(settings=settings, program_id=program_id, campaign_id=campaign_id, timeout_seconds=7)

    assert result.status == "ok"
    assert result.exit_code == 0
    env = captured["env"]
    assert env["CONTROL_API_BASE_URL"] == "http://api.local"
    assert env["AGENT_WORKER_PROGRAM_ID"] == str(program_id)
    assert env["AGENT_WORKER_CAMPAIGN_ID"] == str(campaign_id)
    assert env["AGENT_PROTOCOL_INTERNAL_TOKEN"] == "secret"
    assert "services/agent-worker" in env["PYTHONPATH"]


def test_render_task_run_agent_shows_worker_and_next_steps() -> None:
    task_id = str(uuid4())
    proposal_id = str(uuid4())
    text = render_task_run_agent(
        {
            "created": {
                "task": {
                    "task_id": task_id,
                    "target_agent": "artifacts",
                    "status": "queued",
                    "prompt_excerpt": "разбери JS",
                },
                "first_message": {"body": "разбери JS"},
            },
            "worker": {
                "status": "ok",
                "exit_code": 0,
                "command": ["python", "-m", "agent_worker", "run-once"],
                "stdout": "claimed=1 processed=1 failed=0",
                "stderr": "",
            },
            "task_detail": {
                "messages": [
                    {"role": "user", "message_kind": "note", "body": "разбери JS"},
                    {
                        "role": "agent",
                        "agent_key": "ArtifactAgent",
                        "message_kind": "finding",
                        "body": "В JavaScript найдено 12 скрытых путей.",
                    },
                ],
                "proposals": [
                    {
                        "proposal_id": proposal_id,
                        "status": "pending",
                        "priority": "medium",
                        "risk_level": "low",
                        "agent_key": "ArtifactAgent",
                        "title": "Разобрать JS-пути",
                        "summary": "Добавить пассивную проверку новых путей.",
                    }
                ],
            },
        }
    )

    assert "Agent task run" in text
    assert "claimed=1 processed=1 failed=0" in text
    assert proposal_id in text
    assert f"bb proposal accept {proposal_id}" in text
    assert f"bb task show {task_id}" in text


def test_task_commands_are_primary_cli_surface() -> None:
    from bb_cli.__main__ import build_parser

    help_text = build_parser().format_help()

    assert "task" in help_text
    assert "proposal" in help_text
    assert "dev" not in help_text
    usage_line = help_text.splitlines()[0]
    assert "agent" not in usage_line


def test_task_create_help_uses_direct_command_name() -> None:
    from bb_cli.__main__ import build_parser

    args = build_parser().parse_args(["--program-id", str(uuid4()), "task", "create", "разбери JS", "--agent", "artifacts"])

    assert args.command == "task"
    assert args.task_command == "create"
    assert args.agent == "artifacts"
