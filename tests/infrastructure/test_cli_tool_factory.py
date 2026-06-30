from __future__ import annotations

import asyncio
import logging
from uuid import uuid4

import pytest

from api.application.services.mapcidr import MapCIDRService
from api.infrastructure.commands.command_boundary import CommandInvocation
from api.infrastructure.parsers.httpx_parser import HTTPXProcessEventParser
from api.infrastructure.runners.cli_tool import (
    CliCommandPlan,
    CliToolSpec,
    GenericCliToolRunner,
    ToolErrorPolicy,
)
from api.infrastructure.runners.cli_tool_factory import CliToolRunnerFactory
from api.application.process_event_contracts import ProcessEvent


class SettingsStub:
    FFUF_WORDLIST = "/tmp/words.txt"
    FFUF_RATE_LIMIT = 7
    AMASS_WORDLIST = "/tmp/amass.txt"

    def get_tool_path(self, tool_name: str) -> str:
        return f"/tools/{tool_name}"


def test_cli_tool_runner_factory_creates_generic_runner_with_static_options() -> None:
    runner = CliToolRunnerFactory(SettingsStub()).create("ffuf")  # type: ignore[arg-type]

    assert runner.spec.name == "ffuf"
    assert runner.executable == "/tools/ffuf"
    assert runner.static_options == {
        "wordlist": "/tmp/words.txt",
        "rate_limit": 7,
    }


def test_cli_tool_options_are_derived_from_command_signature() -> None:
    runner = CliToolRunnerFactory(SettingsStub()).create("naabu")  # type: ignore[arg-type]

    assert "ports" in runner.accepted_option_names
    assert "scan_mode" in runner.accepted_option_names
    assert "made_up_option" not in runner.accepted_option_names


class MapCIDRExecutor:
    calls: list[CommandInvocation] = []

    def __init__(self, command: CommandInvocation) -> None:
        self.calls.append(command)

    async def run(self):
        yield ProcessEvent(type="started")
        yield ProcessEvent(type="stdout", payload="192.0.2.1")
        yield ProcessEvent(type="terminated")


class RecordingBus:
    def __init__(self) -> None:
        self.events = []

    async def publish(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_mapcidr_service_uses_cli_tool_factory_without_wrapper() -> None:
    MapCIDRExecutor.calls.clear()
    service = MapCIDRService(
        runner_factory=CliToolRunnerFactory(
            SettingsStub(),  # type: ignore[arg-type]
            executor_cls=MapCIDRExecutor,  # type: ignore[arg-type]
        ),
        bus=RecordingBus(),  # type: ignore[arg-type]
    )

    result = await service.expand(uuid4(), ["192.0.2.0/30"], skip_base=True)

    assert result.output_count == 1
    assert MapCIDRExecutor.calls[0].argv == ("/tools/mapcidr", "-silent", "-skip-base")


def test_log_and_continue_does_not_swallow_command_builder_bug() -> None:
    def broken_commands(executable: str, targets, *, mode: str = "broken"):
        raise ValueError("programming bug")
        yield CliCommandPlan([executable], error_policy=ToolErrorPolicy.LOG_AND_CONTINUE)

    runner = GenericCliToolRunner(
        CliToolSpec(
            name="broken",
            executable="broken",
            build_commands=broken_commands,
            parser_factory=HTTPXProcessEventParser,
            timeout=1,
        ),
        logger=logging.getLogger("test"),
        executor_cls=MapCIDRExecutor,  # type: ignore[arg-type]
    )

    async def consume() -> None:
        async for _ in runner.run_raw(["example.com"]):
            pass

    with pytest.raises(ValueError, match="programming bug"):
        asyncio.run(consume())


def test_cli_tool_options_must_be_keyword_only() -> None:
    def bad_commands(executable: str, targets, rate: int = 10):
        yield CliCommandPlan([executable, str(rate)])

    with pytest.raises(TypeError, match="must be keyword-only"):
        CliToolSpec(
            name="bad",
            executable="bad",
            build_commands=bad_commands,
            parser_factory=HTTPXProcessEventParser,
            timeout=1,
        )
