from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence
from uuid import UUID

from .settings import CliSettings


@dataclass(frozen=True, slots=True)
class WorkerRunResult:
    """Result of a local dev invocation of the external agent worker.

    The CLI still does not become an agent runtime. This helper only spawns the
    already separate `agent_worker` process so developers can verify the loop
    from a terminal before wiring a polished UI.
    """

    status: str
    exit_code: int | None
    command: list[str]
    stdout: str
    stderr: str
    skipped: bool = False

    def as_payload(self) -> dict[str, object]:
        return asdict(self)


def run_agent_worker_once(
    *,
    settings: CliSettings,
    program_id: UUID,
    campaign_id: UUID | None = None,
    command: Sequence[str] | None = None,
    timeout_seconds: float = 60.0,
) -> WorkerRunResult:
    """Run one external agent-worker sweep for CLI/dev feedback loops."""

    cmd = list(command) if command else [sys.executable, "-m", "agent_worker", "run-once"]
    env = _worker_env(settings=settings, program_id=program_id, campaign_id=campaign_id)
    try:
        completed = subprocess.run(  # noqa: S603 - command is explicit operator/dev input.
            cmd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return WorkerRunResult(
            status="not_found",
            exit_code=None,
            command=cmd,
            stdout="",
            stderr=str(exc),
        )
    except subprocess.TimeoutExpired as exc:
        return WorkerRunResult(
            status="timeout",
            exit_code=None,
            command=cmd,
            stdout=exc.stdout or "",
            stderr=exc.stderr or f"agent worker timed out after {timeout_seconds:g}s",
        )
    return WorkerRunResult(
        status="ok" if completed.returncode == 0 else "failed",
        exit_code=completed.returncode,
        command=cmd,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def skipped_worker_result() -> WorkerRunResult:
    return WorkerRunResult(
        status="skipped",
        exit_code=None,
        command=[],
        stdout="",
        stderr="",
        skipped=True,
    )


def _worker_env(*, settings: CliSettings, program_id: UUID, campaign_id: UUID | None) -> dict[str, str]:
    env = dict(os.environ)
    env["CONTROL_API_BASE_URL"] = settings.api_url
    env["AGENT_WORKER_PROGRAM_ID"] = str(program_id)
    if campaign_id is not None:
        env["AGENT_WORKER_CAMPAIGN_ID"] = str(campaign_id)
    elif "AGENT_WORKER_CAMPAIGN_ID" in env:
        env.pop("AGENT_WORKER_CAMPAIGN_ID", None)
    if settings.agent_internal_token and not env.get("AGENT_PROTOCOL_INTERNAL_TOKEN"):
        env["AGENT_PROTOCOL_INTERNAL_TOKEN"] = settings.agent_internal_token
    env.setdefault("AGENT_WORKER_RUNTIME", "langgraph")
    env["PYTHONPATH"] = _pythonpath_for_repo(env.get("PYTHONPATH"))
    return env


def _pythonpath_for_repo(existing: str | None) -> str:
    current = Path(__file__).resolve()
    repo_root = current.parents[3]
    candidates = [
        (repo_root / "src").as_posix(),
        (repo_root / "services" / "agent-worker").as_posix(),
        (repo_root / "services" / "bb-cli").as_posix(),
    ]
    if existing:
        candidates.append(existing)
    seen: set[str] = set()
    ordered = []
    for value in candidates:
        if value and value not in seen:
            ordered.append(value)
            seen.add(value)
    return os.pathsep.join(ordered)
