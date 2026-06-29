from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


_ALLOWED_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("graph_projector", "diagnostics"),
    ("graph_projector", "retry"),
    ("graph_projector", "process-projection-events"),
    ("graph_projector", "apply-one"),
    ("graph_projector", "process-surface-analysis-events"),
    ("graph_projector", "surface-components-materialize"),
    ("search_indexer", "diagnostics"),
    ("search_indexer", "retry"),
    ("search_indexer", "process-events"),
    ("search_indexer", "reindex"),
)

_BB_ALLOWED_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("proposal", "list"),
    ("projection", "overview"),
)

_PYTHON_MODULE_COMMAND_ROOTS = frozenset({"python", "python3"})
_MODULE_COMMANDS = frozenset({"graph_projector", "search_indexer"})
_BB_MODULE = "bb_cli"

_OPTIONS_WITH_VALUES = frozenset({
    "--program-id",
    "--target",
    "--analysis-run-id",
    "--snapshot-id",
    "--queue",
    "--kind",
    "--api-url",
    "--campaign-id",
})


@dataclass(frozen=True)
class CommandShape:
    non_option_tokens: tuple[str, ...]
    options: dict[str, str]


@dataclass(frozen=True)
class OperatorCommandResult:
    command: str
    argv: list[str]
    allowed: bool
    status: str
    returncode: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "argv": self.argv,
            "allowed": self.allowed,
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }


class OperatorStepNotFound(ValueError):
    """Raised when an operator plan step id does not exist."""


class OperatorCommandNotAllowed(ValueError):
    """Raised when an operator plan command is outside the allow-list."""


def run_operator_plan_step(
    plan: dict[str, Any],
    *,
    step_id: str,
    command_indexes: Iterable[int] | None = None,
    execute: bool = False,
    confirmed: bool = False,
    continue_on_error: bool = False,
    runner=subprocess.run,
    audit_log_path: str | Path | None = None,
) -> dict[str, Any]:
    """Preview or execute one operator-plan step through an explicit allow-list.

    The input plan is the read-only backend plan. This helper never invents
    commands. It selects commands already present in the plan, validates their
    argv shape, and either returns a preview or executes them without a shell.
    """

    step = _find_step(plan, step_id)
    commands = _select_commands(step.get("commands") or [], command_indexes=command_indexes)
    if execute and not confirmed:
        raise ValueError("projection run-step requires --yes when --execute is used")

    results: list[OperatorCommandResult] = []
    for command in commands:
        argv = shlex.split(command)
        allowed = _is_allowed_argv(argv)
        if not allowed:
            result = OperatorCommandResult(
                command=command,
                argv=argv,
                allowed=False,
                status="blocked",
                error="command is not in the projection operator allow-list",
            )
            results.append(result)
            if execute:
                raise OperatorCommandNotAllowed(f"operator command is not allowed: {command}")
            continue

        if not execute:
            results.append(OperatorCommandResult(command=command, argv=argv, allowed=True, status="preview"))
            continue

        completed = runner(argv, text=True, capture_output=True, check=False)
        status = "ok" if completed.returncode == 0 else "failed"
        result = OperatorCommandResult(
            command=command,
            argv=argv,
            allowed=True,
            status=status,
            returncode=int(completed.returncode),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        results.append(result)
        if completed.returncode != 0 and not continue_on_error:
            break

    response = {
        "program_id": plan.get("program_id"),
        "step": step,
        "execute": execute,
        "confirmed": confirmed,
        "continue_on_error": continue_on_error,
        "command_count": len(commands),
        "results": [result.as_dict() for result in results],
        "boundary": projection_run_step_boundary(),
    }
    response["audit"] = _write_audit_event(
        response,
        audit_log_path=audit_log_path,
        command_indexes=list(command_indexes or []),
    )
    return response



def read_projection_run_step_audit(
    audit_log_path: str | Path,
    *,
    program_id: str | None = None,
    step_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Read local projection run-step JSONL audit events.

    This is a local, read-only helper for operator visibility. It never calls
    the backend, never runs commands, and tolerates malformed lines by exposing
    them as skipped records rather than failing the whole read.
    """

    path = Path(audit_log_path).expanduser()
    if limit < 1:
        raise ValueError("audit limit must be >= 1")

    events: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    total_lines = 0
    matched_lines = 0

    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "program_id": program_id,
            "step_id": step_id,
            "limit": limit,
            "total_lines": 0,
            "matched_lines": 0,
            "skipped_lines": 0,
            "events": [],
            "boundary": projection_audit_boundary(),
        }

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        total_lines += 1
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            skipped.append({"line_number": line_number, "error": str(exc)})
            continue
        if not isinstance(event, dict):
            skipped.append({"line_number": line_number, "error": "audit line is not a JSON object"})
            continue
        if event.get("surface") != "bb_cli.projection.run_step":
            continue
        if program_id is not None and str(event.get("program_id")) != str(program_id):
            continue
        if step_id is not None and str(event.get("step_id")) != str(step_id):
            continue
        matched_lines += 1
        events.append(_compact_audit_event(event))

    selected = list(reversed(events[-limit:]))
    return {
        "path": str(path),
        "exists": True,
        "program_id": program_id,
        "step_id": step_id,
        "limit": limit,
        "total_lines": total_lines,
        "matched_lines": matched_lines,
        "skipped_lines": len(skipped),
        "skipped": skipped[-10:],
        "events": selected,
        "boundary": projection_audit_boundary(),
    }



def summarize_projection_run_step_audit(
    audit_log_path: str | Path,
    *,
    program_id: str | None = None,
    step_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Summarize local projection run-step JSONL audit events.

    This read-only helper aggregates local operator-run audit history by step.
    It never calls the backend, never executes commands, and uses the same
    tolerant JSONL parsing semantics as ``read_projection_run_step_audit``.
    """

    path = Path(audit_log_path).expanduser()
    if limit < 1:
        raise ValueError("audit summary limit must be >= 1")

    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "program_id": program_id,
            "step_id": step_id,
            "limit": limit,
            "total_lines": 0,
            "matched_lines": 0,
            "skipped_lines": 0,
            "summary": _empty_audit_summary(),
            "steps": [],
            "boundary": projection_audit_boundary(),
        }

    skipped: list[dict[str, Any]] = []
    total_lines = 0
    matched_lines = 0
    steps: dict[str, dict[str, Any]] = {}
    summary = _empty_audit_summary()

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        total_lines += 1
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            skipped.append({"line_number": line_number, "error": str(exc)})
            continue
        if not isinstance(event, dict):
            skipped.append({"line_number": line_number, "error": "audit line is not a JSON object"})
            continue
        if event.get("surface") != "bb_cli.projection.run_step":
            continue
        if program_id is not None and str(event.get("program_id")) != str(program_id):
            continue
        if step_id is not None and str(event.get("step_id")) != str(step_id):
            continue

        matched_lines += 1
        compact = _compact_audit_event(event)
        _apply_audit_event_to_summary(summary, compact)
        step_key = str(compact.get("step_id") or "unknown")
        step = steps.setdefault(step_key, _empty_step_audit_summary(step_key))
        _apply_audit_event_to_summary(step, compact)
        step["step_title"] = compact.get("step_title") or step.get("step_title")
        step["step_severity"] = compact.get("step_severity") or step.get("step_severity")

    ordered_steps = sorted(
        steps.values(),
        key=lambda item: (str(item.get("last_event_at") or ""), int(item.get("total_events") or 0)),
        reverse=True,
    )[:limit]
    return {
        "path": str(path),
        "exists": True,
        "program_id": program_id,
        "step_id": step_id,
        "limit": limit,
        "total_lines": total_lines,
        "matched_lines": matched_lines,
        "skipped_lines": len(skipped),
        "skipped": skipped[-10:],
        "summary": summary,
        "steps": ordered_steps,
        "boundary": projection_audit_boundary(),
    }


def _empty_audit_summary() -> dict[str, Any]:
    return {
        "total_events": 0,
        "preview_events": 0,
        "execute_events": 0,
        "failed_events": 0,
        "blocked_events": 0,
        "ok_events": 0,
        "command_count": 0,
        "status_counts": {},
        "last_event_at": None,
        "last_audit_id": None,
        "last_step_id": None,
    }


def _empty_step_audit_summary(step_id: str) -> dict[str, Any]:
    data = _empty_audit_summary()
    data["step_id"] = step_id
    data["step_title"] = None
    data["step_severity"] = None
    return data


def _apply_audit_event_to_summary(summary: dict[str, Any], event: dict[str, Any]) -> None:
    summary["total_events"] = int(summary.get("total_events") or 0) + 1
    if event.get("execute"):
        summary["execute_events"] = int(summary.get("execute_events") or 0) + 1
    else:
        summary["preview_events"] = int(summary.get("preview_events") or 0) + 1
    summary["command_count"] = int(summary.get("command_count") or 0) + int(event.get("command_count") or 0)

    statuses = event.get("statuses") or {}
    status_counts = summary.setdefault("status_counts", {})
    for status, count in statuses.items():
        status_key = str(status)
        status_counts[status_key] = int(status_counts.get(status_key) or 0) + int(count or 0)

    has_failed = any(status in statuses for status in ("failed", "blocked"))
    has_blocked = "blocked" in statuses
    has_ok = bool(statuses.get("ok")) and not has_failed
    if has_failed:
        summary["failed_events"] = int(summary.get("failed_events") or 0) + 1
    if has_blocked:
        summary["blocked_events"] = int(summary.get("blocked_events") or 0) + 1
    if has_ok:
        summary["ok_events"] = int(summary.get("ok_events") or 0) + 1

    created_at = event.get("created_at")
    if created_at and (summary.get("last_event_at") is None or str(created_at) >= str(summary.get("last_event_at"))):
        summary["last_event_at"] = created_at
        summary["last_audit_id"] = event.get("audit_id")
        summary["last_step_id"] = event.get("step_id")

def projection_audit_boundary() -> dict[str, Any]:
    return {
        "surface": "cli_local_projection_run_step_audit",
        "source": "local_jsonl_file",
        "default_path": ".bb/audit/projection-run-step.jsonl",
        "read_only": True,
        "backend_calls": "none",
        "command_execution": "forbidden",
        "action_submission": "not_performed_by_projection_audit",
        "tool_execution": "forbidden",
    }


def _compact_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    results = event.get("results") or []
    statuses: dict[str, int] = {}
    commands: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        status = str(result.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        command = result.get("command")
        if command is not None:
            commands.append(str(command))
    return {
        "audit_id": event.get("audit_id"),
        "created_at": event.get("created_at"),
        "program_id": event.get("program_id"),
        "step_id": event.get("step_id"),
        "step_title": event.get("step_title"),
        "step_severity": event.get("step_severity"),
        "execute": bool(event.get("execute")),
        "confirmed": bool(event.get("confirmed")),
        "continue_on_error": bool(event.get("continue_on_error")),
        "command_count": int(event.get("command_count") or len(results)),
        "statuses": statuses,
        "commands": commands,
        "results": results,
    }

def projection_run_step_boundary() -> dict[str, Any]:
    return {
        "surface": "cli_controlled_operator_step",
        "command_source": "ProgramProjectionOperatorPlan.steps[].commands",
        "command_execution_default": "preview_only",
        "execute_requires": "--execute and --yes",
        "shell_execution": "forbidden",
        "allowed_command_forms": ["python -m graph_projector <command>", "python -m search_indexer <command>", "python -m bb_cli <read-only-command>"],
        "legacy_allowed_command_roots": ["graph_projector", "search_indexer", "bb"],
        "allowed_command_pairs": ["python -m " + " ".join(pair) for pair in _ALLOWED_COMMANDS],
        "allowed_bb_commands": ["python -m bb_cli " + " ".join(command) for command in _BB_ALLOWED_COMMANDS],
        "allowed_options_with_values": sorted(_OPTIONS_WITH_VALUES),
        "extra_positional_args": "forbidden",
        "unknown_options": "forbidden",
        "action_submission": "not_performed_by_projection_run_step",
        "tool_execution": "only_indirectly_via_selected_existing_ops_command",
        "audit_semantics": "local_jsonl_event_when_configured",
    }



def _write_audit_event(
    response: dict[str, Any],
    *,
    audit_log_path: str | Path | None,
    command_indexes: list[int],
) -> dict[str, Any]:
    if audit_log_path is None:
        return {"enabled": False}

    path = Path(audit_log_path).expanduser()
    event = {
        "audit_id": str(uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "surface": "bb_cli.projection.run_step",
        "program_id": response.get("program_id"),
        "step_id": (response.get("step") or {}).get("step_id"),
        "step_title": (response.get("step") or {}).get("title"),
        "step_severity": (response.get("step") or {}).get("severity"),
        "execute": bool(response.get("execute")),
        "confirmed": bool(response.get("confirmed")),
        "continue_on_error": bool(response.get("continue_on_error")),
        "command_indexes": command_indexes,
        "command_count": int(response.get("command_count") or 0),
        "results": [_audit_result(result) for result in response.get("results") or []],
        "boundary": response.get("boundary") or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return {"enabled": True, "path": str(path), "audit_id": event["audit_id"]}


def _audit_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "command": result.get("command"),
        "argv": result.get("argv") or [],
        "allowed": bool(result.get("allowed")),
        "status": result.get("status"),
        "returncode": result.get("returncode"),
        "stdout_excerpt": _bounded_text(result.get("stdout")),
        "stderr_excerpt": _bounded_text(result.get("stderr")),
        "error": result.get("error"),
    }


def _bounded_text(value: Any, *, limit: int = 4000) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _find_step(plan: dict[str, Any], step_id: str) -> dict[str, Any]:
    for step in plan.get("steps") or []:
        if step.get("step_id") == step_id:
            return step
    raise OperatorStepNotFound(f"operator plan step not found: {step_id}")


def _select_commands(commands: list[str], *, command_indexes: Iterable[int] | None) -> list[str]:
    indexes = list(command_indexes or [])
    if not indexes:
        return list(commands)
    selected: list[str] = []
    for index in indexes:
        if index < 1 or index > len(commands):
            raise ValueError(f"command index {index} is out of range 1..{len(commands)}")
        selected.append(commands[index - 1])
    return selected


def _is_allowed_argv(argv: list[str]) -> bool:
    if len(argv) < 2:
        return False

    module_payload = _module_command_payload(argv)
    if module_payload is not None:
        module, args = module_payload
        shape = _command_shape(args)
        if shape is None:
            return False
        return _is_allowed_module_command(module, shape)

    root = argv[0]
    shape = _command_shape(argv[1:])
    if shape is None:
        return False
    return _is_allowed_legacy_command(root, shape)


def _module_command_payload(argv: list[str]) -> tuple[str, list[str]] | None:
    if len(argv) < 4:
        return None
    if argv[0] not in _PYTHON_MODULE_COMMAND_ROOTS or argv[1] != "-m":
        return None
    return argv[2], argv[3:]


def _is_allowed_module_command(module: str, shape: CommandShape) -> bool:
    if module == _BB_MODULE:
        return shape.non_option_tokens in _BB_ALLOWED_COMMANDS
    if module in _MODULE_COMMANDS and len(shape.non_option_tokens) == 1:
        return (module, shape.non_option_tokens[0]) in _ALLOWED_COMMANDS
    return False


def _is_allowed_legacy_command(root: str, shape: CommandShape) -> bool:
    if root == "bb":
        return shape.non_option_tokens in _BB_ALLOWED_COMMANDS
    if len(shape.non_option_tokens) != 1:
        return False
    return (root, shape.non_option_tokens[0]) in _ALLOWED_COMMANDS


def _command_shape(tokens: list[str]) -> CommandShape | None:
    non_options: list[str] = []
    options: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in _OPTIONS_WITH_VALUES:
            if index + 1 >= len(tokens):
                return None
            value = tokens[index + 1]
            if value.startswith("--"):
                return None
            options[token] = value
            index += 2
            continue
        if token.startswith("--"):
            return None
        non_options.append(token)
        index += 1
    return CommandShape(non_option_tokens=tuple(non_options), options=options)
