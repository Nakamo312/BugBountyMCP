from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from uuid import UUID

from .client import BbApiClient, BbApiError
from .operator_plan import read_projection_run_step_audit, run_operator_plan_step, summarize_projection_run_step_audit
from .devloop import run_agent_worker_once
from .render import (
    print_json,
    render_activity,
    render_agent_task_created,
    render_message_created,
    render_program_projection_overview,
    render_program_projection_plan,
    render_program_projection_audit,
    render_program_projection_audit_summary,
    render_program_projection_run_step,
    render_proposal_result,
    render_proposals_from_workspace,
    render_task_detail,
    render_task_run_agent,
    render_tasks,
    render_workspace,
)
from .settings import CliSettings

_AGENT_CHOICES = ["coordinator", "surface", "artifacts", "critic", "report"]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = CliSettings.from_env()
    try:
        with BbApiClient(settings) as client:
            data, renderer = dispatch(args, settings, client)
    except (BbApiError, ValueError) as exc:
        print(f"bb: error: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "json", False):
        print_json(data)
    else:
        print(renderer(data))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bb",
        description="CLI for the research control plane.",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON response")
    parser.add_argument("--program-id", help="program UUID; defaults to BB_PROGRAM_ID")
    parser.add_argument("--campaign-id", help="campaign UUID; defaults to BB_CAMPAIGN_ID")
    sub = parser.add_subparsers(dest="command", required=True)

    workspace = sub.add_parser("workspace", help="show campaign workspace snapshot")
    workspace.add_argument("--task-limit", type=int, default=20)
    workspace.add_argument("--proposal-limit", type=int, default=20)
    workspace.add_argument("--action-limit", type=int, default=20)

    activity = sub.add_parser("activity", help="show incremental agent activity")
    activity.add_argument("--task-id")
    activity.add_argument("--after")
    activity.add_argument("--limit", type=int, default=100)

    task = sub.add_parser("task", help="create, inspect, reply to, and run agent tasks")
    _add_task_commands(task)

    proposal = sub.add_parser("proposal", help="list, accept, reject, or suppress agent proposals")
    _add_proposal_commands(proposal)

    projection = sub.add_parser("projection", help="inspect projection/materialization/search readiness")
    _add_projection_commands(projection)
    return parser


def _add_projection_commands(projection: argparse.ArgumentParser) -> None:
    projection_sub = projection.add_subparsers(dest="projection_command", required=True)

    overview = projection_sub.add_parser(
        "overview",
        help="show read-only end-to-end projection overview for a program",
    )
    overview.add_argument(
        "--show-boundary",
        action="store_true",
        help="include the read-only boundary in text output",
    )

    plan = projection_sub.add_parser(
        "plan",
        help="show ordered read-only operator steps for projection/materialization/search freshness",
    )
    plan.add_argument(
        "--show-boundary",
        action="store_true",
        help="include the read-only boundary in text output",
    )

    run_step = projection_sub.add_parser(
        "run-step",
        help="preview or execute exactly one operator-plan step from the backend plan",
    )
    run_step.add_argument("step_id", help="step_id from `bb projection plan`")
    run_step.add_argument(
        "--command-index",
        type=int,
        action="append",
        default=[],
        help="1-based command index to run; may be repeated; defaults to all commands in the step",
    )
    run_step.add_argument("--execute", action="store_true", help="execute selected commands instead of previewing them")
    run_step.add_argument("--yes", action="store_true", help="required together with --execute")
    run_step.add_argument(
        "--continue-on-error",
        action="store_true",
        help="continue executing remaining commands if one command exits non-zero",
    )
    run_step.add_argument(
        "--show-boundary",
        action="store_true",
        help="include the controlled-execution boundary in text output",
    )
    run_step.add_argument(
        "--audit-log",
        default=".bb/audit/projection-run-step.jsonl",
        help="JSONL audit log path for preview/execute events; default: .bb/audit/projection-run-step.jsonl",
    )
    run_step.add_argument(
        "--no-audit",
        action="store_true",
        help="disable local JSONL audit logging for this run-step invocation",
    )

    audit = projection_sub.add_parser(
        "audit",
        help="show local JSONL audit history for projection run-step invocations",
    )
    audit.add_argument(
        "--audit-log",
        default=".bb/audit/projection-run-step.jsonl",
        help="JSONL audit log path; default: .bb/audit/projection-run-step.jsonl",
    )
    audit.add_argument("--step-id", help="filter audit events by operator step id")
    audit.add_argument("--limit", type=int, default=20, help="maximum events to display")
    audit.add_argument(
        "--show-boundary",
        action="store_true",
        help="include the local audit read boundary in text output",
    )

    audit_summary = projection_sub.add_parser(
        "audit-summary",
        help="summarize local JSONL audit history for projection run-step invocations",
    )
    audit_summary.add_argument(
        "--audit-log",
        default=".bb/audit/projection-run-step.jsonl",
        help="JSONL audit log path; default: .bb/audit/projection-run-step.jsonl",
    )
    audit_summary.add_argument("--step-id", help="filter audit events by operator step id")
    audit_summary.add_argument("--limit", type=int, default=20, help="maximum step summaries to display")
    audit_summary.add_argument(
        "--show-boundary",
        action="store_true",
        help="include the local audit read boundary in text output",
    )


def _add_task_commands(task: argparse.ArgumentParser) -> None:
    task_sub = task.add_subparsers(dest="task_command", required=True)

    create = task_sub.add_parser("create", help="create a bounded agent task from a prompt")
    create.add_argument("prompt")
    create.add_argument("--agent", default="coordinator", choices=_AGENT_CHOICES)
    _add_runtime_args(create)

    list_cmd = task_sub.add_parser("list", help="list agent tasks")
    list_cmd.add_argument("--status")
    list_cmd.add_argument("--limit", type=int, default=100)

    show = task_sub.add_parser("show", help="show one agent task detail")
    show.add_argument("task_id")
    show.add_argument("--message-limit", type=int, default=100)

    reply = task_sub.add_parser("reply", help="append a follow-up prompt to an agent task")
    reply.add_argument("task_id")
    reply.add_argument("body")
    _add_runtime_args(reply)

    run_agent = task_sub.add_parser("run-agent", help="run one external agent-worker sweep")
    run_agent.add_argument("task_id", nargs="?", help="optional task id to show after the worker sweep")
    run_agent.add_argument("--worker-timeout", type=float, default=60.0)
    run_agent.add_argument("--message-limit", type=int, default=100)
    run_agent.add_argument("--worker-command", nargs=argparse.REMAINDER, help="override the worker command; put it last")


def _add_proposal_commands(proposal: argparse.ArgumentParser) -> None:
    proposal_sub = proposal.add_subparsers(dest="proposal_command", required=True)

    list_cmd = proposal_sub.add_parser("list", help="list pending agent proposals from workspace")
    list_cmd.add_argument("--limit", type=int, default=50)

    accept = proposal_sub.add_parser("accept", help="submit a proposal through ActionService")
    accept.add_argument("proposal_id")
    _add_proposal_kind_arg(accept)
    accept.add_argument("--target", action="append", dest="targets", default=[])
    accept.add_argument("--capability-id")
    accept.add_argument("--profile-id")
    accept.add_argument("--reason")
    accept.add_argument("--confidence", type=float, default=0.5)
    accept.add_argument("--option", action="append", default=[], help="JSON object or key=value action option")

    reject = proposal_sub.add_parser("reject", help="reject proposal as feedback")
    reject.add_argument("proposal_id")
    _add_proposal_kind_arg(reject)
    reject.add_argument("--reason")
    reject.add_argument("--confidence", type=float, default=0.5)
    reject.add_argument("--tag", action="append", default=[])

    suppress = proposal_sub.add_parser("suppress", help="suppress similar future proposals")
    suppress.add_argument("proposal_id")
    _add_proposal_kind_arg(suppress)
    suppress.add_argument("--reason")
    suppress.add_argument("--confidence", type=float, default=0.8)
    suppress.add_argument("--tag", action="append", default=[])


def dispatch(args: argparse.Namespace, settings: CliSettings, client: BbApiClient):
    program_id = _program_id(args, settings)
    campaign_id = _campaign_id(args, settings)
    if args.command == "workspace":
        return client.workspace(
            program_id=program_id,
            campaign_id=campaign_id,
            task_limit=args.task_limit,
            proposal_limit=args.proposal_limit,
            action_limit=args.action_limit,
        ), render_workspace
    if args.command == "activity":
        task_id = UUID(args.task_id) if args.task_id else None
        return client.activity(
            program_id=program_id,
            campaign_id=campaign_id,
            task_id=task_id,
            after=args.after,
            limit=args.limit,
        ), render_activity
    if args.command == "task":
        return _dispatch_task(args, settings, client, program_id, campaign_id)
    if args.command == "proposal":
        return _dispatch_proposal(args, settings, client, program_id, campaign_id)
    if args.command == "projection":
        return _dispatch_projection(args, client, program_id)
    raise ValueError(f"unknown command: {args.command}")


def _dispatch_projection(args: argparse.Namespace, client: BbApiClient, program_id: UUID):
    if args.projection_command == "overview":
        return client.program_projection_overview(program_id=program_id), lambda data: render_program_projection_overview(
            data,
            show_boundary=args.show_boundary,
        )
    if args.projection_command == "plan":
        return client.program_projection_plan(program_id=program_id), lambda data: render_program_projection_plan(
            data,
            show_boundary=args.show_boundary,
        )
    if args.projection_command == "run-step":
        plan = client.program_projection_plan(program_id=program_id)
        audit_log_path = None if args.no_audit else args.audit_log
        result = run_operator_plan_step(
            plan,
            step_id=args.step_id,
            command_indexes=args.command_index,
            execute=args.execute,
            confirmed=args.yes,
            continue_on_error=args.continue_on_error,
            audit_log_path=audit_log_path,
        )
        return result, lambda data: render_program_projection_run_step(
            data,
            show_boundary=args.show_boundary,
        )
    if args.projection_command == "audit":
        result = read_projection_run_step_audit(
            args.audit_log,
            program_id=str(program_id),
            step_id=args.step_id,
            limit=args.limit,
        )
        return result, lambda data: render_program_projection_audit(
            data,
            show_boundary=args.show_boundary,
        )
    if args.projection_command == "audit-summary":
        result = summarize_projection_run_step_audit(
            args.audit_log,
            program_id=str(program_id),
            step_id=args.step_id,
            limit=args.limit,
        )
        return result, lambda data: render_program_projection_audit_summary(
            data,
            show_boundary=args.show_boundary,
        )
    raise ValueError(f"unknown projection command: {args.projection_command}")


def _dispatch_task(
    args: argparse.Namespace,
    settings: CliSettings,
    client: BbApiClient,
    program_id: UUID,
    campaign_id: UUID | None,
):
    if args.task_command == "create":
        return _create_task(args, settings, client, program_id, campaign_id)
    if args.task_command == "list":
        return _list_tasks(args, client, program_id, campaign_id)
    if args.task_command == "show":
        return client.task_detail(task_id=UUID(args.task_id), message_limit=args.message_limit), render_task_detail
    if args.task_command == "reply":
        return _reply_task(args, settings, client)
    if args.task_command == "run-agent":
        return _run_agent_for_task(args, settings, client, program_id, campaign_id)
    raise ValueError(f"unknown task command: {args.task_command}")


def _create_task(
    args: argparse.Namespace,
    settings: CliSettings,
    client: BbApiClient,
    program_id: UUID,
    campaign_id: UUID | None,
):
    _require_deep_confirmation(args)
    return client.create_agent_task(
        program_id=program_id,
        campaign_id=campaign_id,
        prompt=args.prompt,
        target_agent=args.agent,
        created_by=settings.created_by,
        runtime_mode=args.mode,
        deep_confirmed=args.deep_confirmed,
    ), render_agent_task_created


def _list_tasks(args: argparse.Namespace, client: BbApiClient, program_id: UUID, campaign_id: UUID | None):
    return client.list_agent_tasks(
        program_id=program_id,
        campaign_id=campaign_id,
        status=args.status,
        limit=args.limit,
    ), render_tasks


def _reply_task(args: argparse.Namespace, settings: CliSettings, client: BbApiClient):
    _require_deep_confirmation(args)
    return client.reply_agent_task(
        task_id=UUID(args.task_id),
        body=args.body,
        created_by=settings.created_by,
        runtime_mode=args.mode,
        deep_confirmed=args.deep_confirmed,
    ), render_message_created


def _run_agent_for_task(
    args: argparse.Namespace,
    settings: CliSettings,
    client: BbApiClient,
    program_id: UUID,
    campaign_id: UUID | None,
):
    worker = run_agent_worker_once(
        settings=settings,
        program_id=program_id,
        campaign_id=campaign_id,
        command=args.worker_command or None,
        timeout_seconds=args.worker_timeout,
    )
    task_detail = None
    if args.task_id:
        task_detail = client.task_detail(task_id=UUID(args.task_id), message_limit=args.message_limit)
    return {"worker": worker.as_payload(), "task_detail": task_detail}, render_task_run_agent


def _add_proposal_kind_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--kind",
        choices=["agent", "experience"],
        default="agent",
        help="proposal source: agent-action proposal or graph/GDS action-experience proposal",
    )


def _dispatch_proposal(
    args: argparse.Namespace,
    settings: CliSettings,
    client: BbApiClient,
    program_id: UUID,
    campaign_id: UUID | None,
):
    if args.proposal_command == "list":
        return _list_proposals(args, client, program_id, campaign_id)
    proposal_id = UUID(args.proposal_id)
    if args.proposal_command == "accept":
        return client.accept_proposal(
            proposal_id=proposal_id,
            accepted_by=settings.created_by,
            reason=args.reason,
            confidence=args.confidence,
            proposal_kind=args.kind,
            capability_id=args.capability_id,
            profile_id=args.profile_id,
            targets=args.targets,
            options=_parse_options(args.option),
        ), lambda data: render_proposal_result(data, action="accepted")
    if args.proposal_command == "reject":
        return client.review_proposal(
            proposal_id=proposal_id,
            decision="reject",
            reviewed_by=settings.created_by,
            reason=args.reason,
            confidence=args.confidence,
            proposal_kind=args.kind,
            feedback_tags=args.tag,
        ), lambda data: render_proposal_result(data, action="rejected")
    if args.proposal_command == "suppress":
        return client.review_proposal(
            proposal_id=proposal_id,
            decision="suppress",
            reviewed_by=settings.created_by,
            reason=args.reason,
            confidence=args.confidence,
            proposal_kind=args.kind,
            feedback_tags=args.tag,
        ), lambda data: render_proposal_result(data, action="suppressed")
    raise ValueError(f"unknown proposal command: {args.proposal_command}")


def _list_proposals(args: argparse.Namespace, client: BbApiClient, program_id: UUID, campaign_id: UUID | None):
    return client.workspace(
        program_id=program_id,
        campaign_id=campaign_id,
        proposal_limit=args.limit,
    ), render_proposals_from_workspace


def _add_runtime_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", default="none", choices=["none", "cheap", "normal", "deep"], help="agent runtime mode")
    parser.add_argument("--deep-confirmed", action="store_true", help="explicitly confirm deep runtime mode")


def _require_deep_confirmation(args: argparse.Namespace) -> None:
    if args.mode == "deep" and not args.deep_confirmed:
        raise ValueError("deep mode requires --deep-confirmed; backend policy may still downgrade it")


def _program_id(args: argparse.Namespace, settings: CliSettings) -> UUID:
    value = getattr(args, "program_id", None)
    if value:
        return UUID(value)
    if settings.program_id is not None:
        return settings.program_id
    raise ValueError("program id required: pass --program-id or set BB_PROGRAM_ID")


def _campaign_id(args: argparse.Namespace, settings: CliSettings) -> UUID | None:
    value = getattr(args, "campaign_id", None)
    if value:
        return UUID(value)
    return settings.campaign_id


def _parse_options(items: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for item in items:
        stripped = item.strip()
        if not stripped:
            continue
        if stripped.startswith("{"):
            parsed = json.loads(stripped)
            if not isinstance(parsed, dict):
                raise ValueError("--option JSON must be an object")
            options.update(parsed)
            continue
        if "=" not in stripped:
            raise ValueError("--option must be JSON object or key=value")
        key, value = stripped.split("=", 1)
        options[key.strip()] = _parse_scalar(value.strip())
    return options


def _parse_scalar(value: str) -> Any:
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


if __name__ == "__main__":
    raise SystemExit(main())
