from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from api.application.contracts import SafetyLevel, ToolInvocation
from api.application.execution_limits import ExecutionBudget
from api.application.pipeline.invocation import run_raw
from api.infrastructure.commands.command_boundary import CommandInvocation
from api.infrastructure.runners.cli_tool_factory import CliToolRunnerFactory



class SettingsStub:
    FFUF_WORDLIST = "/tmp/words.txt"
    FFUF_RATE_LIMIT = 100
    AMASS_WORDLIST = "/tmp/amass.txt"

    def get_tool_path(self, tool_name: str) -> str:
        return tool_name


def _runner(tool_name: str, **options: Any):
    settings = SettingsStub()
    if "rate_limit" in options:
        settings.FFUF_RATE_LIMIT = options.pop("rate_limit")
    return CliToolRunnerFactory(
        settings,  # type: ignore[arg-type]
        executor_cls=RecordingExecutor,
    ).create(tool_name, **options)


@dataclass
class CapturedCommand:
    command: list[str]
    stdin: str | None
    timeout: int | float | None


class RecordingExecutor:
    calls: list[CapturedCommand] = []

    def __init__(
        self,
        command: list[str] | CommandInvocation,
        *,
        stdin: str | None = None,
        timeout: int | float | None = None,
    ) -> None:
        if isinstance(command, CommandInvocation):
            self.calls.append(
                CapturedCommand(
                    command=list(command.argv),
                    stdin=command.stdin,
                    timeout=command.timeout,
                )
            )
            return
        self.calls.append(
            CapturedCommand(command=list(command), stdin=stdin, timeout=timeout)
        )

    async def run(self):
        if False:
            yield None


def _invocation(
    capability_id: str,
    options: dict[str, Any],
    *,
    budget: ExecutionBudget | None = None,
) -> ToolInvocation:
    return ToolInvocation(
        action_id=uuid4(),
        job_id=uuid4(),
        run_id=uuid4(),
        program_id=uuid4(),
        capability_id=capability_id,
        profile_id="test-profile",
        targets=["https://example.com"],
        options=options,
        safety_level=SafetyLevel.SAFE_ACTIVE,
        scope_decision_id=uuid4(),
        policy_decision_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        execution_budget=budget
        or ExecutionBudget(
            max_duration_seconds=600,
            max_targets=100,
            rate_per_second=1000,
            concurrency=5,
        ),
    )


async def _consume(stream) -> None:
    async for _ in stream:
        pass


@pytest.fixture(autouse=True)
def clear_recorded_commands() -> None:
    RecordingExecutor.calls.clear()


@pytest.mark.asyncio
async def test_httpx_invocation_timeout_reaches_command_executor() -> None:
    runner = _runner("httpx")

    await _consume(
        run_raw(
            runner,
            ["https://example.com"],
            _invocation("httpx", {"timeout": 17}),
        )
    )

    assert RecordingExecutor.calls[0].timeout == 17


@pytest.mark.asyncio
async def test_katana_invocation_controls_depth_features_and_timeout() -> None:
    runner = _runner("katana")

    await _consume(
        run_raw(
            runner,
            ["https://example.com"],
            _invocation(
                "katana",
                {
                    "depth": 2,
                    "js_crawl": False,
                    "headless": False,
                    "timeout": 19,
                },
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.command[captured.command.index("-d") + 1] == "2"
    assert "-jc" not in captured.command
    assert "-hl" not in captured.command
    assert captured.timeout == 19


@pytest.mark.asyncio
async def test_ffuf_invocation_timeout_reaches_command_executor() -> None:
    runner = _runner("ffuf")

    await _consume(
        run_raw(
            runner,
            "https://example.com",
            _invocation("ffuf", {"timeout": 23}),
        )
    )

    assert RecordingExecutor.calls[0].timeout == 23


@pytest.mark.asyncio
async def test_naabu_invocation_reaches_typed_scan_arguments() -> None:
    runner = _runner("naabu")

    await _consume(
        run_raw(
            runner,
            ["api.example.com"],
            _invocation(
                "naabu",
                {
                    "ports": "80,443",
                    "rate": 25,
                    "scan_mode": "active",
                    "scan_type": "c",
                    "exclude_cdn": False,
                    "timeout": 29,
                },
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.command[captured.command.index("-p") + 1] == "80,443"
    assert captured.command[captured.command.index("-rate") + 1] == "25"
    assert "-exclude-cdn" not in captured.command
    assert captured.timeout == 29


@pytest.mark.asyncio
async def test_httpx_budget_clamps_timeout_and_threads() -> None:
    runner = _runner("httpx")
    targets = [f"https://host-{index}.example.com" for index in range(10)]

    await _consume(
        run_raw(
            runner,
            targets,
            _invocation(
                "httpx",
                {"timeout": 90},
                budget=ExecutionBudget(
                    max_duration_seconds=30,
                    concurrency=3,
                ),
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.timeout == 30
    assert captured.command[captured.command.index("-t") + 1] == "3"


@pytest.mark.asyncio
async def test_katana_budget_clamps_timeout_and_parallelism() -> None:
    runner = _runner("katana")

    await _consume(
        run_raw(
            runner,
            ["https://example.com"],
            _invocation(
                "katana",
                {"timeout": 90},
                budget=ExecutionBudget(
                    max_duration_seconds=30,
                    concurrency=2,
                ),
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.timeout == 30
    assert captured.command[captured.command.index("-c") + 1] == "2"
    assert captured.command[captured.command.index("-p") + 1] == "2"


@pytest.mark.asyncio
async def test_ffuf_budget_clamps_timeout_rate_and_threads() -> None:
    runner = _runner("ffuf", rate_limit=100)

    await _consume(
        run_raw(
            runner,
            "https://example.com",
            _invocation(
                "ffuf",
                {"timeout": 90},
                budget=ExecutionBudget(
                    max_duration_seconds=30,
                    rate_per_second=5,
                    concurrency=2,
                ),
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.timeout == 30
    assert captured.command[captured.command.index("-rate") + 1] == "5"
    assert captured.command[captured.command.index("-t") + 1] == "2"


@pytest.mark.asyncio
async def test_naabu_budget_clamps_timeout_rate_and_concurrency() -> None:
    runner = _runner("naabu")

    await _consume(
        run_raw(
            runner,
            ["api.example.com"],
            _invocation(
                "naabu",
                {
                    "rate": 100,
                    "scan_mode": "active",
                    "timeout": 90,
                },
                budget=ExecutionBudget(
                    max_duration_seconds=30,
                    rate_per_second=25,
                    concurrency=2,
                ),
            ),
        )
    )

    captured = RecordingExecutor.calls[0]
    assert captured.timeout == 30
    assert captured.command[captured.command.index("-rate") + 1] == "25"
    assert captured.command[captured.command.index("-c") + 1] == "2"
